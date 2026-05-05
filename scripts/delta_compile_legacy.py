#!/usr/bin/env python
"""Legacy heuristic delta-compile builders (deprecated).

This module preserves the old domain-specific heuristic delta generation logic
for backward compatibility. New domains should use the three-stage
--collect-only → LLM → --apply workflow in delta_compile.py.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from pipeline.shared import get_one_sentence

# Domain-specific patterns (自动驾驶 domain only)
NOISE_PATTERNS = (
    "系列导读", "上一篇", "开场", "那个工程师写下的一行笔记",
    "广泛流传的感受", "本文要做的是一次分类", "下一篇", "接下来这个",
    "这句话，精确地概括了", "车绕过了一辆", "早期测试者们反复报告了类似的场景",
    "待补充", "待后续", "说明",
)
PREFERRED_PATTERNS = (
    "根本", "意味着", "核心", "直接", "推动", "区别", "架构",
    "AIDV", "EEA", "SDV", "端到端", "冲击", "影响", "集中", "分工", "取消分工",
)
RAW_SECTION_HEADINGS = (
    "第一幕：AIDV 和 SDV 的根本区别在哪里",
    "这个区别在工程上意味着什么",
    "从 EEA 的视角看：为什么 E2E 逼出了中央计算",
    "E2E 架构的工程本质",
    "一个被低估的工程优势：推理延迟",
)

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
RAW_SOURCE_PATTERN = re.compile(r'raw_source:\s*"\[\[([^\]]+)\]\]"')
INDEX_LINE = re.compile(r"^- \[\[([^|\]]+)\]\](?::\s*(.*))?$")
INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n]+')
FOLDER_WEIGHTS = {"syntheses": 8, "sources": 6, "briefs": 5, "domains": 4, "concepts": 1, "entities": 0}


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
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


def _plain_text(md: str) -> str:
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


def _section_excerpt(body: str, heading: str) -> str:
    pattern = re.compile(rf"##\s+{re.escape(heading)}\s*\n(.*?)(?:\n##\s+|\Z)", re.S)
    match = pattern.search(body)
    if not match:
        return ""
    return _plain_text(match.group(1)).strip()


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", text)
    return [part.strip() for part in parts if len(part.strip()) >= 14]


def _normalize_sentence(sentence: str) -> str:
    sentence = sentence.replace("\\ \\ ", " ").replace('\\"', '"')
    sentence = re.sub(r"^[^：]{2,20}：", "", sentence)
    sentence = re.sub(r"\s+", " ", sentence).strip()
    return sentence.strip(' -"\'')


def _is_noise(sentence: str) -> bool:
    if len(sentence) < 18:
        return True
    if any(p in sentence for p in NOISE_PATTERNS):
        return True
    if "raw/assets/" in sentence or "相关主题域" in sentence or "来自来源" in sentence:
        return True
    if sentence.count("：") >= 2:
        return True
    return False


def _score(sentence: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        if term and term in sentence:
            score += 4 + sentence.count(term)
    for p in PREFERRED_PATTERNS:
        if p in sentence:
            score += 2
    if "。" in sentence or "；" in sentence:
        score += 1
    return score


def _select_sentences(sentences: list[str], terms: list[str], limit: int) -> list[str]:
    cleaned = [_normalize_sentence(s) for s in sentences]
    filtered = [s for s in cleaned if not _is_noise(s)]
    ranked = sorted(filtered, key=lambda s: _score(s, terms), reverse=True)
    result: list[str] = []
    for s in (ranked or cleaned):
        if s not in result:
            result.append(s)
        if len(result) >= limit:
            break
    return result


def _compress_lead(sentences: list[str]) -> str:
    picked = [_normalize_sentence(s).rstrip("。") for s in sentences[:2] if s]
    if not picked:
        return "待补充。"
    if len(picked) == 1:
        return picked[0] + "。"
    return f"{picked[0]}；{picked[1]}。"


def _sanitize_filename(name: str, max_length: int = 96) -> str:
    name = INVALID_CHARS.sub("_", name.strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return (name[:max_length].rstrip("_. ") or "untitled")


def _slugify(name: str) -> str:
    return f"{datetime.now().strftime('%Y-%m-%d--%H%M%S')}--{_sanitize_filename(name, 64)}"


def _outbound_links(path: Path) -> set[str]:
    return {m.strip() for m in LINK_PATTERN.findall(path.read_text(encoding="utf-8"))}


def _page_title(path: Path) -> str:
    meta, _ = _parse_frontmatter(path.read_text(encoding="utf-8"))
    return meta.get("title") or path.stem


def _linked_raw_path(path: Path, vault: Path) -> Path | None:
    text = path.read_text(encoding="utf-8")
    match = RAW_SOURCE_PATTERN.search(text)
    if not match:
        return None
    raw_path = vault / f"{match.group(1)}.md"
    return raw_path if raw_path.exists() else None


def _linked_domain_refs(path: Path) -> list[str]:
    return sorted(l for l in _outbound_links(path) if l.startswith("domains/"))


def _synthesis_ref_for_domain(domain_ref: str) -> str:
    return f"syntheses/{domain_ref.split('/', 1)[1]}--综合分析"


def _preferred_raw_sentences(raw_markdown: str) -> list[str]:
    sentences: list[str] = []
    for heading in RAW_SECTION_HEADINGS:
        pattern = re.compile(rf"##+\s+{re.escape(heading)}\s*\n(.*?)(?:\n##+\s+|\Z)", re.S)
        match = pattern.search(raw_markdown)
        if match:
            sentences.extend(_split_sentences(_plain_text(match.group(1)).strip()))
    if sentences:
        return sentences
    return _split_sentences(_plain_text(raw_markdown))


def _load_index_candidates(vault: Path, query: str, top: int = 5) -> list:
    from dataclasses import dataclass
    @dataclass
    class _C:
        ref: str; path: Path; score: int

    index_text = (vault / "wiki" / "index.md").read_text(encoding="utf-8")
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[一-鿿]{2,8}", query)
    candidates: list[_C] = []
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
        score = sum(3 for t in terms if t in haystack) + sum(haystack.count(t) for t in terms) + FOLDER_WEIGHTS.get(folder, 0)
        if score > 0:
            candidates.append(_C(ref=ref, path=path, score=score))
    return sorted(candidates, key=lambda c: c.score, reverse=True)[:top]


def _dedupe(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for item in items:
        item = item.strip()
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result


def build_query_delta_legacy(vault: Path, question: str) -> tuple[str, str]:
    """Legacy heuristic query delta builder (自动驾驶 domain specific)."""
    candidates = _load_index_candidates(vault, question, top=5)
    evidence: list[str] = []
    source_refs: list[str] = []
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[一-鿿]{2,8}", question)
    preferred = [c for c in candidates if c.ref.startswith(("syntheses/", "sources/", "briefs/", "domains/"))] or candidates
    for c in preferred[:3]:
        meta, body = _parse_frontmatter(c.path.read_text(encoding="utf-8"))
        page_type = meta.get("type", "")
        if page_type == "source":
            evidence.extend(_split_sentences(_section_excerpt(body, "核心摘要")))
            for dref in _linked_domain_refs(c.path):
                spath = vault / "wiki" / f"{_synthesis_ref_for_domain(dref)}.md"
                if spath.exists():
                    _, sbody = _parse_frontmatter(spath.read_text(encoding="utf-8"))
                    evidence.extend(_split_sentences(_section_excerpt(sbody, "当前结论")))
                    source_refs.append(_synthesis_ref_for_domain(dref))
                source_refs.append(dref)
        elif page_type == "brief":
            evidence.extend(_split_sentences(get_one_sentence(meta, body)))
            evidence.extend(_split_sentences(_section_excerpt(body, "骨架") or _section_excerpt(body, "数据") or _section_excerpt(body, "核心要点")))
        elif page_type == "synthesis":
            evidence.extend(_split_sentences(_section_excerpt(body, "当前结论")))
        else:
            evidence.extend(_split_sentences(_plain_text(body)[:400]))
        if c.ref.startswith("sources/"):
            source_refs.append(c.ref)
        raw_path = _linked_raw_path(c.path, vault)
        if raw_path:
            evidence.extend(_preferred_raw_sentences(raw_path.read_text(encoding="utf-8")))
            source_refs.append(f"raw/articles/{raw_path.stem}")

    bullets = _select_sentences(evidence, terms, limit=5)
    answer_lead = _compress_lead(bullets)
    slug = _slugify(f"delta-query-{question}")
    page = "\n".join([
        "---",
        f'title: "{question} | Delta Compile 草稿"',
        'type: "delta-compile"', 'status: "review-needed"',
        'graph_role: "working"', 'graph_include: "false"',
        'lifecycle: "review-needed"',
        f'question: "{question}"',
        f'created_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
        "---", "",
        f"# {question} | Delta Compile 草稿", "",
        "## 背景", "", "- 该问题在 `wiki/log.md` 中重复出现。", "",
        "## 建议回答", "", answer_lead, "",
        "## 支撑要点", "", *(f"- {line}" for line in bullets[:3]), "",
        "## 建议沉淀", "", "- 如果这个问题继续高频出现，建议提升为正式 `syntheses/` 页面段落。", "",
        "## 使用证据", "", *(f"- [[{ref}]]" for ref in _dedupe(source_refs, limit=8)), "",
    ])
    return slug, page


def build_source_delta_legacy(vault: Path, source_title: str) -> tuple[str, str]:
    """Legacy heuristic source delta builder (自动驾驶 domain specific)."""
    source_path = None
    for path in (vault / "wiki" / "sources").glob("*.md"):
        if _page_title(path) == source_title:
            source_path = path
            break
    if source_path is None:
        raise SystemExit(f"Source page not found for title: {source_title}")
    source_text = source_path.read_text(encoding="utf-8")
    _, source_body = _parse_frontmatter(source_text)
    raw_path = _linked_raw_path(source_path, vault)
    raw_md = raw_path.read_text(encoding="utf-8") if raw_path else ""
    source_summary = _split_sentences(_section_excerpt(source_body, "核心摘要"))
    raw_sentences = _preferred_raw_sentences(raw_md) if raw_md else []
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[一-鿿]{2,8}", source_title)
    merged = _select_sentences(source_summary + raw_sentences, terms, limit=8)
    lead = _compress_lead(merged)
    slug = _slugify(f"delta-source-{source_path.stem}")
    page = "\n".join([
        "---",
        f'title: "{source_title} | Delta Compile 草稿"',
        'type: "delta-compile"', 'status: "review-needed"',
        'graph_role: "working"', 'graph_include: "false"',
        'lifecycle: "review-needed"',
        f'source_page: "[[sources/{source_path.stem}]]"',
        f'raw_source: "[[raw/articles/{raw_path.stem}]]"' if raw_path else 'raw_source: ""',
        f'created_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
        "---", "",
        f"# {source_title} | Delta Compile 草稿", "",
        "## 建议替换的一句话结论", "", lead, "",
        "## 建议替换的快读要点", "", *(f"- {line}" for line in merged[:5]), "",
        "## 建议替换的来源摘要", "", *(f"- {line}" for line in merged[:6]), "",
        "## 使用证据", "", f"- [[sources/{source_path.stem}]]",
        *(["- [[raw/articles/{}]]".format(raw_path.stem)] if raw_path else []), "",
        "## 说明", "", "- 该来源在 `wiki/log.md` 中被重复 ingest，适合人工确认后正式回写。", "",
    ])
    return slug, page
