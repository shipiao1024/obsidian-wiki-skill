#!/usr/bin/env python
"""Supporting script for the review stage in the WeChat Obsidian LLM wiki.

Three-stage architecture:
  --collect-only : Collect review data → JSON for LLM prioritization (Phase 1)
  --apply        : Execute LLM decisions from JSON (Phase 3)
  --write        : Write wiki/review_queue.md (legacy or from LLM result)
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from pipeline.encoding_fix import fix_windows_encoding
from pipeline.shared import resolve_vault, validate_apply_json
from pipeline.text_utils import (
    FRONTMATTER,
    SECTION_PATTERN,
    CLAIM_PATTERN,
    parse_frontmatter,
    section_body,
)

# Sweep constants
SWEEP_BATCH_SIZE = 20
SWEEP_MAX_BATCHES = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supporting script for the review stage: generate a review queue page from pending outputs.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--collect-only", action="store_true", help="Collect review data as JSON for LLM analysis.")
    parser.add_argument("--sweep", action="store_true", help="Sweep mode: auto-resolve stale outputs via rule matching + LLM judgment.")
    parser.add_argument("--apply", type=Path, dest="apply_json", help="Execute LLM prioritization from result JSON.")
    parser.add_argument("--apply-sweep", type=Path, dest="apply_sweep_json", help="Execute LLM sweep decisions from result JSON.")
    parser.add_argument("--output", type=Path, help="Output path for --collect-only JSON.")
    parser.add_argument("--write", action="store_true", help="Write wiki/review_queue.md")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size for sweep LLM judgment.")
    parser.add_argument("--max-batches", type=int, default=3, help="Maximum number of sweep batches.")
    return parser.parse_args()


def summary_line(meta: dict[str, str], body: str) -> str:
    page_type = meta.get("type", "")
    if page_type == "delta-compile":
        summary = (
            section_body(body, "关键判断")
            or section_body(body, "建议替换的一句话结论")
            or section_body(body, "背景")
            or "待复核草稿"
        )
        return re.sub(r"\s+", " ", summary).strip()
    answer = section_body(body, "回答") or "待复核问答"
    first = [line.strip() for line in answer.splitlines() if line.strip() and not line.strip().endswith("：")]
    return re.sub(r"\s+", " ", (first[0] if first else answer)).strip()


def lifecycle_rank(meta: dict[str, str]) -> tuple[int, str]:
    lifecycle = meta.get("lifecycle", "")
    order = {
        "review-needed": 0,
        "temporary": 1,
        "accepted": 2,
        "absorbed": 3,
        "archived": 4,
    }
    return order.get(lifecycle, 9), lifecycle


def low_quality_source_items(vault: Path) -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    for path in sorted((vault / "wiki" / "sources").glob("*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if meta.get("quality", "").strip().lower() != "low":
            continue
        title = meta.get("title") or path.stem
        summary = summary_line(meta, body)
        items.append((path.stem, title, summary))
    return items


def low_confidence_claims(vault: Path) -> list[tuple[str, str, str, str]]:
    items: list[tuple[str, str, str, str]] = []
    for folder in ("sources", "briefs"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            _, body = parse_frontmatter(text)
            claim_section = section_body(body, "关键判断")
            if not claim_section:
                continue
            for match in CLAIM_PATTERN.finditer(claim_section):
                confidence = match.group(2).strip().lower()
                if confidence == "low":
                    claim_text = match.group(3).strip().rstrip("⚠️需验证").strip()
                    items.append((folder, path.stem, confidence, claim_text))
    return items


def upgradable_candidate_pages(vault: Path) -> list[tuple[str, str, str, int]]:
    from pipeline.extractors import page_mention_count
    items: list[tuple[str, str, str, int]] = []
    for folder in ("concepts", "entities"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            if meta.get("lifecycle") != "candidate":
                continue
            name = meta.get("title") or path.stem
            ref_count = page_mention_count(vault, "sources", name)
            if ref_count >= 2:
                items.append((folder, path.stem, name, ref_count))
    return items


def collect_review_data(vault: Path) -> dict:
    """Phase 1: Collect review data for LLM prioritization."""
    outputs = sorted((vault / "wiki" / "outputs").glob("*.md"))
    pending_outputs: list[dict[str, str]] = []
    absorbed_count = 0
    archived_count = 0

    for path in outputs:
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = meta.get("title") or path.stem
        lifecycle = meta.get("lifecycle", "")
        created = meta.get("date", "")
        sources_cited = len(re.findall(r"\[\[sources/([^\]]+)\]\]", body))

        if lifecycle == "absorbed":
            absorbed_count += 1
        elif lifecycle == "archived":
            archived_count += 1
        elif lifecycle in {"temporary", "review-needed"}:
            pending_outputs.append({
                "path": f"outputs/{path.stem}",
                "type": meta.get("type", ""),
                "lifecycle": lifecycle,
                "title": title,
                "created": created,
                "sources_cited": sources_cited,
                "has_draft": meta.get("has_draft", "true"),
                "summary": summary_line(meta, body)[:200],
            })

    # Candidate pages
    candidate_pages: list[dict[str, str]] = []
    for folder in ("sources", "briefs", "concepts", "entities"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.glob("*.md")):
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            if meta.get("lifecycle") == "candidate":
                name = meta.get("title") or path.stem
                from pipeline.extractors import page_mention_count
                mention_count = page_mention_count(vault, "sources", name)
                candidate_pages.append({
                    "path": f"{folder}/{path.stem}",
                    "lifecycle": "candidate",
                    "mention_count": mention_count,
                    "title": meta.get("title", path.stem).strip('"'),
                })

    # Low-confidence claims
    low_claims = low_confidence_claims(vault)
    low_confidence = [
        {"path": f"{folder}/{slug}", "claim": claim_text}
        for folder, slug, _conf, claim_text in low_claims
    ]

    return {
        "pending_outputs": pending_outputs,
        "candidate_pages": candidate_pages,
        "low_confidence_claims": low_confidence,
        "absorbed_count": absorbed_count,
        "archived_count": archived_count,
    }


def apply_review_result(vault: Path, result_path: Path, write: bool = False) -> dict:
    """Phase 3: Execute LLM prioritization decisions."""
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validate_apply_json(result, ["prioritized_items"], context="review_queue")
    prioritized = result.get("prioritized_items", [])
    upgrades = result.get("upgrade_recommendations", [])
    summary = result.get("summary", {})

    actions_taken: list[str] = []
    for item in prioritized:
        path = item.get("path", "")
        action = item.get("action", "skip")
        reason = item.get("reason", "")
        if action == "approve":
            actions_taken.append(f"[approve] {path}: {reason}")
        elif action == "archive":
            # Move to archived lifecycle
            full_path = vault / "wiki" / f"{path}.md"
            if full_path.exists():
                text = full_path.read_text(encoding="utf-8")
                text = text.replace('lifecycle: "temporary"', 'lifecycle: "archived"')
                text = text.replace('lifecycle: "review-needed"', 'lifecycle: "archived"')
                full_path.write_text(text, encoding="utf-8")
                actions_taken.append(f"[archive] {path}")
        elif action == "review":
            actions_taken.append(f"[review] {path}: {reason}")
        # skip: no action

    for upgrade in upgrades:
        path = upgrade.get("path", "")
        to_lifecycle = upgrade.get("to_lifecycle", "official")
        full_path = vault / "wiki" / f"{path}.md"
        if full_path.exists():
            text = full_path.read_text(encoding="utf-8")
            text = text.replace('lifecycle: "candidate"', f'lifecycle: "{to_lifecycle}"')
            full_path.write_text(text, encoding="utf-8")
            actions_taken.append(f"[upgrade] {path} → {to_lifecycle}")

    return {
        "actions": actions_taken,
        "summary": summary,
    }


def _existing_wiki_pages(vault: Path) -> set[str]:
    """Collect all existing page paths under wiki/ (relative to vault)."""
    pages: set[str] = set()
    wiki_root = vault / "wiki"
    if not wiki_root.exists():
        return pages
    for md_path in wiki_root.rglob("*.md"):
        rel = md_path.relative_to(vault)
        # Strip .md extension for wikilink matching
        pages.add(str(rel.with_suffix("")))
    return pages


def _extract_wikilinks(body: str) -> list[str]:
    """Extract [[wikilink]] targets from body text."""
    import re
    return re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]", body)


def _rule_match_sweep(
    pending_outputs: list[dict[str, str]],
    existing_pages: set[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Apply R1 and R2 rule matching. Returns (auto_resolved, remaining_for_llm)."""
    auto_resolved: list[dict[str, str]] = []
    remaining: list[dict[str, str]] = []

    # R1: missing-page — if all referenced pages now exist
    r1_resolved_paths: set[str] = set()
    for item in pending_outputs:
        mode = item.get("mode", "")
        item_type = item.get("type", "")
        if mode == "insight" or item_type == "query":
            refs = item.get("referenced_pages", [])
            if refs and all(ref in existing_pages for ref in refs):
                auto_resolved.append({
                    **item,
                    "status": "resolved",
                    "reason": "all_referenced_pages_exist",
                    "detail": f"All {len(refs)} referenced pages now exist in wiki/",
                })
                r1_resolved_paths.add(item["path"])
                continue

    # R2: superseded — multiple outputs with same normalized title
    from collections import defaultdict
    title_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in pending_outputs:
        if item["path"] in r1_resolved_paths:
            continue
        norm_title = item.get("normalized_title", item.get("title", "").lower().strip())
        title_groups[norm_title].append(item)

    r2_resolved_paths: set[str] = set()
    for norm_title, group in title_groups.items():
        if len(group) <= 1:
            continue
        # Sort by created date, keep newest
        group.sort(key=lambda x: x.get("created", ""), reverse=True)
        for old_item in group[1:]:
            auto_resolved.append({
                **old_item,
                "status": "resolved",
                "reason": "superseded_by_newer",
                "detail": f"Superseded by {group[0]['path']} (newer date)",
            })
            r2_resolved_paths.add(old_item["path"])

    # Remaining for LLM judgment
    for item in pending_outputs:
        if item["path"] not in r1_resolved_paths and item["path"] not in r2_resolved_paths:
            remaining.append(item)

    return auto_resolved, remaining


