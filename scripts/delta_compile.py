#!/usr/bin/env python
"""Generate review-ready recompilation drafts from stale/high-churn wiki signals.

Three-stage architecture:
  --collect-only : Collect vault signals → JSON for LLM analysis (Phase 1)
  --apply        : Write delta-compile page from LLM result JSON (Phase 3)
  (default)      : Legacy mode — heuristic draft generation (deprecated for new domains)
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from pipeline.encoding_fix import fix_windows_encoding
from pipeline.shared import (
    CODE_BLOCK,
    FRONTMATTER,
    HEADING,
    INVALID_CHARS,
    get_one_sentence,
    parse_frontmatter,
    plain_text,
    resolve_vault,
    sanitize_filename,
    section_excerpt,
    split_sentences,
    validate_apply_json,
)


LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
RAW_SOURCE_PATTERN = re.compile(r'raw_source:\s*"\[\[([^\]]+)\]\]"')
INDEX_LINE = re.compile(r"^- \[\[([^|\]]+)\]\](?::\s*(.*))?$")
QUERY_LOG_PATTERN = re.compile(r"^## \[[^\]]+\] query(?:\(\w+\))? \| (.+)$", re.M)
INGEST_LOG_PATTERN = re.compile(r"^## \[[^\]]+\] ingest \| (.+)$", re.M)
FOLDER_WEIGHTS = {
    "syntheses": 8,
    "sources": 6,
    "briefs": 5,
    "domains": 4,
    "concepts": 1,
    "entities": 0,
}


@dataclass
class Candidate:
    ref: str
    path: Path
    score: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate draft recompilations from stale wiki signals.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--query", help="Specific question to recompile.")
    parser.add_argument("--source-title", help="Specific source title to recompile.")
    parser.add_argument("--top", type=int, default=1, help="How many top churn items to compile by default.")
    parser.add_argument("--collect-only", action="store_true", help="Collect vault signals as JSON for LLM analysis.")
    parser.add_argument("--apply", type=Path, dest="apply_json", help="Write delta-compile page from LLM result JSON.")
    parser.add_argument("--output", type=Path, help="Output path for --collect-only JSON.")
    return parser.parse_args()


def slugify(name: str) -> str:
    return f"{datetime.now().strftime('%Y-%m-%d--%H%M%S')}--{sanitize_filename(name, 64)}"


def outbound_links(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {match.strip() for match in LINK_PATTERN.findall(text)}


def page_title(path: Path) -> str:
    meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    return meta.get("title") or path.stem


def repeated_entries(log_text: str, pattern: re.Pattern[str]) -> Counter[str]:
    return Counter(match.group(1).strip() for match in pattern.finditer(log_text))


def top_queries(vault: Path, top: int) -> list[str]:
    log_text = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    ranked = repeated_entries(log_text, QUERY_LOG_PATTERN).most_common()
    return [item for item, count in ranked if count > 1][:top]


def top_sources(vault: Path, top: int) -> list[str]:
    log_text = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    ranked = repeated_entries(log_text, INGEST_LOG_PATTERN).most_common()
    return [item for item, count in ranked if count > 1][:top]


def load_index_candidates(vault: Path, query: str, top: int = 5) -> list[Candidate]:
    index_text = (vault / "wiki" / "index.md").read_text(encoding="utf-8")
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[一-鿿]{2,8}", query)
    candidates: list[Candidate] = []
    for raw_line in index_text.splitlines():
        line = raw_line.strip()
        match = INDEX_LINE.match(line)
        if not match:
            continue
        ref = match.group(1)
        if ref.startswith("outputs/"):
            continue
        folder = ref.split("/", 1)[0]
        path = (vault / "wiki" / f"{ref}.md") if not ref.startswith("raw/articles/") else (vault / f"{ref}.md")
        if not path.exists():
            continue
        haystack = f"{ref} {match.group(2) or ''}"
        score = 0
        for term in terms:
            if term in haystack:
                score += 3
            score += haystack.count(term)
        score += FOLDER_WEIGHTS.get(folder, 0)
        if score > 0:
            candidates.append(Candidate(ref=ref, path=path, score=score))
    return sorted(candidates, key=lambda item: item.score, reverse=True)[:top]


def dedupe_lines(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for item in items:
        item = item.strip()
        if not item or item in result:
            continue
        result.append(item)
        if len(result) >= limit:
            break
    return result


def linked_raw_path(path: Path, vault: Path) -> Path | None:
    text = path.read_text(encoding="utf-8")
    match = RAW_SOURCE_PATTERN.search(text)
    if not match:
        return None
    raw_path = vault / f"{match.group(1)}.md"
    return raw_path if raw_path.exists() else None


def linked_domain_refs(path: Path) -> list[str]:
    return sorted(link for link in outbound_links(path) if link.startswith("domains/"))


def synthesis_ref_for_domain(domain_ref: str) -> str:
    stem = domain_ref.split("/", 1)[1]
    return f"syntheses/{stem}--综合分析"


def collect_delta_data(vault: Path, query: str | None = None, source_title: str | None = None, top: int = 1) -> dict:
    """Phase 1: Collect vault signals for LLM delta analysis."""
    # Identify targets
    queries: list[str] = []
    source_titles: list[str] = []
    if query:
        queries = [query]
    elif source_title:
        source_titles = [source_title]
    else:
        queries = top_queries(vault, top)
        source_titles = top_sources(vault, top)

    # Collect query signals
    query_signals: list[dict] = []
    for q in queries:
        candidates = load_index_candidates(vault, q, top=5)
        query_signals.append({
            "query": q,
            "candidates": [
                {
                    "ref": c.ref,
                    "title": page_title(c.path),
                    "score": c.score,
                    "folder": c.ref.split("/", 1)[0],
                }
                for c in candidates
            ],
        })

    # Collect source signals
    source_signals: list[dict] = []
    for title in source_titles:
        source_path = None
        for path in (vault / "wiki" / "sources").glob("*.md"):
            if page_title(path) == title:
                source_path = path
                break
        if not source_path:
            continue
        meta, body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
        raw_path = linked_raw_path(source_path, vault)
        source_signals.append({
            "title": title,
            "slug": f"sources/{source_path.stem}",
            "quality": meta.get("quality", "unknown"),
            "core_summary": section_excerpt(body, "核心摘要")[:500],
            "has_raw": raw_path is not None,
            "raw_excerpt": plain_text(raw_path.read_text(encoding="utf-8"))[:500] if raw_path else "",
            "domains": linked_domain_refs(source_path),
        })

    return {
        "query_signals": query_signals,
        "source_signals": source_signals,
        "total_queries": len(queries),
        "total_sources": len(source_titles),
    }


def apply_delta_result(vault: Path, result_path: Path) -> list[str]:
    """Phase 3: Write delta-compile pages from LLM result."""
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validate_apply_json(result, ["drafts"], context="delta_compile")
    drafts = result.get("drafts", [])
    generated: list[str] = []

    for draft in drafts:
        draft_type = draft.get("type", "query")
        question = draft.get("question", "")
        source_title = draft.get("source_title", "")
        conclusion = draft.get("conclusion", "待补充。")
        key_points = draft.get("key_points", [])
        evidence_refs = draft.get("evidence_refs", [])
        reasoning = draft.get("reasoning", "")

        if draft_type == "query":
            slug = slugify(f"delta-query-{question}")
            title = f"{question} | Delta Compile 草稿"
        else:
            slug = slugify(f"delta-source-{source_title}")
            title = f"{source_title} | Delta Compile 草稿"

        lines = [
            "---",
            f'title: "{title}"',
            'type: "delta-compile"',
            'status: "review-needed"',
            'graph_role: "working"',
            'graph_include: "false"',
            'lifecycle: "review-needed"',
            f'created_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
            'analysis_method: "llm-driven"',
            "---",
            "",
            f"# {title}",
            "",
            "## 建议替换的一句话结论",
            "",
            conclusion,
            "",
            "## 关键要点",
            "",
        ]
        for point in key_points:
            lines.append(f"- {point}")
        lines.extend(["", "## 使用证据", ""])
        for ref in evidence_refs:
            lines.append(f"- [[{ref}]]")
        if reasoning:
            lines.extend(["", "## 分析理由", "", reasoning])
        lines.append("")

        page_path = vault / "wiki" / "outputs" / f"{slug}.md"
        page_path.write_text("\n".join(lines), encoding="utf-8")

        # Append to log
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_lines = [
            f"## [{timestamp}] delta_compile | {question or source_title}",
            "",
            f"- output: [[outputs/{slug}]]",
            "",
        ]
        with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
            fh.write("\n".join(log_lines))

        generated.append(str(page_path))

    # Rebuild index
    _rebuild_index(vault)
    return generated


def _rebuild_index(vault: Path) -> None:
    """Rebuild wiki/index.md."""
    sections = [
        ("Sources", "sources"), ("Briefs", "briefs"), ("Concepts", "concepts"),
        ("Entities", "entities"), ("Domains", "domains"), ("Syntheses", "syntheses"),
        ("Outputs", "outputs"),
    ]
    lines = [
        "---", 'title: "Wiki Index"', 'type: "system-index"',
        'graph_role: "system"', 'graph_include: "false"', 'lifecycle: "canonical"',
        "---", "", "# Wiki Index", "", "> 先扫描本页，再按需打开相关页面。", "",
    ]
    for title, folder in sections:
        lines.extend([f"## {title}", ""])
        files = sorted((vault / "wiki" / folder).glob("*.md"))
        if not files:
            lines.extend(["- （空）", ""])
            continue
        for file in files:
            meta, body = parse_frontmatter(file.read_text(encoding="utf-8"))
            if folder == "outputs" and meta.get("lifecycle") == "absorbed":
                continue
            if meta.get("type") == "source":
                summary = section_excerpt(body, "核心摘要")
            elif meta.get("type") == "brief":
                summary = get_one_sentence(meta, body)
            elif meta.get("type") in {"output", "delta-compile"}:
                summary = section_excerpt(body, "建议回答") or section_excerpt(body, "回答")
            else:
                summary = plain_text(body)[:240]
            lines.append(f"- [[{folder}/{file.stem}]]: {summary or '待补充摘要'}")
        lines.append("")
    (vault / "wiki" / "index.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    if args.apply_json:
        generated = apply_delta_result(vault, args.apply_json)
        print(json.dumps({"generated": generated}, ensure_ascii=False, indent=2))
        return 0

    if args.collect_only:
        data = collect_delta_data(vault, query=args.query, source_title=args.source_title, top=args.top)
        output = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Delta data written to {args.output}")
        else:
            print(output)
        return 0

    # Legacy mode: heuristic delta generation
    # NOTE: This mode uses legacy sentence selection. For new domains,
    # use --collect-only → LLM → --apply instead.
    from delta_compile_legacy import build_query_delta_legacy, build_source_delta_legacy

    generated: list[str] = []
    query_targets = [args.query] if args.query else ([] if args.source_title else top_queries(vault, args.top))
    source_targets = [args.source_title] if args.source_title else ([] if args.query else top_sources(vault, args.top))

    for question in query_targets:
        slug, page = build_query_delta_legacy(vault, question)
        (vault / "wiki" / "outputs" / f"{slug}.md").write_text(page, encoding="utf-8")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
            fh.write(f"## [{timestamp}] delta_compile | {question}\n\n- output: [[outputs/{slug}]]\n\n")
        generated.append(str(vault / "wiki" / "outputs" / f"{slug}.md"))

    for source_title in source_targets:
        slug, page = build_source_delta_legacy(vault, source_title)
        (vault / "wiki" / "outputs" / f"{slug}.md").write_text(page, encoding="utf-8")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
            fh.write(f"## [{timestamp}] delta_compile | {source_title}\n\n- output: [[outputs/{slug}]]\n\n")
        generated.append(str(vault / "wiki" / "outputs" / f"{slug}.md"))

    _rebuild_index(vault)
    print(json.dumps({"generated": generated, "mode": "legacy"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
