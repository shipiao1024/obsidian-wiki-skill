"""Mode: contradict — find strongest rebuttal from knowledge base."""

from __future__ import annotations

import re
from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import parse_frontmatter, section_excerpt, plain_text
from pipeline.typed_edges import collect_typed_edges


def build_contradict_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """Find the strongest rebuttal from the knowledge base."""
    lines: list[str] = [f"# 反驳检索：{question}", ""]

    # Parse the question to extract the claim to rebut
    claim = question
    for prefix in ("反驳", "反对", "contradict", "rebut", "挑战", "质疑"):
        if claim.lower().startswith(prefix):
            claim = claim[len(prefix):].strip("：: ，, ")
            break

    lines.append(f"目标论点：{claim}")
    lines.append("")

    # Scan stances for contradicting evidence
    lines.append("## 立场中的反对证据")
    lines.append("")
    stances_dir = vault / "wiki" / "stances"
    stance_hits = 0
    if stances_dir.exists():
        for spath in sorted(stances_dir.glob("*.md")):
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("status") not in ("active", "challenged"):
                continue
            # Check if the stance topic or body relates to the claim
            stance_title = _page_title(meta, spath.stem)
            if claim and claim not in text and claim not in stance_title:
                continue
            contradict_section = section_excerpt(body, "反对证据（steel-man）")
            if contradict_section and "暂无" not in contradict_section:
                lines.append(f"### [[stances/{spath.stem}]]")
                lines.append(f"置信度：{meta.get('confidence', 'medium')}")
                lines.append("")
                lines.append(contradict_section[:400])
                lines.append("")
                stance_hits += 1
                if stance_hits >= 3:
                    break
    if stance_hits == 0:
        lines.append("- （立场页中未找到直接反对证据）")
    lines.append("")

    # Scan typed edges for contradicting and supporting relationships
    lines.append("## 类型化关系图谱")
    lines.append("")
    edges = collect_typed_edges(vault)
    typed_hits = 0
    # Find contradict edges related to the claim terms
    claim_terms = [t for t in re.findall(r"[一-鿿]{2,8}|[A-Za-z0-9\-\+]{2,}", claim) if len(t) >= 2]
    for edge in edges:
        if edge["type"] not in ("contradicts", "supports"):
            continue
        source_ref = edge["source"]
        target_ref = edge["target"]
        # Check if the edge's source/target refs relate to the claim
        _, source_body = _read_page(vault, source_ref)
        source_text = source_body[:500]
        is_relevant = not claim_terms or any(t in source_text for t in claim_terms)
        if not is_relevant:
            # Also check target
            _, target_body = _read_page(vault, target_ref)
            target_text = target_body[:500]
            is_relevant = any(t in target_text for t in claim_terms)
        if not is_relevant:
            continue
        edge_label = "反驳" if edge["type"] == "contradicts" else "支持"
        judgement = section_excerpt(source_body, "核心判断")[:160]
        lines.append(f"- [[{source_ref}]] {edge_label} [[{target_ref}]]: {judgement}")
        typed_hits += 1
        if typed_hits >= 5:
            break
    if typed_hits == 0:
        lines.append("- （类型化关系图谱中未找到相关反对/支持边）")
    lines.append("")
    lines.append("## 来源中的冲突信号")
    lines.append("")
    source_hits = 0
    for cand in candidates[:8]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if meta.get("type") != "source":
            continue
        relation = section_excerpt(body, "与现有知识库的关系")
        if "冲突" in relation or "矛盾" in relation or "反驳" in relation or "挑战" in relation:
            title = _page_title(meta, cand.path.stem)  # type: ignore[attr-defined]
            lines.append(f"- [[{ref}]]: {relation[:200]}")
            source_hits += 1
            if source_hits >= 5:
                break
    if source_hits == 0:
        lines.append("- （来源页中未检测到冲突信号）")
    lines.append("")

    # Find sources that disagree with top candidates
    lines.append("## 潜在对立面")
    lines.append("")
    if claim:
        # Look for pages that contain negation patterns near the claim terms
        negation_patterns = ["并非", "不是", "错误", "不正确", "误解", "质疑", "反驳", "矛盾"]
        potential: list[str] = []
        for folder in ("sources", "syntheses", "stances"):
            dir_path = vault / "wiki" / folder
            if not dir_path.exists():
                continue
            for fpath in dir_path.glob("*.md"):
                text = fpath.read_text(encoding="utf-8")
                _, body = parse_frontmatter(text)
                for pattern in negation_patterns:
                    # Find sentences containing both a negation and a claim term
                    for sentence in re.split(r"(?<=[。！？；])", plain_text(body)):
                        if pattern in sentence and any(t in sentence for t in claim if len(t) >= 2):
                            potential.append(f"- [[{folder}/{fpath.stem}]]: {sentence.strip()[:150]}")
                            break
                    if len(potential) >= 5:
                        break
                if len(potential) >= 5:
                    break
            if len(potential) >= 5:
                break
        lines.extend(potential[:5])
    if not lines[-1].startswith("- [["):
        lines.append("- （未找到潜在对立面）")
    lines.append("")

    return "\n".join(lines)