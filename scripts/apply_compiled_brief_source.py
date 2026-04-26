#!/usr/bin/env python
"""Supporting script for the apply stage in the WeChat Obsidian LLM wiki.

This script accepts a structured compile result and applies it into
official brief/source pages plus review-ready delta drafts.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from wiki_ingest_wechat import (
    Article,
    build_brief_page_from_compile,
    build_source_page_from_compile,
    sanitize_filename,
    ensure_synthesis_pages,
    ensure_taxonomy_pages,
    parse_frontmatter,
    rebuild_index,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supporting script for the apply stage: write brief/source from a structured compile result.")
    parser.add_argument("--vault", type=Path, required=True, help="Obsidian vault root.")
    parser.add_argument("--raw", type=Path, required=True, help="Raw article markdown path.")
    parser.add_argument("--compiled-json", type=Path, required=True, help="Structured compile result JSON path.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing brief/source pages.")
    return parser.parse_args()


def article_from_raw(raw_path: Path) -> tuple[Article, str]:
    text = raw_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    title = meta.get("title") or raw_path.stem
    article = Article(
        title=title,
        author=meta.get("author", ""),
        date=meta.get("date", ""),
        source=meta.get("source", ""),
        body=body.strip(),
        src_dir=raw_path.parent,
        md_path=raw_path,
    )
    return article, raw_path.stem


def load_compiled_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Compiled result must be a JSON object: {path}")
    if "brief" not in data or "source" not in data:
        raise SystemExit(f"Compiled result missing brief/source keys: {path}")
    return data


def load_compiled_json_any(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Compiled result must be a JSON object: {path}")
    if str(data.get("version", "")).strip() == "2.0":
        return {"schema_version": "2.0", "result": data}
    if "schema_version" in data and "result" in data:
        schema_version = str(data.get("schema_version", "")).strip() or "1.0"
        result = data.get("result")
        if not isinstance(result, dict):
            raise SystemExit(f"Compiled result wrapper missing object result: {path}")
        return {"schema_version": schema_version, "result": result}
    if "brief" in data and "source" in data:
        return {"schema_version": "1.0", "result": data}
    raise SystemExit(f"Compiled result missing recognized schema keys: {path}")


def extract_document_outputs(compiled_payload: dict[str, object]) -> dict[str, object]:
    schema_version = compiled_payload.get("schema_version")
    result = compiled_payload.get("result")
    if not isinstance(result, dict):
        raise SystemExit("Compiled payload result must be an object.")
    if schema_version == "2.0":
        outputs = result.get("document_outputs")
        if not isinstance(outputs, dict):
            raise SystemExit("V2 compiled payload missing document_outputs.")
        return outputs
    return result


def to_legacy_compile_shape(document_outputs: dict[str, object], compiled_payload: dict[str, object]) -> dict[str, object]:
    schema_version = compiled_payload.get("schema_version")
    if schema_version != "2.0":
        return document_outputs
    result = compiled_payload.get("result")
    knowledge_proposals = result.get("knowledge_proposals") if isinstance(result, dict) else {}
    domains = []
    if isinstance(knowledge_proposals, dict):
        for item in knowledge_proposals.get("domains", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
            action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
            if name and action != "no_page":
                domains.append(name)
    source = document_outputs.get("source") if isinstance(document_outputs.get("source"), dict) else {}
    return {
        "brief": document_outputs.get("brief", {}),
        "source": {
            "core_summary": source.get("core_summary", []),
            "candidate_concepts": [],
            "candidate_entities": [],
            "domains": domains,
            "knowledge_base_relation": source.get("knowledge_base_relation", []),
            "contradictions": source.get("contradictions", []),
            "reinforcements": source.get("reinforcements", []),
        },
    }


def extract_update_proposals(compiled_payload: dict[str, object]) -> list[dict[str, object]]:
    if compiled_payload.get("schema_version") != "2.0":
        return []
    result = compiled_payload.get("result")
    proposals = result.get("update_proposals") if isinstance(result, dict) else []
    claim_inventory = result.get("claim_inventory") if isinstance(result, dict) else []
    claim_items = claim_inventory if isinstance(claim_inventory, list) else []
    normalized_claims = [item for item in claim_items if isinstance(item, dict)]
    if not isinstance(proposals, list):
        return []
    extracted: list[dict[str, object]] = []
    for item in proposals:
        if not isinstance(item, dict):
            continue
        proposal = dict(item)
        if not isinstance(proposal.get("claims"), list):
            proposal["claims"] = normalized_claims
        extracted.append(proposal)
    return extracted


def compiled_domains(compiled: dict[str, object]) -> list[str]:
    source = compiled.get("source")
    if not isinstance(source, dict):
        return []
    domains = source.get("domains")
    if not isinstance(domains, list):
        return []
    return [item for item in domains if isinstance(item, str) and item.strip()]


def append_log(vault: Path, slug: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## [{timestamp}] compile_apply | {slug}",
        "",
        f"- source: [[sources/{slug}]]",
        f"- brief: [[briefs/{slug}]]",
        "",
    ]
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def append_log_v2(vault: Path, slug: str, emitted_deltas: list[Path]) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## [{timestamp}] compile_apply_v2 | {slug}",
        "",
        f"- source: [[sources/{slug}]]",
        f"- brief: [[briefs/{slug}]]",
    ]
    for path in emitted_deltas:
        lines.append(f"- delta: [[outputs/{path.stem}]]")
    lines.append("")
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def build_delta_page_from_update_proposal(
    *,
    proposal: dict[str, object],
    source_slug: str,
    article_title: str,
) -> tuple[str, str]:
    target_page = proposal.get("target_page", "").strip() if isinstance(proposal.get("target_page"), str) else ""
    target_type = proposal.get("target_type", "").strip() if isinstance(proposal.get("target_type"), str) else "source"
    action = proposal.get("action", "").strip() if isinstance(proposal.get("action"), str) else "draft_delta"
    reason = proposal.get("reason", "").strip() if isinstance(proposal.get("reason"), str) else "待人工审核。"
    confidence = proposal.get("confidence", "low")
    evidence = proposal.get("evidence", []) if isinstance(proposal.get("evidence"), list) else []
    patch = proposal.get("patch") if isinstance(proposal.get("patch"), dict) else {}
    claims = proposal.get("claims") if isinstance(proposal.get("claims"), list) else []
    slug = sanitize_filename(f"delta-{source_slug}-{Path(target_page).stem or target_type}")
    lines = [
        "---",
        f'title: "{article_title} Delta Proposal"',
        'type: "delta-compile"',
        'status: "review-needed"',
        'lifecycle: "review-needed"',
        'graph_role: "working"',
        'graph_include: "false"',
        f'source_page: "wiki/sources/{source_slug}.md"',
        f'target_page: "{target_page}"',
        f'target_type: "{target_type}"',
        "---",
        "",
        "# Delta Proposal",
        "",
        "## 目标页面",
        "",
        f"- `{target_page or 'unknown'}`",
        "",
        "## 动作",
        "",
        f"- `{action}`",
        "",
        "## 原因",
        "",
        f"- {reason}",
        "",
        "## 置信度",
        "",
        f"- {confidence}",
        "",
        "## 证据",
        "",
    ]
    lines.extend(f"- {item}" for item in evidence[:6])
    if not evidence:
        lines.append("- 待人工补充证据。")
    lines.extend(["", "## 关键判断", ""])
    for item in claims[:6]:
        if not isinstance(item, dict):
            continue
        claim = item.get("claim", "").strip() if isinstance(item.get("claim"), str) else ""
        claim_type = item.get("claim_type", "").strip() if isinstance(item.get("claim_type"), str) else "interpretation"
        confidence_label = item.get("confidence", "low")
        if claim:
            lines.append(f"- [{claim_type}|{confidence_label}] {claim}")
    if lines[-1] == "":
        lines.append("- 待人工补充关键判断。")
    lines.extend(["", "## 建议修改", ""])
    summary_delta = patch.get("summary_delta", []) if isinstance(patch.get("summary_delta"), list) else []
    content = patch.get("content", []) if isinstance(patch.get("content"), list) else []
    questions_open = patch.get("questions_open", []) if isinstance(patch.get("questions_open"), list) else []
    lines.extend(f"- {item}" for item in summary_delta[:6])
    lines.extend(f"- {item}" for item in content[:6])
    lines.extend(f"- 待验证：{item}" for item in questions_open[:4])
    if not summary_delta and not content and not questions_open:
        lines.append("- 待人工补充草稿内容。")
    lines.append("")
    return slug, "\n".join(lines)


def emit_update_proposals_as_deltas(
    *,
    vault: Path,
    proposals: list[dict[str, object]],
    source_slug: str,
    article_title: str,
) -> list[Path]:
    outputs_dir = vault / "wiki" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    emitted: list[Path] = []
    for proposal in proposals:
        claims = proposal.get("claims")
        if not isinstance(claims, list):
            proposal["claims"] = []
        slug, page = build_delta_page_from_update_proposal(
            proposal=proposal,
            source_slug=source_slug,
            article_title=article_title,
        )
        path = outputs_dir / f"{slug}.md"
        path.write_text(page, encoding="utf-8")
        emitted.append(path)
    return emitted


def main() -> int:
    args = parse_args()
    vault = args.vault.resolve()
    raw_path = args.raw.resolve()
    article, slug = article_from_raw(raw_path)
    compiled_payload = load_compiled_json_any(args.compiled_json.resolve())
    document_outputs = extract_document_outputs(compiled_payload)
    compiled = to_legacy_compile_shape(document_outputs, compiled_payload)

    brief_path = vault / "wiki" / "briefs" / f"{slug}.md"
    source_path = vault / "wiki" / "sources" / f"{slug}.md"
    if (brief_path.exists() or source_path.exists()) and not args.force:
        raise SystemExit("Target brief/source already exist. Pass --force to overwrite.")

    brief_path.write_text(build_brief_page_from_compile(article, slug, compiled), encoding="utf-8")
    source_path.write_text(build_source_page_from_compile(vault, article, slug, compiled), encoding="utf-8")
    domains = compiled_domains(compiled)
    ensure_taxonomy_pages(vault, article, slug, args.force, domains_override=domains or None)
    ensure_synthesis_pages(vault, article, slug, domains_override=domains or None)
    emitted_deltas = emit_update_proposals_as_deltas(
        vault=vault,
        proposals=extract_update_proposals(compiled_payload),
        source_slug=slug,
        article_title=article.title,
    )
    rebuild_index(vault)
    if compiled_payload.get("schema_version") == "2.0":
        append_log_v2(vault, slug, emitted_deltas)
    else:
        append_log(vault, slug)

    print(
        json.dumps(
            {
                "brief": str(brief_path),
                "source": str(source_path),
                "compile_mode": "agent-interactive-v2" if compiled_payload.get("schema_version") == "2.0" else "agent-interactive",
                "delta_outputs": [str(path) for path in emitted_deltas],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
