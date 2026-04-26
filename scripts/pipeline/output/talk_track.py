"""Mode: talk-track — meeting material pack: stance arguments + rebuttals + questions."""

from __future__ import annotations

from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import parse_frontmatter, section_excerpt
from pipeline.typed_edges import collect_typed_edges


def build_talk_track_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """Meeting material pack: stance arguments + rebuttals + open questions."""
    lines: list[str] = [f"# 会议素材包：{question}", ""]

    # Key arguments from stances
    stances_dir = vault / "wiki" / "stances"
    lines.append("## 核心论点")
    lines.append("")
    stance_count = 0
    if stances_dir.exists():
        for spath in sorted(stances_dir.glob("*.md")):
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("status") not in ("active", "challenged"):
                continue
            judgement = section_excerpt(body, "核心判断")[:200]
            support = section_excerpt(body, "支持证据")[:300]
            confidence = meta.get("confidence", "medium")
            lines.append(f"### [[stances/{spath.stem}]] （置信度：{confidence}）")
            lines.append(judgement)
            lines.append("")
            if support:
                lines.append(f"支持论据：{support}")
                lines.append("")
            stance_count += 1
            if stance_count >= 5:
                break
    if stance_count == 0:
        lines.append("- （暂无记录的立场）")
    lines.append("")

    # Rebuttals from typed edges
    lines.append("## 反驳与异议")
    lines.append("")
    edges = collect_typed_edges(vault)
    contradict_edges = [e for e in edges if e["type"] == "contradicts"]
    if contradict_edges:
        for edge in contradict_edges[:5]:
            _, source_body = _read_page(vault, edge["source"])
            judgement = section_excerpt(source_body, "核心判断")[:200]
            lines.append(f"- [[{edge['source']}]] 反驳 [[{edge['target']}]]: {judgement or '存在反对证据'}")
    else:
        lines.append("- （类型化关系图谱中未检测到反驳边）")
    lines.append("")

    # Open questions
    lines.append("## 待讨论问题")
    lines.append("")
    questions_dir = vault / "wiki" / "questions"
    q_count = 0
    if questions_dir.exists():
        for qpath in sorted(questions_dir.glob("*.md")):
            text = qpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("status") in ("open", "partial"):
                q_text = section_excerpt(body, "问题")[:160] or _page_title(meta, qpath.stem)
                confidence = meta.get("confidence", "medium")
                lines.append(f"- [[questions/{qpath.stem}]] （{confidence}）: {q_text}")
                q_count += 1
                if q_count >= 8:
                    break
    if q_count == 0:
        lines.append("- （暂无开放问题）")
    lines.append("")

    # Evidence sources
    lines.append("## 关键证据来源")
    lines.append("")
    for cand in candidates[:5]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "source":
            core = section_excerpt(body, "核心摘要")[:150]
            lines.append(f"- [[{ref}]]: {core or _page_title(meta, ref)}")
    lines.append("")

    return "\n".join(lines)