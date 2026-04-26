#!/usr/bin/env python
"""Generate review-ready recompilation drafts from stale/high-churn wiki signals."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
RAW_SOURCE_PATTERN = re.compile(r'raw_source:\s*"\[\[([^\]]+)\]\]"')
INDEX_LINE = re.compile(r"^- \[\[([^|\]]+)\]\](?::\s*(.*))?$")
INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n]+')
QUERY_LOG_PATTERN = re.compile(r"^## \[[^\]]+\] query(?:\(\w+\))? \| (.+)$", re.M)
INGEST_LOG_PATTERN = re.compile(r"^## \[[^\]]+\] ingest \| (.+)$", re.M)
NOISE_PATTERNS = (
    "系列导读",
    "上一篇",
    "开场",
    "那个工程师写下的一行笔记",
    "广泛流传的感受",
    "本文要做的是一次分类",
    "下一篇",
    "接下来这个",
    "这句话，精确地概括了",
    "车绕过了一辆",
    "早期测试者们反复报告了类似的场景",
    "待补充",
    "待后续",
    "说明",
)
PREFERRED_PATTERNS = (
    "根本",
    "意味着",
    "核心",
    "直接",
    "推动",
    "区别",
    "架构",
    "AIDV",
    "EEA",
    "SDV",
    "端到端",
    "冲击",
    "影响",
    "集中",
    "分工",
    "取消分工",
)
FOLDER_WEIGHTS = {
    "syntheses": 8,
    "sources": 6,
    "briefs": 5,
    "domains": 4,
    "concepts": 1,
    "entities": 0,
}
RAW_SECTION_HEADINGS = (
    "第一幕：AIDV 和 SDV 的根本区别在哪里",
    "这个区别在工程上意味着什么",
    "从 EEA 的视角看：为什么 E2E 逼出了中央计算",
    "E2E 架构的工程本质",
    "一个被低估的工程优势：推理延迟",
)


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


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", text)
    return [part.strip() for part in parts if len(part.strip()) >= 14]


def normalize_sentence(sentence: str) -> str:
    sentence = sentence.replace("\\ \\ ", " ").replace('\\"', '"')
    sentence = re.sub(r"^[^：]{2,20}：", "", sentence)
    sentence = re.sub(r"\s+", " ", sentence).strip()
    sentence = sentence.strip(' -"\'')
    return sentence


def is_noise_sentence(sentence: str) -> bool:
    if len(sentence) < 18:
        return True
    if any(pattern in sentence for pattern in NOISE_PATTERNS):
        return True
    if "raw/assets/" in sentence:
        return True
    if "相关主题域" in sentence or "来自来源" in sentence:
        return True
    if sentence.count("：") >= 2:
        return True
    return False


def score_sentence(sentence: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        if term and term in sentence:
            score += 4
            score += sentence.count(term)
    for pattern in PREFERRED_PATTERNS:
        if pattern in sentence:
            score += 2
    if "。" in sentence or "；" in sentence:
        score += 1
    return score


def select_sentences(sentences: list[str], terms: list[str], limit: int) -> list[str]:
    cleaned = [normalize_sentence(item) for item in sentences]
    filtered = [item for item in cleaned if not is_noise_sentence(item)]
    ranked = sorted(filtered, key=lambda item: score_sentence(item, terms), reverse=True)
    return dedupe_lines(ranked or cleaned, limit)


def compress_lead(sentences: list[str]) -> str:
    picked = [normalize_sentence(item).rstrip("。") for item in sentences[:2] if item]
    if not picked:
        return "待补充。"
    if len(picked) == 1:
        return picked[0] + "。"
    return f"{picked[0]}；{picked[1]}。"


def sanitize_filename(name: str, max_length: int = 96) -> str:
    name = INVALID_CHARS.sub("_", name.strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return (name[:max_length].rstrip("_. ") or "untitled")


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
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[\u4e00-\u9fff]{2,8}", query)
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


def raw_section_excerpt(raw_markdown: str, heading: str) -> str:
    pattern = re.compile(rf"##+\s+{re.escape(heading)}\s*\n(.*?)(?:\n##+\s+|\Z)", re.S)
    match = pattern.search(raw_markdown)
    if not match:
        return ""
    return plain_text(match.group(1)).strip()


def preferred_raw_sentences(raw_markdown: str) -> list[str]:
    sentences: list[str] = []
    for heading in RAW_SECTION_HEADINGS:
        excerpt = raw_section_excerpt(raw_markdown, heading)
        if excerpt:
            sentences.extend(split_sentences(excerpt))
    if sentences:
        return sentences
    return split_sentences(plain_text(raw_markdown))


def build_query_delta(vault: Path, question: str) -> tuple[str, str]:
    candidates = load_index_candidates(vault, question, top=5)
    evidence: list[str] = []
    source_refs: list[str] = []
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[\u4e00-\u9fff]{2,8}", question)
    preferred_candidates = [
        candidate for candidate in candidates
        if candidate.ref.startswith(("syntheses/", "sources/", "briefs/", "domains/"))
    ] or candidates
    for candidate in preferred_candidates[:3]:
        meta, body = parse_frontmatter(candidate.path.read_text(encoding="utf-8"))
        page_type = meta.get("type", "")
        if page_type == "source":
            evidence.extend(split_sentences(section_excerpt(body, "核心摘要")))
            for domain_ref in linked_domain_refs(candidate.path):
                synthesis_ref = synthesis_ref_for_domain(domain_ref)
                synthesis_path = vault / "wiki" / f"{synthesis_ref}.md"
                if synthesis_path.exists():
                    synth_meta, synth_body = parse_frontmatter(synthesis_path.read_text(encoding="utf-8"))
                    evidence.extend(split_sentences(section_excerpt(synth_body, "当前结论")))
                    source_refs.append(synthesis_ref)
                source_refs.append(domain_ref)
        elif page_type == "brief":
            evidence.extend(split_sentences(section_excerpt(body, "一句话结论")))
            evidence.extend(split_sentences(section_excerpt(body, "核心要点")))
        elif page_type == "synthesis":
            evidence.extend(split_sentences(section_excerpt(body, "当前结论")))
        else:
            evidence.extend(split_sentences(plain_text(body)[:400]))
        if candidate.ref.startswith("sources/"):
            source_refs.append(candidate.ref)
        raw_path = linked_raw_path(candidate.path, vault)
        if raw_path is not None:
            evidence.extend(preferred_raw_sentences(raw_path.read_text(encoding="utf-8")))
            source_refs.append(f"raw/articles/{raw_path.stem}")

    bullets = select_sentences(evidence, terms, limit=5)
    answer_lead = compress_lead(bullets)
    answer_lines = [
        "## 建议回答",
        "",
        answer_lead,
        "",
        "## 支撑要点",
        "",
        *(f"- {line}" for line in bullets[:3]),
        "",
        "## 建议沉淀",
        "",
        "- 如果这个问题继续高频出现，建议把这组结论提升为正式 `syntheses/` 页面段落。",
        "",
        "## 使用证据",
        "",
        *(f"- [[{ref}]]" for ref in dedupe_lines(source_refs, limit=8)),
        "",
    ]
    page = "\n".join(
        [
            "---",
            f'title: "{question} | Delta Compile 草稿"',
            'type: "delta-compile"',
            'status: "review-needed"',
            'graph_role: "working"',
            'graph_include: "false"',
            'lifecycle: "review-needed"',
            f'question: "{question}"',
            f'created_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
            "---",
            "",
            f"# {question} | Delta Compile 草稿",
            "",
            "## 背景",
            "",
            "- 该问题在 `wiki/log.md` 中重复出现，说明已经具备沉淀价值。",
            "",
            *answer_lines,
        ]
    )
    return slugify(f"delta-query-{question}"), page


def find_source_page_by_title(vault: Path, source_title: str) -> Path | None:
    for path in (vault / "wiki" / "sources").glob("*.md"):
        if page_title(path) == source_title:
            return path
    return None


def build_source_delta(vault: Path, source_title: str) -> tuple[str, str]:
    source_path = find_source_page_by_title(vault, source_title)
    if source_path is None:
        raise SystemExit(f"Source page not found for title: {source_title}")
    source_text = source_path.read_text(encoding="utf-8")
    source_meta, source_body = parse_frontmatter(source_text)
    raw_path = linked_raw_path(source_path, vault)
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path else ""
    source_summary = split_sentences(section_excerpt(source_body, "核心摘要"))
    raw_sentences = preferred_raw_sentences(raw_markdown) if raw_markdown else []
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[\u4e00-\u9fff]{2,8}", source_title)
    merged = select_sentences(source_summary + raw_sentences, terms, limit=8)
    lead = compress_lead(merged)
    brief_bullets = merged[:5]

    page = "\n".join(
        [
            "---",
            f'title: "{source_title} | Delta Compile 草稿"',
            'type: "delta-compile"',
            'status: "review-needed"',
            'graph_role: "working"',
            'graph_include: "false"',
            'lifecycle: "review-needed"',
            f'source_page: "[[sources/{source_path.stem}]]"',
            f'raw_source: "[[raw/articles/{raw_path.stem}]]"' if raw_path else 'raw_source: ""',
            f'created_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
            "---",
            "",
            f"# {source_title} | Delta Compile 草稿",
            "",
            "## 建议替换的一句话结论",
            "",
            lead,
            "",
            "## 建议替换的快读要点",
            "",
            *(f"- {line}" for line in brief_bullets),
            "",
            "## 建议替换的来源摘要",
            "",
            *(f"- {line}" for line in merged[:6]),
            "",
            "## 使用证据",
            "",
            f"- [[sources/{source_path.stem}]]",
            *( [f"- [[raw/articles/{raw_path.stem}]]"] if raw_path else [] ),
            "",
            "## 说明",
            "",
            "- 该来源在 `wiki/log.md` 中被重复 ingest，说明当前页面正在频繁迭代，适合人工确认后正式回写。",
            "",
        ]
    )
    return slugify(f"delta-source-{source_path.stem}"), page


def rebuild_index(vault: Path) -> None:
    sections = [
        ("Sources", "sources"),
        ("Briefs", "briefs"),
        ("Concepts", "concepts"),
        ("Entities", "entities"),
        ("Domains", "domains"),
        ("Syntheses", "syntheses"),
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
            meta, body = parse_frontmatter(file.read_text(encoding="utf-8"))
            if folder == "outputs" and meta.get("lifecycle") == "absorbed":
                continue
            if meta.get("type") in {"source"}:
                summary = section_excerpt(body, "核心摘要")
            elif meta.get("type") in {"brief"}:
                summary = section_excerpt(body, "一句话结论")
            elif meta.get("type") in {"output", "delta-compile"}:
                summary = section_excerpt(body, "建议回答") or section_excerpt(body, "回答")
            else:
                summary = plain_text(body)[:240]
            lines.append(f"- [[{folder}/{file.stem}]]: {summary or '待补充摘要'}")
        lines.append("")
    (vault / "wiki" / "index.md").write_text("\n".join(lines), encoding="utf-8")


def append_log(vault: Path, label: str, output_slug: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## [{timestamp}] delta_compile | {label}",
        "",
        f"- output: [[outputs/{output_slug}]]",
        "",
    ]
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    generated: list[str] = []
    query_targets = [args.query] if args.query else ([] if args.source_title else top_queries(vault, args.top))
    source_targets = [args.source_title] if args.source_title else ([] if args.query else top_sources(vault, args.top))

    for question in query_targets:
        slug, page = build_query_delta(vault, question)
        (vault / "wiki" / "outputs" / f"{slug}.md").write_text(page, encoding="utf-8")
        append_log(vault, question, slug)
        generated.append(str(vault / "wiki" / "outputs" / f"{slug}.md"))

    for source_title in source_targets:
        slug, page = build_source_delta(vault, source_title)
        (vault / "wiki" / "outputs" / f"{slug}.md").write_text(page, encoding="utf-8")
        append_log(vault, source_title, slug)
        generated.append(str(vault / "wiki" / "outputs" / f"{slug}.md"))

    rebuild_index(vault)
    print(json.dumps({"generated": generated}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
