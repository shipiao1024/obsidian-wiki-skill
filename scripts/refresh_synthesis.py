#!/usr/bin/env python
"""Rebuild synthesis pages from linked sources in the local Obsidian LLM wiki."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
RAW_SOURCE_PATTERN = re.compile(r'raw_source:\s*"\[\[([^\]]+)\]\]"')
NOISE_PATTERNS = (
    "系列导读",
    "上一篇",
    "开场",
    "那个工程师写下的一行笔记",
    "广泛流传的感受",
    "接下来这个",
    "下一篇",
    "待补充",
    "待后续",
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
    "集中",
    "分工",
    "取消分工",
)
RAW_SECTION_HEADINGS = (
    "第一幕：AIDV 和 SDV 的根本区别在哪里",
    "这个区别在工程上意味着什么",
    "从 EEA 的视角看：为什么 E2E 逼出了中央计算",
    "E2E 架构的工程本质",
    "一个被低估的工程优势：推理延迟",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh synthesis pages from current linked sources.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--domain", help="Specific domain name, such as 自动驾驶.")
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
    if "raw/assets/" in sentence or "相关主题域" in sentence or "来自来源" in sentence:
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


def synthesis_sources(vault: Path, synthesis_path: Path) -> list[Path]:
    refs = sorted(link for link in outbound_links(synthesis_path) if link.startswith("sources/"))
    return [vault / "wiki" / f"{ref}.md" for ref in refs if (vault / "wiki" / f"{ref}.md").exists()]


def synthesis_concepts(source_paths: list[Path]) -> list[str]:
    concepts: list[str] = []
    for path in source_paths:
        concepts.extend(link for link in outbound_links(path) if link.startswith("concepts/"))
    return dedupe_lines(concepts, 8)


def build_synthesis_page(vault: Path, synthesis_path: Path) -> str:
    meta, _ = parse_frontmatter(synthesis_path.read_text(encoding="utf-8"))
    domain = meta.get("domain") or synthesis_path.stem.replace("--综合分析", "")
    source_paths = synthesis_sources(vault, synthesis_path)
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[\u4e00-\u9fff]{2,8}", domain)

    evidence: list[str] = []
    for source_path in source_paths:
        source_meta, source_body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
        evidence.extend(split_sentences(section_excerpt(source_body, "核心摘要")))
        raw_path = linked_raw_path(source_path, vault)
        if raw_path:
            evidence.extend(preferred_raw_sentences(raw_path.read_text(encoding="utf-8")))

    selected = select_sentences(evidence, terms, 8)
    lead = compress_lead(selected)
    concepts = synthesis_concepts(source_paths)

    lines = [
        "---",
        f'title: "{domain} 综合分析"',
        'type: "synthesis"',
        'status: "draft"',
        'graph_role: "knowledge"',
        'graph_include: "true"',
        'lifecycle: "official"',
        f'domain: "{domain}"',
        f'updated_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
        "---",
        "",
        f"# {domain} 综合分析",
        "",
        "## 当前结论",
        "",
        lead,
        "",
        "## 核心判断",
        "",
    ]
    lines.extend(f"- {item}" for item in selected[:4])
    lines.extend(
        [
            "",
            "## 近期来源",
            "",
        ]
    )
    lines.extend(f"- [[sources/{path.stem}]]" for path in source_paths)
    lines.extend(
        [
            "",
            "## 相关概念",
            "",
        ]
    )
    lines.extend((f"- [[{item}]]" for item in concepts),)
    if not concepts:
        lines.append("- 待补充。")
    lines.extend(
        [
            "",
            "## 待验证 / 后续维护",
            "",
        ]
    )
    if len(source_paths) <= 1:
        lines.append("- 当前主要基于单一来源，后续需要更多来源补充冲突、边界和反例。")
    else:
        lines.append("- 新来源进入该主题域时，优先检查结论是否被强化、修正或推翻。")
        lines.append("- 如果不同来源给出不同判断，应补一节“冲突与边界”。")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    targets = []
    if args.domain:
        target = vault / "wiki" / "syntheses" / f"{args.domain}--综合分析.md"
        if not target.exists():
            raise SystemExit(f"Synthesis page not found for domain: {args.domain}")
        targets.append(target)
    else:
        targets = sorted((vault / "wiki" / "syntheses").glob("*.md"))

    updated: list[str] = []
    for path in targets:
        path.write_text(build_synthesis_page(vault, path), encoding="utf-8")
        updated.append(str(path))

    print(json.dumps({"updated": updated}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
