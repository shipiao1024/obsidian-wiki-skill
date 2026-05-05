"""Multi-source digest generation: deep report, comparison table, timeline.

Digest modes aggregate across multiple sources/stances/questions
to produce structured knowledge outputs beyond single-source briefs.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .shared import get_one_sentence, parse_frontmatter, section_excerpt


def collect_digest_sources(vault: Path, topic: str, limit: int = 10) -> list[dict[str, str]]:
    """Collect sources, stances, and questions related to a topic."""
    terms = [t for t in re.findall(r"[一-鿿]{2,8}|[A-Za-z0-9\-\+]{2,}", topic) if len(t) >= 2]
    sources: list[dict[str, str]] = []

    folders = {
        "sources": vault / "wiki" / "sources",
        "stances": vault / "wiki" / "stances",
        "questions": vault / "wiki" / "questions",
        "syntheses": vault / "wiki" / "syntheses",
        "briefs": vault / "wiki" / "briefs",
    }

    for folder_name, folder_path in folders.items():
        if not folder_path.exists():
            continue
        for fpath in sorted(folder_path.glob("*.md")):
            text = fpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            # Score relevance by term overlap
            score = sum(1 for t in terms if t in text)
            if score == 0:
                title = meta.get("title", "").strip('"')
                score = sum(1 for t in terms if t in title)
            if score == 0:
                continue
            sources.append({
                "ref": f"{folder_name}/{fpath.stem}",
                "title": meta.get("title", "").strip('"') or fpath.stem,
                "date": meta.get("date", "").strip('"'),
                "type": meta.get("type", folder_name),
                "score": str(score),
                "meta": meta,
                "body_excerpt": body[:600],
            })

    sources.sort(key=lambda s: int(s.get("score", "0")), reverse=True)
    return sources[:limit]


def build_deep_report(vault: Path, topic: str, sources: list[dict[str, str]]) -> str:
    """Build a deep report: background + core views + cross-perspective comparison + knowledge lineage + unresolved questions."""
    lines: list[str] = [f"# 深度报告：{topic}", ""]
    lines.append(f"> 生成日期：{date.today().isoformat()}")
    lines.append("")

    # Background
    lines.append("## 背景")
    lines.append("")
    background_sources = [s for s in sources if s["type"] in ("source", "brief")]
    for s in background_sources[:3]:
        core = section_excerpt(s["body_excerpt"], "核心摘要") or get_one_sentence(s.get("meta", {}), s["body_excerpt"])
        lines.append(f"- [[{s['ref']}]]: {core[:200] or s['title']}")
    lines.append("")

    # Core views
    lines.append("## 核心观点")
    lines.append("")
    for s in sources[:6]:
        if s["type"] == "source":
            core = section_excerpt(s["body_excerpt"], "核心摘要")[:300]
        elif s["type"] == "synthesis":
            core = section_excerpt(s["body_excerpt"], "当前结论")[:300]
        elif s["type"] == "stance":
            core = section_excerpt(s["body_excerpt"], "核心判断")[:300]
        else:
            core = s["body_excerpt"][:200]
        if core:
            lines.append(f"### [[{s['ref']}]]")
            lines.append(core)
            lines.append("")
    lines.append("")

    # Cross-perspective comparison
    lines.append("## 跨视角对比")
    lines.append("")
    stances = [s for s in sources if s["type"] == "stance"]
    if stances:
        for s in stances:
            judgement = section_excerpt(s["body_excerpt"], "核心判断")[:160]
            support = section_excerpt(s["body_excerpt"], "支持证据")[:160]
            contradict = section_excerpt(s["body_excerpt"], "反对证据（steel-man）")[:160]
            lines.append(f"- [[{s['ref']}]]: {judgement}")
            if support:
                lines.append(f"  支持：{support}")
            if contradict:
                lines.append(f"  反驳：{contradict}")
    else:
        lines.append("- （暂无立场对比数据）")
    lines.append("")

    # Unresolved questions
    lines.append("## 未解问题")
    lines.append("")
    questions = [s for s in sources if s["type"] == "question"]
    for s in questions[:5]:
        q_text = section_excerpt(s["body_excerpt"], "问题")[:160] or s["title"]
        lines.append(f"- [[{s['ref']}]]: {q_text}")
    if not questions:
        lines.append("- （暂无记录的开放问题）")
    lines.append("")

    return "\n".join(lines)


def build_comparison_table(vault: Path, topic: str, sources: list[dict[str, str]]) -> str:
    """Build a comparison table: core views, applicable scenarios, strengths, weaknesses."""
    lines: list[str] = [f"# 对比表：{topic}", ""]
    lines.append(f"> 生成日期：{date.today().isoformat()}")
    lines.append("")

    lines.append("| 来源 | 核心观点 | 适用场景 | 优势 | 劣势 |")
    lines.append("|---|---|---|---|---|")

    for s in sources[:8]:
        if s["type"] not in ("source", "synthesis", "stance"):
            continue
        if s["type"] == "source":
            core = section_excerpt(s["body_excerpt"], "核心摘要")[:80]
            relation = section_excerpt(s["body_excerpt"], "与现有知识库的关系")[:80]
            pros = ""
            cons = ""
            if "巩固" in relation or "巩固" in s["body_excerpt"]:
                pros = "有实证支持"
            if "冲突" in relation or "矛盾" in relation:
                cons = "与已有知识冲突"
        elif s["type"] == "synthesis":
            core = section_excerpt(s["body_excerpt"], "当前结论")[:80]
            pros = "综合视角"
            cons = "依赖多源质量"
        elif s["type"] == "stance":
            core = section_excerpt(s["body_excerpt"], "核心判断")[:80]
            pros = section_excerpt(s["body_excerpt"], "支持证据")[:40]
            cons = section_excerpt(s["body_excerpt"], "反对证据（steel-man）")[:40]
        else:
            core = ""
            pros = ""
            cons = ""
        lines.append(f"| [[{s['ref']}]] | {core or '-'} | - | {pros or '-'} | {cons or '-'} |")

    lines.append("")
    return "\n".join(lines)


def build_timeline(vault: Path, topic: str, sources: list[dict[str, str]]) -> str:
    """Build a timeline: Mermaid gantt chart + event descriptions."""
    lines: list[str] = [f"# 时间线：{topic}", ""]
    lines.append(f"> 生成日期：{date.today().isoformat()}")
    lines.append("")

    # Sort sources by date
    dated_sources = sorted(
        [s for s in sources if s.get("date")],
        key=lambda s: s["date"],
    )

    if dated_sources:
        lines.append("## Mermaid 时间线")
        lines.append("")
        lines.append("```mermaid")
        lines.append("timeline")
        for s in dated_sources[:15]:
            d = s["date"][:10] if len(s["date"]) >= 10 else s["date"]
            title = s["title"][:50]
            lines.append(f"  {d} : {title}")
        lines.append("```")
        lines.append("")

    lines.append("## 事件列表")
    lines.append("")
    for s in dated_sources[:15]:
        core = section_excerpt(s["body_excerpt"], "核心摘要")[:200] or s["body_excerpt"][:100]
        lines.append(f"- **{s['date'][:10]}** [[{s['ref']}]]: {core}")
    if not dated_sources:
        lines.append("- （来源均无日期信息，无法构建时间线）")
    lines.append("")

    return "\n".join(lines)


def write_digest_page(vault: Path, topic: str, digest_type: str, content: str) -> Path:
    """Write a digest page to wiki/syntheses/."""
    safe_topic = re.sub(r'[\\/:*?"<>|\r\n]', "_", topic.strip())[:50]
    slug = f"{safe_topic}--{digest_type}"
    page_path = vault / "wiki" / "syntheses" / f"{slug}.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = [
        "---",
        f'title: "{topic} {digest_type}"',
        f'type: "digest"',
        f'digest_type: "{digest_type}"',
        f'digest_topic: "{topic}"',
        'lifecycle: "canonical"',
        f'generated: "{date.today().isoformat()}"',
        "---",
        "",
    ]
    page_path.write_text("\n".join(frontmatter) + content + "\n", encoding="utf-8")
    return page_path


def build_research_report(vault: Path, topic: str) -> str:
    """Build a research report from wiki/research/ artifacts if they exist.

    When a deep-research project has completed for the given topic,
    this function reads the ledger, scenarios, and premortem pages
    and assembles them into a digest-style cross-reference report.
    If no research project exists, returns an empty string.
    """
    from .dependency_ledger import research_slug
    slug = research_slug(topic)
    report_path = vault / "wiki" / "research" / f"{slug}--report.md"
    if not report_path.exists():
        return ""

    text = report_path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    return body