def collect_sweep_data(vault: Path, batch_size: int = SWEEP_BATCH_SIZE) -> dict:
    """Phase 1: Collect sweep data — rule matching + batch info for LLM."""
    outputs = sorted((vault / "wiki" / "outputs").glob("*.md"))
    existing_pages = _existing_wiki_pages(vault)

    pending_outputs: list[dict[str, str]] = []
    for path in outputs:
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        lifecycle = meta.get("lifecycle", "")
        if lifecycle not in {"temporary", "review-needed"}:
            continue
        title = meta.get("title") or path.stem
        # Normalize title for R2 matching
        norm_title = re.sub(
            r"^(missing[\s-]?page[:：]\s*|duplicate[\s-]?page[:：]\s*|缺失页面[:：]\s*|缺少页面[:：]\s*|重复页面[:：]\s*|疑似重复[:：]\s*)",
            "", title, flags=re.I
        ).strip().lower()

        refs = _extract_wikilinks(body)

        pending_outputs.append({
            "path": f"outputs/{path.stem}",
            "type": meta.get("type", ""),
            "mode": meta.get("mode", ""),
            "lifecycle": lifecycle,
            "title": title,
            "normalized_title": norm_title,
            "created": meta.get("date", ""),
            "sources_cited": len(re.findall(r"\[\[sources/([^\]]+)\]\]", body)),
            "summary": summary_line(meta, body)[:200],
            "referenced_pages": refs,
        })

    # Apply R1 + R2 rules
    auto_resolved, remaining = _rule_match_sweep(pending_outputs, existing_pages)

    # Split remaining into batches for LLM
    batches: list[list[dict[str, str]]] = []
    for i in range(0, len(remaining), batch_size):
        batches.append(remaining[i:i + batch_size])

    # Trim referenced_pages for output (too verbose for LLM context)
    for item in auto_resolved:
        item.pop("referenced_pages", None)
        item.pop("normalized_title", None)
    for batch in batches:
        for item in batch:
            item.pop("referenced_pages", None)
            item.pop("normalized_title", None)

    return {
        "auto_resolved": auto_resolved,
        "pending_for_llm": remaining,
        "batches": batches[:SWEEP_MAX_BATCHES],
        "total_pending": len(pending_outputs),
        "auto_resolved_count": len(auto_resolved),
        "llm_batch_count": min(len(batches), SWEEP_MAX_BATCHES),
        "batch_size": batch_size,
        "existing_pages_sample": sorted(existing_pages)[:50],
    }


