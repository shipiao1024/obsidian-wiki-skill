#!/usr/bin/env python
"""Rebuild synthesis pages from linked sources in the local Obsidian LLM wiki.

Three-stage architecture:
  --collect-only : Collect source data → JSON for LLM synthesis (Phase 1)
  --apply        : Write synthesis page from LLM result JSON (Phase 3)
  (default)      : Legacy mode — heuristic synthesis (deprecated for new domains)
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from pipeline.encoding_fix import fix_windows_encoding
from pipeline.shared import resolve_vault, validate_apply_json


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
RAW_SOURCE_PATTERN = re.compile(r'raw_source:\s*"\[\[([^\]]+)\]\]"')
CLAIM_PATTERN = re.compile(r"^- \[([^\]|]+)\|([^\]]+)\]\s+(.+)$", re.M)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh synthesis pages from current linked sources.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--domain", help="Specific domain name, such as 自动驾驶.")
    parser.add_argument("--collect-only", action="store_true", help="Collect source data as JSON for LLM synthesis.")
    parser.add_argument("--apply", type=Path, dest="apply_json", help="Write synthesis page from LLM result JSON.")
    parser.add_argument("--output", type=Path, help="Output path for --collect-only JSON.")
    return parser.parse_args()


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, text[match.end():]


def plain_text(md: str) -> str:
    text = FRONTMATTER.sub("", md)
    text = CODE_BLOCK.sub("", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"!\[\[[^\]]+\]\]", "", text)
    text = re.sub(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = HEADING.sub("", text)
    text = re.sub(r"[>*_`~\-\|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def section_excerpt(body: str, heading: str) -> str:
    pattern = re.compile(rf"##\s+{re.escape(heading)}\s*\n(.*?)(?:\n##\s+|\Z)", re.S)
    match = pattern.search(body)
    if not match:
        return ""
    return plain_text(match.group(1)).strip()


def outbound_links(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {match.strip() for match in LINK_PATTERN.findall(text)}


def linked_raw_path(path: Path, vault: Path) -> Path | None:
    text = path.read_text(encoding="utf-8")
    match = RAW_SOURCE_PATTERN.search(text)
    if not match:
        return None
    raw_path = vault / f"{match.group(1)}.md"
    return raw_path if raw_path.exists() else None


def extract_claims_from_source(source_path: Path) -> list[dict[str, str]]:
    text = source_path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    pattern = re.compile(r"##\s+关键判断\s*\n(.*?)(?:\n##\s+|\Z)", re.S)
    match = pattern.search(body)
    if not match:
        return []
    claims_body = match.group(1)
    claims = []
    for match in CLAIM_PATTERN.finditer(claims_body):
        claim_text = match.group(3).strip().rstrip("⚠️需验证").strip()
        claims.append({
            "claim_type": match.group(1).strip(),
            "confidence": match.group(2).strip().lower(),
            "claim": claim_text,
        })
    return claims


def synthesis_sources(vault: Path, synthesis_path: Path) -> list[Path]:
    refs = sorted(link for link in outbound_links(synthesis_path) if link.startswith("sources/"))
    return [vault / "wiki" / f"{ref}.md" for ref in refs if (vault / "wiki" / f"{ref}.md").exists()]


def collect_synthesis_data(vault: Path, synthesis_path: Path) -> dict:
    """Phase 1: Collect source data for LLM synthesis."""
    meta, body = parse_frontmatter(synthesis_path.read_text(encoding="utf-8"))
    domain = meta.get("domain") or synthesis_path.stem.replace("--综合分析", "")
    source_paths = synthesis_sources(vault, synthesis_path)

    # Existing synthesis content
    current_conclusion = section_excerpt(body, "当前结论")

    # Collect linked sources
    linked_sources: list[dict[str, str]] = []
    for source_path in source_paths:
        src_meta, src_body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
        core_summary = section_excerpt(src_body, "核心摘要")
        one_sentence = src_meta.get("one_sentence", "").strip('"')
        key_claims = extract_claims_from_source(source_path)

        linked_sources.append({
            "slug": f"sources/{source_path.stem}",
            "title": src_meta.get("title", source_path.stem).strip('"'),
            "quality": src_meta.get("quality", "unknown"),
            "date": src_meta.get("date", ""),
            "core_summary": core_summary[:500],
            "one_sentence": one_sentence,
            "key_claims": [c["claim"] for c in key_claims],
        })

    return {
        "synthesis_path": f"syntheses/{synthesis_path.stem}",
        "domain": domain,
        "source_count": len(linked_sources),
        "linked_sources": linked_sources,
        "existing_synthesis": {
            "current_conclusion": current_conclusion[:500],
        },
    }


def apply_synthesis_result(vault: Path, result_path: Path, synthesis_path: Path | None = None) -> None:
    """Phase 3: Write synthesis page from LLM result."""
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validate_apply_json(result, ["current_conclusion"], context="refresh_synthesis")
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Determine domain and path
    domain = result.get("domain", "")
    if not domain and synthesis_path:
        meta, _ = parse_frontmatter(synthesis_path.read_text(encoding="utf-8"))
        domain = meta.get("domain", synthesis_path.stem.replace("--综合分析", ""))
    if not synthesis_path:
        synthesis_path = vault / "wiki" / "syntheses" / f"{domain}--综合分析.md"

    current_conclusion = result.get("current_conclusion", "待补充。")
    core_claims = result.get("core_claims", [])
    divergences = result.get("divergences", [])
    knowledge_gaps = result.get("knowledge_gaps", [])

    # Build source links from existing page or result
    source_links: list[str] = []
    if synthesis_path.exists():
        _, old_body = parse_frontmatter(synthesis_path.read_text(encoding="utf-8"))
        for link in outbound_links(synthesis_path):
            if link.startswith("sources/"):
                source_links.append(f"- [[{link}]]")

    lines = [
        "---",
        f'title: "{domain} 综合分析"',
        'type: "synthesis"',
        'status: "draft"',
        'graph_role: "knowledge"',
        'graph_include: "true"',
        'lifecycle: "official"',
        f'domain: "{domain}"',
        f'updated_at: "{today}"',
        'analysis_method: "llm-driven"',
        "---",
        "",
        f"# {domain} 综合分析",
        "",
        "## 当前结论",
        "",
        current_conclusion,
        "",
        "## 核心判断",
        "",
    ]

    for claim in core_claims:
        conf = claim.get("confidence", "low")
        text = claim.get("text", "")
        evidence_type = claim.get("evidence_type", "")
        marker = f"{conf}" if conf != "low" else "low⚠️"
        sources = claim.get("supporting_sources", [])
        source_ref = f" —— [[{sources[0]}]]" if sources else ""
        lines.append(f"- [{marker}|{evidence_type}] {text}{source_ref}")

    if divergences:
        lines.extend(["", "## 分歧与争议", ""])
        for div in divergences:
            topic = div.get("topic", "")
            lines.append(f"### {topic}")
            lines.append("")
            for pos in div.get("positions", []):
                view = pos.get("view", "")
                sources = pos.get("sources", [])
                source_ref = f"（[[{sources[0]}]]）" if sources else ""
                lines.append(f"- {view}{source_ref}")
            lines.append("")

    if knowledge_gaps:
        lines.extend(["", "## 知识缺口", ""])
        for gap in knowledge_gaps:
            lines.append(f"- {gap}")

    lines.extend(["", "## 近期来源", ""])
    if source_links:
        lines.extend(source_links)
    else:
        lines.append("- 待补充。")

    lines.extend(["", "## 待验证 / 后续维护", ""])
    if len(source_links) <= 1:
        lines.append("- 当前主要基于单一来源，后续需要更多来源补充冲突、边界和反例。")
    else:
        lines.append("- 新来源进入该主题域时，优先检查结论是否被强化、修正或推翻。")
    lines.append("")

    synthesis_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Synthesis page written to {synthesis_path}")


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    # Determine target synthesis pages
    targets: list[Path] = []
    if args.domain:
        target = vault / "wiki" / "syntheses" / f"{args.domain}--综合分析.md"
        if not target.exists():
            raise SystemExit(f"Synthesis page not found for domain: {args.domain}")
        targets.append(target)
    else:
        targets = sorted((vault / "wiki" / "syntheses").glob("*.md"))

    if args.apply_json:
        for path in targets:
            apply_synthesis_result(vault, args.apply_json, synthesis_path=path)
        return 0

    if args.collect_only:
        all_data: list[dict] = []
        for path in targets:
            all_data.append(collect_synthesis_data(vault, path))
        output = json.dumps(all_data if len(all_data) > 1 else all_data[0], ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Synthesis data written to {args.output}")
        else:
            print(output)
        return 0

    # Legacy mode: heuristic synthesis (deprecated for new domains)
    # NOTE: This mode uses hardcoded patterns from the 自动驾驶 domain.
    # For new domains, use --collect-only → LLM → --apply instead.
    updated: list[str] = []
    for path in targets:
        # Import legacy functions only when needed
        from refresh_synthesis_legacy import build_synthesis_page_legacy
        path.write_text(build_synthesis_page_legacy(vault, path), encoding="utf-8")
        updated.append(str(path))
    print(json.dumps({"updated": updated, "mode": "legacy"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
