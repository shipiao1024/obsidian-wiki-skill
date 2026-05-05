"""Mode: briefing — 4-dimension cognitive briefing: sources + skeleton + data + predict + falsification + stances."""

from __future__ import annotations

import re
from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import get_one_sentence, parse_frontmatter, section_excerpt
from pipeline.typed_edges import collect_typed_edges


def build_briefing_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """4-dimension cognitive briefing: sources, skeleton, data, predict, falsification, stances."""
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
            summary = get_one_sentence(meta, body)[:200]
        elif meta.get("type") == "synthesis":
            summary = section_excerpt(body, "当前结论")[:200]
        lines.append(f"- [[{ref}]]: {summary or title}")
    if not seen_refs:
        lines.append("- （未找到相关来源）")
    lines.append("")

    # --- Skeleton (from brief pages' 骨架 section) ---
    lines.append("## 骨架聚合")
    lines.append("")
    skeleton_found = False
    for cand in candidates[:6]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "brief":
            skeleton_text = section_excerpt(body, "骨架")
            if skeleton_text:
                lines.append(f"- [[{ref}]]: {skeleton_text[:200]}")
                skeleton_found = True
        elif meta.get("type") == "source":
            core = section_excerpt(body, "核心摘要")
            if core:
                # Extract key claims from source summaries as skeleton evidence
                for sentence in re.split(r"(?<=[。！？；])", core):
                    s = sentence.strip()
                    if len(s) >= 14 and not skeleton_found:
                        lines.append(f"- [[{ref}]]: {s[:200]}")
                        skeleton_found = True
                        break
    if not skeleton_found:
        lines.append("- （待从来源中提取因果骨架）")
    lines.append("")

    # --- Data (from brief pages' 数据 section) ---
    lines.append("## 关键数据")
    lines.append("")
    data_found = False
    for cand in candidates[:6]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "brief":
            data_text = section_excerpt(body, "数据")
            if data_text:
                lines.append(f"- [[{ref}]]: {data_text[:200]}")
                data_found = True
    if not data_found:
        lines.append("- （暂无结构化数据）")
    lines.append("")

    # --- Predict (from brief pages' 推演 section) ---
    lines.append("## 推演信号")
    lines.append("")
    predict_found = False
    for cand in candidates[:6]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "brief":
            predict_text = section_excerpt(body, "推演")
            if predict_text:
                lines.append(f"- [[{ref}]]: {predict_text[:200]}")
                predict_found = True
    if not predict_found:
        lines.append("- （暂无推演分析）")
    lines.append("")

    # --- Falsification (from brief pages' 失效信号 section + typed edges contradicts) ---
    lines.append("## 失效信号")
    lines.append("")
    falsification_found = False
    # From brief pages
    for cand in candidates[:6]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "brief":
            fals_text = section_excerpt(body, "失效信号")
            if fals_text:
                lines.append(f"- [[{ref}]]: {fals_text[:200]}")
                falsification_found = True
    # From typed edges (contradicts relationships)
    edges = collect_typed_edges(vault)
    contradict_edges = [e for e in edges if e["type"] == "contradicts"]
    for edge in contradict_edges[:3]:
        source_ref = edge["source"]
        target_ref = edge["target"]
        _, source_body = _read_page(vault, source_ref)
        source_judgement = section_excerpt(source_body, "核心判断")[:160]
        lines.append(f"- [[{source_ref}]] 反驳 [[{target_ref}]]: {source_judgement or '存在反对证据'}")
        falsification_found = True
    # Heuristic: check source pages for contradiction keywords
    for cand in candidates[:5]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") == "source":
            contradictions = section_excerpt(body, "与现有知识库的关系")
            if "冲突" in contradictions or "矛盾" in contradictions or "反驳" in contradictions:
                lines.append(f"- [[{ref}]]: {contradictions[:200]}")
                falsification_found = True
    if not falsification_found:
        lines.append("- （当前知识库中未检测到明显冲突或失效条件）")
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