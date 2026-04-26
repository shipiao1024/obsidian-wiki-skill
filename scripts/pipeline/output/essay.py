"""Mode: essay — draft essay from stance + synthesis + sources."""

from __future__ import annotations

from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import parse_frontmatter, section_excerpt


def build_essay_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """Draft essay from stance + synthesis + sources with [[ref]] backlinks."""
    lines: list[str] = [f"# 文章草稿：{question}", ""]

    # Gather stances
    stances_dir = vault / "wiki" / "stances"
    stances: list[tuple[str, dict[str, str], str]] = []
    if stances_dir.exists():
        for spath in sorted(stances_dir.glob("*.md")):
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("status") not in ("active", "challenged"):
                continue
            stances.append((spath.stem, meta, body))

    # Gather synthesis pages
    syntheses_dir = vault / "wiki" / "syntheses"
    syntheses: list[tuple[str, dict[str, str], str]] = []
    if syntheses_dir.exists():
        for spath in sorted(syntheses_dir.glob("*.md")):
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            syntheses.append((spath.stem, meta, body))

    # Introduction
    lines.append("## 引言")
    lines.append("")
    lines.append(f"本文围绕「{question}」展开讨论，综合知识库中的立场、综合分析和来源。")
    lines.append("")

    # Main body from stances
    if stances:
        lines.append("## 核心论点")
        lines.append("")
        for stem, meta, body in stances[:5]:
            judgement = section_excerpt(body, "核心判断")[:300]
            support = section_excerpt(body, "支持证据")[:200]
            lines.append(f"### [[stances/{stem}]]")
            lines.append(judgement)
            lines.append("")
            if support:
                lines.append(f"支持证据：{support}")
                lines.append("")

    # Synthesis context
    if syntheses:
        lines.append("## 综合视角")
        lines.append("")
        for stem, meta, body in syntheses[:3]:
            conclusion = section_excerpt(body, "当前结论")[:300]
            lines.append(f"### [[syntheses/{stem}]]")
            lines.append(conclusion)
            lines.append("")

    # Source evidence
    lines.append("## 来源依据")
    lines.append("")
    for cand in candidates[:6]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "source":
            core = section_excerpt(body, "核心摘要")[:200]
            lines.append(f"- [[{ref}]]: {core or meta.get('title', ref)}")
    lines.append("")

    # Conclusion
    lines.append("## 结论与展望")
    lines.append("")
    questions_dir = vault / "wiki" / "questions"
    q_count = 0
    if questions_dir.exists():
        for qpath in sorted(questions_dir.glob("*.md")):
            text = qpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("status") in ("open", "partial"):
                q_text = section_excerpt(body, "问题")[:120]
                lines.append(f"- 待解答：[[questions/{qpath.stem}]] {q_text}")
                q_count += 1
                if q_count >= 3:
                    break
    if q_count == 0:
        lines.append("- （需进一步研究确认结论）")
    lines.append("")

    return "\n".join(lines)