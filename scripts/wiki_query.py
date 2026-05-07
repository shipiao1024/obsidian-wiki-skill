#!/usr/bin/env python
"""Query the local Obsidian LLM wiki and write answers back to wiki/outputs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.encoding_fix import fix_windows_encoding
from pipeline.output import VALID_MODES, build_mode_output
from pipeline.shared import resolve_vault
from pipeline.text_utils import get_one_sentence


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n]+')
INDEX_LINE = re.compile(r"^- \[\[([^|\]]+)\]\](?::\s*(.*))?$")
RAW_LINK_PATTERN = re.compile(r'raw_source:\s*"\[\[([^\]]+)\]\]"')

HIGH_PRECISION_PATTERNS = [
    r"\d",
    r"多少",
    r"几",
    r"哪年",
    r"何时",
    r"什么时候",
    r"日期",
    r"时间",
    r"引用",
    r"原话",
    r"作者",
    r"立场",
    r"定义",
]


@dataclass
class Candidate:
    ref: str
    path: Path
    score: int
    summary: str


FOLDER_WEIGHTS = {
    "briefs": 8,
    "sources": 6,
    "concepts": 5,
    "stances": 4,
    "syntheses": 4,
    "domains": 3,
    "comparisons": 3,
    "entities": 3,
    "questions": 2,
    "outputs": -10,
}

MIN_RELEVANCE_SCORE = 4


def sanitize_filename(name: str, max_length: int = 96) -> str:
    name = INVALID_CHARS.sub("_", name.strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return (name[:max_length].rstrip("_. ") or "untitled")


def slugify_query(question: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d--%H%M%S")
    return f"{timestamp}--{sanitize_filename(question, max_length=48)}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the Obsidian LLM wiki and write back outputs.")
    parser.add_argument("question", help="Natural-language question to answer from the local wiki.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--top", type=int, default=5, help="Number of candidate pages to read.")
    parser.add_argument("--no-writeback", action="store_true", help="Do not write a result page to wiki/outputs.")
    parser.add_argument("--mode", default="auto", choices=VALID_MODES, help="Output mode (default: auto — auto-detected from question).")
    parser.add_argument("--digest-type", default="deep", choices=("deep", "compare", "timeline"), help="Digest sub-type override (default: deep).")
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
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
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


def query_terms(question: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[\u4e00-\u9fff]{2,8}", question)
    stopwords = {"什么", "怎么", "如何", "这个", "这篇", "文章", "一下", "一个", "是否", "以及", "关于"}
    deduped: list[str] = []
    for term in terms:
        if term in stopwords:
            continue
        if term not in deduped:
            deduped.append(term)
    return deduped or [question.strip()]


def score_text(text: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        if term in text:
            score += 3
        score += text.count(term)
    return score


def load_index_candidates(vault: Path, question: str) -> list[Candidate]:
    index_path = vault / "wiki" / "index.md"
    text = index_path.read_text(encoding="utf-8")
    terms = query_terms(question)
    candidates: list[Candidate] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = INDEX_LINE.match(line)
        if not match:
            continue
        ref = match.group(1)
        summary = match.group(2) or ""
        folder = ref.split("/", 1)[0]
        if folder == "outputs":
            continue
        path = vault / f"wiki/{ref}.md"
        if ref.startswith("raw/articles/"):
            path = vault / f"{ref}.md"
        if not path.exists():
            continue
        score = score_text(ref, terms) * 2 + score_text(summary, terms) + FOLDER_WEIGHTS.get(folder, 0)
        if score <= 0:
            continue
        candidates.append(Candidate(ref=ref, path=path, score=score, summary=summary))
    return sorted(candidates, key=lambda item: item.score, reverse=True)


def needs_raw_lookup(question: str) -> bool:
    return any(re.search(pattern, question, re.I) for pattern in HIGH_PRECISION_PATTERNS)


def linked_raw_path(vault: Path, path: Path) -> Path | None:
    text = path.read_text(encoding="utf-8")
    match = RAW_LINK_PATTERN.search(text)
    if not match:
        return None
    ref = match.group(1)
    raw_path = vault / f"{ref}.md"
    return raw_path if raw_path.exists() else None


def prioritized_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    page_type = meta.get("type", "")
    prioritized: list[str] = []
    if page_type == "source":
        prioritized.extend(
            [
                section_excerpt(body, "核心摘要"),
                section_excerpt(body, "与现有知识库的关系"),
                section_excerpt(body, "主题域"),
            ]
        )
    elif page_type == "brief":
        prioritized.extend(
            [
                get_one_sentence(meta, body),
                section_excerpt(body, "骨架") or section_excerpt(body, "数据") or section_excerpt(body, "核心要点"),
                section_excerpt(body, "关键判断"),
                section_excerpt(body, "跨域联想"),
                section_excerpt(body, "值得回看"),
            ]
        )
    elif page_type == "concept":
        prioritized.extend(
            [
                section_excerpt(body, "定义"),
                section_excerpt(body, "当前判断"),
                section_excerpt(body, "证据链"),
                section_excerpt(body, "跨域联想"),
            ]
        )
    elif page_type == "stance":
        prioritized.extend(
            [
                section_excerpt(body, "核心判断"),
                section_excerpt(body, "支持证据"),
                section_excerpt(body, "反对证据（steel-man）"),
            ]
        )
    elif page_type == "synthesis":
        prioritized.extend(
            [
                section_excerpt(body, "当前结论"),
                section_excerpt(body, "证据链"),
                section_excerpt(body, "立场追踪"),
                section_excerpt(body, "近期来源"),
            ]
        )
    elif page_type == "output":
        prioritized.append(section_excerpt(body, "回答"))
    if not any(prioritized):
        prioritized.append(plain_text(body))
    return "\n".join(item for item in prioritized if item).strip()


def read_candidate_excerpt(path: Path, question: str, limit: int = 3) -> list[str]:
    text = prioritized_text(path)
    pieces = re.split(r"(?<=[。！？!?；;])\s*", text)
    terms = query_terms(question)
    ranked = sorted(
        (piece.strip() for piece in pieces if len(piece.strip()) >= 18),
        key=lambda piece: score_text(piece, terms),
        reverse=True,
    )
    excerpts: list[str] = []
    for piece in ranked:
        if score_text(piece, terms) <= 0:
            continue
        if piece not in excerpts:
            excerpts.append(piece)
        if len(excerpts) >= limit:
            break
    if excerpts:
        return excerpts
    return ranked[:limit] or [text[:240]]


def candidate_title(path: Path) -> str:
    meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    return meta.get("title") or path.stem


def select_candidates(vault: Path, question: str, top: int) -> list[Candidate]:
    ranked = load_index_candidates(vault, question)
    if ranked:
        # Boost mature/evergreen pages by reading their frontmatter status
        for candidate in ranked:
            if candidate.path.exists():
                text = candidate.path.read_text(encoding="utf-8")
                match = FRONTMATTER.match(text)
                if match:
                    fm = match.group(1)
                    status_match = re.search(r'status:\s*"(\w+)"', fm)
                    if status_match:
                        status = status_match.group(1)
                        if status in ("mature", "evergreen"):
                            candidate.score += 2
                        elif status == "developing":
                            candidate.score += 1
        return sorted(ranked, key=lambda item: item.score, reverse=True)[:top]

    fallback: list[Candidate] = []
    terms = query_terms(question)
    for folder in ["briefs", "sources", "concepts", "stances", "entities", "domains", "comparisons", "syntheses"]:
        for path in (vault / "wiki" / folder).glob("*.md"):
            text = plain_text(path.read_text(encoding="utf-8"))
            score = score_text(path.stem, terms) * 2 + score_text(text[:1200], terms) + FOLDER_WEIGHTS.get(folder, 0)
            if score >= MIN_RELEVANCE_SCORE:
                fallback.append(Candidate(ref=f"{folder}/{path.stem}", path=path, score=score, summary=text[:180]))
    return sorted(fallback, key=lambda item: item.score, reverse=True)[:top]


def build_answer(question: str, candidates: list[Candidate], raw_paths: list[Path]) -> str:
    lines = [
        f"问题：{question}",
        "",
        "结论：",
    ]
    if not candidates:
        lines.append("当前知识库中没有命中足够相关的页面，建议先补充来源或改写问题。")
        return "\n".join(lines)

    first = candidates[0]
    top_excerpt = read_candidate_excerpt(first.path, question, limit=2)
    lines.extend(f"- {item}" for item in top_excerpt)

    if len(candidates) > 1:
        lines.extend(["", "补充依据："])
        for candidate in candidates[1:3]:
            excerpts = read_candidate_excerpt(candidate.path, question, limit=1)
            lines.append(f"- {candidate_title(candidate.path)}：{excerpts[0]}")

    if raw_paths:
        lines.extend(["", "原文核对："])
        for raw_path in raw_paths[:2]:
            excerpts = read_candidate_excerpt(raw_path, question, limit=1)
            lines.append(f"- {raw_path.stem}：{excerpts[0]}")

    return "\n".join(lines)


def build_output_page(question: str, answer: str, candidates: list[Candidate], raw_paths: list[Path], slug: str, mode: str = "brief") -> str:
    lines = [
        "---",
        f'title: "{question}"',
        'type: "output"',
        'status: "draft"',
        'graph_role: "working"',
        'graph_include: "false"',
        'lifecycle: "temporary"',
        f'slug: "{slug}"',
        f'mode: "{mode}"',
        f'created_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
        "---",
        "",
        f"# {question}",
        "",
        "## 回答",
        "",
        answer,
        "",
        "## 使用页面",
        "",
    ]
    lines.extend(f"- [[{candidate.ref}]]" for candidate in candidates)
    if raw_paths:
        lines.extend(["", "## 原文核对", ""])
        lines.extend(f"- [[raw/articles/{path.stem}]]" for path in raw_paths)
    lines.append("")
    return "\n".join(lines)


def rebuild_index(vault: Path) -> None:
    sections = [
        ("Sources", "sources"),
        ("Briefs", "briefs"),
        ("Concepts", "concepts"),
        ("Entities", "entities"),
        ("Domains", "domains"),
        ("Syntheses", "syntheses"),
        ("Comparisons", "comparisons"),
        ("Outputs", "outputs"),
    ]
    lines = [
        "---",
        'title: "Wiki Index"',
        'type: "system-index"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        "---",
        "",
        "# Wiki Index",
        "",
        "> 先扫描本页，再按需打开相关页面。",
        "",
    ]
    for title, folder in sections:
        lines.extend([f"## {title}", ""])
        files = sorted((vault / "wiki" / folder).glob("*.md"))
        if not files:
            lines.extend(["- （空）", ""])
            continue
        for file in files:
            text = file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if folder == "outputs" and meta.get("lifecycle") == "absorbed":
                continue
            page_type = meta.get("type", "")
            if page_type == "source":
                summary = section_excerpt(body, "核心摘要")
            elif page_type == "brief":
                summary = get_one_sentence(meta, body)
            elif page_type == "output":
                summary = section_excerpt(body, "回答")
            else:
                summary = plain_text(body)[:240].strip()
            lines.append(f"- [[{folder}/{file.stem}]]: {summary or '待补充摘要'}")
        lines.append("")
    (vault / "wiki" / "index.md").write_text("\n".join(lines), encoding="utf-8")


def append_query_log(vault: Path, question: str, output_slug: str | None, mode: str = "brief") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## [{timestamp}] query({mode}) | {question}",
        "",
    ]
    if output_slug:
        lines.append(f"- output: [[outputs/{output_slug}]]")
    else:
        lines.append("- output: skipped")
    lines.extend(["", ""])
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def update_hot_cache_query(vault: Path, question: str, mode: str) -> None:
    """Append query summary to wiki/hot.md Recent Queries section."""
    hot_path = vault / "wiki" / "hot.md"
    if not hot_path.exists():
        return
    text = hot_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_line = f"- [{timestamp}] query({mode}) {question}"
    # Merge into existing section, preserving prior entries
    pattern = re.compile(rf"(##\s+{re.escape('Recent Queries')}\s*\n)(.*?)(?=\n##\s+|\Z)", re.S)
    match = pattern.search(body)
    if match:
        current_body = match.group(2)
        current_links = set(re.findall(r"\- \[.*?\]", current_body))
        merged = list(current_links)
        merged.append(new_line)
        replacement = match.group(1) + ("\n".join(merged[-5:] or ["- （空）"])) + "\n"
        updated = body[:match.start()] + replacement + body[match.end():]
    else:
        updated = body.rstrip() + "\n\n## Recent Queries\n\n" + new_line + "\n"
    meta_lines = "---\n" + "\n".join(f'{k}: "{v}"' for k, v in meta.items()) + "\n---\n\n"
    hot_path.write_text(meta_lines + updated, encoding="utf-8")


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    question = args.question.strip()

    # --- Read hot cache for recent context ---
    hot_path = vault / "wiki" / "hot.md"
    hot_context = ""
    if hot_path.exists():
        _, hot_body = parse_frontmatter(hot_path.read_text(encoding="utf-8"))
        hot_context = plain_text(hot_body)[:500]

    candidates = select_candidates(vault, question, args.top)
    mode = args.mode

    raw_paths: list[Path] = []
    if needs_raw_lookup(question):
        seen: set[Path] = set()
        for candidate in candidates:
            raw_path = linked_raw_path(vault, candidate.path)
            if raw_path and raw_path not in seen:
                seen.add(raw_path)
                raw_paths.append(raw_path)

    answer, routing_info = build_mode_output(
        mode=mode,
        vault=vault,
        question=question,
        candidates=candidates,
        raw_paths=raw_paths,
        build_answer_fn=build_answer,
        digest_type=args.digest_type,
    )
    if hot_context:
        answer = f"## 近期知识库动态\n\n{hot_context}\n\n---\n\n{answer}"

    resolved_mode = routing_info.get("resolved_mode", mode)
    output_path: Path | None = None
    output_slug: str | None = None
    if not args.no_writeback:
        output_slug = slugify_query(question)
        output_path = vault / "wiki" / "outputs" / f"{output_slug}.md"
        output_page = build_output_page(question, answer, candidates, raw_paths, output_slug, mode=resolved_mode)
        output_path.write_text(output_page, encoding="utf-8")
        rebuild_index(vault)
    append_query_log(vault, question, output_slug, mode=resolved_mode)
    update_hot_cache_query(vault, question, resolved_mode)

    print(
        json.dumps(
            {
                "question": question,
                "mode": resolved_mode,
                "auto_routed": routing_info.get("auto_routed", "false"),
                "entry_layer": routing_info.get("entry_layer", "ask"),
                "answer": answer,
                "used_pages": [candidate.ref for candidate in candidates],
                "used_raw_pages": [str(path) for path in raw_paths],
                "output": str(output_path) if output_path else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