def apply_sweep_result(vault: Path, result_path: Path) -> dict:
    """Phase 3: Execute LLM sweep decisions."""
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validate_apply_json(result, ["sweep_results"], context="review_sweep")
    sweep_results = result.get("sweep_results", [])
    summary = result.get("summary", {})

    actions_taken: list[str] = []
    for item in sweep_results:
        path = item.get("path", "")
        status = item.get("status", "pending")
        reason = item.get("reason", "")

        if status != "resolved":
            continue

        full_path = vault / "wiki" / f"{path}.md"
        if not full_path.exists():
            actions_taken.append(f"[skip] {path}: file not found")
            continue

        text = full_path.read_text(encoding="utf-8")
        # Update lifecycle to archived
        text = text.replace('lifecycle: "temporary"', 'lifecycle: "archived"')
        text = text.replace('lifecycle: "review-needed"', 'lifecycle: "archived"')
        text = text.replace("lifecycle: temporary", 'lifecycle: "archived"')
        text = text.replace("lifecycle: review-needed", 'lifecycle: "archived"')
        full_path.write_text(text, encoding="utf-8")
        actions_taken.append(f"[resolved] {path}: {reason}")

    return {
        "actions": actions_taken,
        "summary": summary,
    }


def build_review_queue_page(vault: Path) -> str:
    """Build review queue page from current vault state (mechanical)."""
    outputs = sorted((vault / "wiki" / "outputs").glob("*.md"))
    pending: list[tuple[str, str, str, str]] = []
    absorbed: list[tuple[str, str, str, str]] = []
    archived: list[tuple[str, str, str, str]] = []
    active_groups: defaultdict[str, list[str]] = defaultdict(list)

    for path in outputs:
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = meta.get("title") or path.stem
        lifecycle = meta.get("lifecycle", "")
        item = (path.stem, title, lifecycle, summary_line(meta, body))
        if lifecycle == "absorbed":
            absorbed.append(item)
        elif lifecycle == "archived":
            archived.append(item)
        elif lifecycle in {"temporary", "review-needed"}:
            pending.append(item)
            active_groups[title].append(path.stem)

    pending.sort(key=lambda item: (lifecycle_rank({"lifecycle": item[2]}), item[0]))
    duplicates = {title: stems for title, stems in active_groups.items() if len(stems) > 1}
    low_quality_sources = low_quality_source_items(vault)

    lines = [
        "---",
        'title: "Review Queue"',
        'type: "system-review-queue"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        "---",
        "",
        "# Review Queue",
        "",
        "> 只看待处理 output，不把已吸收历史草稿混进日常导航。",
        "",
    ]

    # Low quality sources
    lines.extend(["## 低质量来源候选", ""])
    if low_quality_sources:
        for stem, title, summary in low_quality_sources:
            lines.append(f"- [[sources/{stem}]] | {title}")
            lines.append(f"  - {summary}")
    else:
        lines.append("- 当前没有低质量来源候选。")

    # Pending
    lines.extend(["", "## 待处理", ""])
    if pending:
        for stem, title, lifecycle, summary in pending:
            lines.append(f"- [[outputs/{stem}]] | `{lifecycle}` | {title}")
            lines.append(f"  - {summary}")
    else:
        lines.append("- 当前没有待处理 output。")

    # Duplicates
    lines.extend(["", "## 重复候选", ""])
    if duplicates:
        for title, stems in sorted(duplicates.items()):
            lines.append(f"- {title}")
            for stem in sorted(stems):
                lines.append(f"  - [[outputs/{stem}]]")
    else:
        lines.append("- 当前没有标题重复的 output。")

    # Stats
    lines.extend(["", "## 统计", ""])
    lines.append(f"- 已吸收：{len(absorbed)}")
    lines.append(f"- 已归档：{len(archived)}")
    lines.append(f"- 待处理：{len(pending)}")

    # Candidate pages
    candidate_pages: list[tuple[str, str, str]] = []
    for folder in ("sources", "briefs"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.glob("*.md")):
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            if meta.get("lifecycle") == "candidate":
                title = meta.get("title") or path.stem
                summary = summary_line(meta, body)
                candidate_pages.append((folder, path.stem, title, summary))

    lines.extend(["", "## 候选页待审", ""])
    if candidate_pages:
        for folder, stem, title, summary in candidate_pages:
            lines.append(f"- [[{folder}/{stem}]] | {title}")
            lines.append(f"  - {summary}")
    else:
        lines.append("- 当前没有候选页待审。")

    # Low-confidence claims
    low_claims = low_confidence_claims(vault)
    lines.extend(["", "## 低置信判断", ""])
    if low_claims:
        for folder, stem, confidence, claim_text in low_claims:
            lines.append(f"- [[{folder}/{stem}]] | `low` | {claim_text}")
    else:
        lines.append("- 当前没有低置信判断。")

    # Upgradable candidates
    upgradable = upgradable_candidate_pages(vault)
    lines.extend(["", "## 可升级候选页", ""])
    if upgradable:
        for folder, stem, name, ref_count in upgradable:
            lines.append(f"- [[{folder}/{stem}]] | {name} | {ref_count} 次引用")
    else:
        lines.append("- 当前没有可升级的候选页。")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    if args.apply_json:
        result = apply_review_result(vault, args.apply_json, write=args.write)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.apply_sweep_json:
        result = apply_sweep_result(vault, args.apply_sweep_json)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.sweep:
        data = collect_sweep_data(vault, batch_size=args.batch_size)
        output = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Sweep data written to {args.output}")
        else:
            print(output)
        return 0

    if args.collect_only:
        data = collect_review_data(vault)
        output = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Review data written to {args.output}")
        else:
            print(output)
        return 0

    # Legacy mode: build page + JSON report
    page = build_review_queue_page(vault)
    page_path = vault / "wiki" / "review_queue.md"
    if args.write:
        page_path.write_text(page, encoding="utf-8")

    # Build report JSON
    data = collect_review_data(vault)
    report = {
        "pending_count": len(data["pending_outputs"]),
        "absorbed_count": data["absorbed_count"],
        "archived_count": data["archived_count"],
        "pending": data["pending_outputs"],
        "candidate_pages": data["candidate_pages"],
        "low_confidence_claims": data["low_confidence_claims"],
    }
    if args.write:
        report["page"] = str(page_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
