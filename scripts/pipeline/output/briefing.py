"""Mode: briefing — structured briefing: sources + claims + controversies + questions + stance."""

from __future__ import annotations

import re
from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import parse_frontmatter, section_excerpt
from pipeline.typed_edges import collect_typed_edges


def build_briefing_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """Structured briefing: sources, claims, controversies, open questions, stances."""
    lines: list[str] = [f"# 简报：{question}", ""]

    # --- Sources ---
    lines.append("## 相关来源")
    lines.append("")
    seen_refs: list[str] = []
    for cand in candidates[:8]:
        ref = cand.ref  # type: ignore[attr-defined]
        seen_refs.append(ref)
        meta, body = _read_page(vault, ref)
        title = _page_title(meta, cand.path.stem)  # type: ignore[attr-defined]
        summary = ""
        if meta.get("type") == "source":
            summary = section_excerpt(body, "核心摘要")[:200]
        elif meta.get("type") == "brief":
            summary = section_excerpt(body, "一句话结论")[:200]
        elif meta.get("type") == "synthesis":
            summary = section_excerpt(body, "当前结论")[:200]
        lines.append(f"- [[{ref}]]: {summary or title}")
    if not seen_refs:
        lines.append("- （未找到相关来源）")
    lines.append("")

    # --- Claims ---
    lines.append("## 核心主张")
    lines.append("")
    claim_count = 0
    for cand in candidates[:5]:
        meta, body = _read_page(vault, cand.ref)  # type: ignore[attr-defined]
        if meta.get("type") in ("source", "brief"):
            section = section_excerpt(body, "核心摘要") or section_excerpt(body, "核心要点")
            if section:
                for sentence in re.split(r"(?<=[。！？；])", section):
                    s = sentence.strip()
                    if len(s) >= 14 and claim_count < 6:
                        lines.append(f"- {s}  （[[{cand.ref}]]）")  # type: ignore[attr-defined]
                        claim_count += 1
    if claim_count == 0:
        lines.append("- （待从来源中提取）")
    lines.append("")

    # --- Controversies (typed edges + heuristic) ---
    lines.append("## 争议与冲突")
    lines.append("")
    controversy_found = False
    # Use typed edges for contradict relationships
    edges = collect_typed_edges(vault)
    contradict_edges = [e for e in edges if e["type"] == "contradicts"]
    seen_contradict_targets: set[str] = set()
    for edge in contradict_edges[:5]:
        source_ref = edge["source"]
        target_ref = edge["target"]
        _, source_body = _read_page(vault, source_ref)
        _, target_body = _read_page(vault, target_ref)
        source_judgement = section_excerpt(source_body, "核心判断")[:160]
        lines.append(f"- [[{source_ref}]] 反驳 [[{target_ref}]]: {source_judgement or '存在反对证据'}")
        seen_contradict_targets.add(target_ref)
        controversy_found = True
    # Also check source pages for contradiction keywords (heuristic fallback)
    for cand in candidates[:5]:
        ref = cand.ref  # type: ignore[attr-defined]
        if ref in seen_contradict_targets:
            continue
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "source":
            contradictions = section_excerpt(body, "与现有知识库的关系")
            if "冲突" in contradictions or "矛盾" in contradictions or "反驳" in contradictions:
                lines.append(f"- [[{ref}]]: {contradictions[:200]}")
                controversy_found = True
    if not controversy_found:
        lines.append("- （当前知识库中未检测到明显冲突）")
    lines.append("")

    # --- Open questions ---
    lines.append("## 相关开放问题")
    lines.append("")
    questions_dir = vault / "wiki" / "questions"
    q_count = 0
    if questions_dir.exists():
        for qpath in sorted(questions_dir.glob("*.md")):
            text = qpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("status") in ("open", "partial"):
                q_text = section_excerpt(body, "问题") or _page_title(meta, qpath.stem)
                lines.append(f"- [[questions/{qpath.stem}]]: {q_text[:120]}")
                q_count += 1
                if q_count >= 5:
                    break
    if q_count == 0:
        lines.append("- （暂无开放问题）")
    lines.append("")

    # --- Stances ---
    lines.append("## 相关立场")
    lines.append("")
    stances_dir = vault / "wiki" / "stances"
    s_count = 0
    if stances_dir.exists():
        for spath in sorted(stances_dir.glob("*.md")):
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("status") in ("active", "challenged"):
                confidence = meta.get("confidence", "medium")
                judgement = section_excerpt(body, "核心判断")[:160]
                lines.append(f"- [[stances/{spath.stem}]] （{confidence}）: {judgement}")
                s_count += 1
                if s_count >= 5:
                    break
    if s_count == 0:
        lines.append("- （暂无相关立场）")
    lines.append("")

    return "\n".join(lines)