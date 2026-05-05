#!/usr/bin/env python
"""Legacy heuristic synthesis builder (deprecated).

This module preserves the old domain-specific heuristic synthesis logic
for backward compatibility. New domains should use the three-stage
--collect-only → LLM → --apply workflow in refresh_synthesis.py.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

# Domain-specific patterns (自动驾驶 domain only)
NOISE_PATTERNS = (
    "系列导读", "上一篇", "开场", "那个工程师写下的一行笔记",
    "广泛流传的感受", "接下来这个", "下一篇", "待补充", "待后续",
)
PREFERRED_PATTERNS = (
    "根本", "意味着", "核心", "直接", "推动", "区别", "架构",
    "AIDV", "EEA", "SDV", "端到端", "集中", "分工", "取消分工",
)
RAW_SECTION_HEADINGS = (
    "第一幕：AIDV 和 SDV 的根本区别在哪里",
    "这个区别在工程上意味着什么",
    "从 EEA 的视角看：为什么 E2E 逼出了中央计算",
    "E2E 架构的工程本质",
    "一个被低估的工程优势：推理延迟",
)


def _plain_text(md: str) -> str:
    text = re.sub(r"\A---\s*\n(.*?)\n---\s*\n?", "", md, flags=re.S)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"!\[\[[^\]]+\]\]", "", text)
    text = re.sub(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
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


def build_synthesis_page_legacy(vault: Path, synthesis_path: Path) -> str:
    """Legacy heuristic synthesis builder (自动驾驶 domain specific)."""
    # Import shared utilities
    from pipeline.shared import resolve_vault

    FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
    LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
    RAW_SOURCE_PATTERN = re.compile(r'raw_source:\s*"\[\[([^\]]+)\]\]"')
    CLAIM_PATTERN = re.compile(r"^- \[([^\]|]+)\|([^\]]+)\]\s+(.+)$", re.M)
    CONF_WEIGHT = {"high": 6, "medium": 3, "low": 1}

    def parse_fm(text: str) -> tuple[dict[str, str], str]:
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

    def outbound(path: Path) -> set[str]:
        return {m.strip() for m in LINK_PATTERN.findall(path.read_text(encoding="utf-8"))}

    def linked_raw(path: Path) -> Path | None:
        text = path.read_text(encoding="utf-8")
        match = RAW_SOURCE_PATTERN.search(text)
        if not match:
            return None
        raw = vault / f"{match.group(1)}.md"
        return raw if raw.exists() else None

    def source_paths() -> list[Path]:
        refs = sorted(l for l in outbound(synthesis_path) if l.startswith("sources/"))
        return [vault / "wiki" / f"{r}.md" for r in refs if (vault / "wiki" / f"{r}.md").exists()]

    def extract_claims(sp: Path) -> list[dict[str, str]]:
        text = sp.read_text(encoding="utf-8")
        _, body = parse_fm(text)
        pattern = re.compile(r"##\s+关键判断\s*\n(.*?)(?:\n##\s+|\Z)", re.S)
        match = pattern.search(body)
        if not match:
            return []
        claims = []
        for m in CLAIM_PATTERN.finditer(match.group(1)):
            claims.append({
                "claim_type": m.group(1).strip(),
                "confidence": m.group(2).strip().lower(),
                "claim": m.group(3).strip().rstrip("⚠️需验证").strip(),
            })
        return claims

    meta, _ = parse_fm(synthesis_path.read_text(encoding="utf-8"))
    domain = meta.get("domain") or synthesis_path.stem.replace("--综合分析", "")
    sps = source_paths()
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[一-鿿]{2,8}", domain)

    all_claims: list[dict[str, str]] = []
    for sp in sps:
        for c in extract_claims(sp):
            c["_source"] = sp.stem
            all_claims.append(c)

    if all_claims:
        ranked = sorted(all_claims, key=lambda c: CONF_WEIGHT.get(c.get("confidence", "low"), 1) + sum(4 for t in terms if t in c.get("claim", "")), reverse=True)
        seen: set[str] = set()
        deduped = []
        for c in ranked:
            if c["claim"] not in seen:
                seen.add(c["claim"])
                deduped.append(c)
        high_medium = [c for c in deduped if c.get("confidence") in ("high", "medium")]
        lead_parts = [_normalize_sentence(c["claim"]).rstrip("。") for c in (high_medium or deduped)[:2]]
        lead = f"{lead_parts[0]}。" if len(lead_parts) == 1 else f"{lead_parts[0]}；{lead_parts[1]}。" if lead_parts else "待补充。"
        selected = [c["claim"] for c in deduped[:8]]
    else:
        evidence: list[str] = []
        for sp in sps:
            _, body = parse_fm(sp.read_text(encoding="utf-8"))
            evidence.extend(_split_sentences(_section_excerpt(body, "核心摘要")))
            raw = linked_raw(sp)
            if raw:
                raw_text = raw.read_text(encoding="utf-8")
                for heading in RAW_SECTION_HEADINGS:
                    excerpt = _section_excerpt(raw_text, heading)
                    if excerpt:
                        evidence.extend(_split_sentences(excerpt))
                if not evidence:
                    evidence.extend(_split_sentences(_plain_text(raw_text)))
        cleaned = [_normalize_sentence(s) for s in evidence]
        filtered = [s for s in cleaned if not _is_noise(s)]
        ranked = sorted(filtered, key=lambda s: _score(s, terms), reverse=True)
        selected = []
        for s in (ranked or cleaned):
            if s not in selected:
                selected.append(s)
            if len(selected) >= 8:
                break
        lead_parts = [_normalize_sentence(s).rstrip("。") for s in selected[:2] if s]
        lead = f"{lead_parts[0]}。" if len(lead_parts) == 1 else f"{lead_parts[0]}；{lead_parts[1]}。" if lead_parts else "待补充。"

    concepts: list[str] = []
    for sp in sps:
        concepts.extend(l for l in outbound(sp) if l.startswith("concepts/"))
    deduped_concepts: list[str] = []
    for c in concepts:
        if c not in deduped_concepts:
            deduped_concepts.append(c)
        if len(deduped_concepts) >= 8:
            break

    lines = [
        "---",
        f'title: "{domain} 综合分析"',
        'type: "synthesis"', 'status: "draft"',
        'graph_role: "knowledge"', 'graph_include: "true"',
        'lifecycle: "official"',
        f'domain: "{domain}"',
        f'updated_at: "{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"',
        "---", "",
        f"# {domain} 综合分析", "",
        "## 当前结论", "", lead, "",
        "## 核心判断", "",
    ]
    if all_claims:
        for c in deduped[:4]:
            conf = c.get("confidence", "low")
            marker = f"{conf}" if conf != "low" else "low⚠️"
            src = f" —— [[sources/{c.get('_source', '')}]]" if c.get("_source") else ""
            lines.append(f"- [{marker}] {c['claim']}{src}")
    else:
        lines.extend(f"- {s}" for s in selected[:4])

    lines.extend(["", "## 近期来源", ""])
    lines.extend(f"- [[sources/{sp.stem}]]" for sp in sps)
    lines.extend(["", "## 相关概念", ""])
    lines.extend(f"- [[{c}]]" for c in deduped_concepts)
    if not deduped_concepts:
        lines.append("- 待补充。")
    lines.extend(["", "## 待验证 / 后续维护", ""])
    if len(sps) <= 1:
        lines.append("- 当前主要基于单一来源，后续需要更多来源补充冲突、边界和反例。")
    else:
        lines.append("- 新来源进入该主题域时，优先检查结论是否被强化、修正或推翻。")
        lines.append("- 如果不同来源给出不同判断，应补一节"冲突与边界"。")
    lines.append("")
    return "\n".join(lines)
