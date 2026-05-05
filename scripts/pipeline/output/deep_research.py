"""Mode: deep-research — vault briefing + LLM-driven protocol."""

from __future__ import annotations

from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import parse_frontmatter, section_excerpt


def build_deep_research_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """Deep research: vault briefing + instructions for LLM-driven protocol.

    This mode does NOT execute the research itself (LLM-first principle).
    It produces a briefing of existing vault knowledge and a protocol checklist
    that you follow to orchestrate the 8-phase reasoning-driven research cycle.
    """
    from pipeline.digest import build_research_report

    # Check if a research report already exists for this topic
    existing_report = build_research_report(vault, question)
    if existing_report:
        return existing_report

    lines: list[str] = [f"# 深度研究：{question}", ""]
    lines.append("> 此模式需要你执行推理驱动 8 阶段研究协议（横纵双轴分析）。")
    lines.append("> 协议详情见 references/deep-research-protocol.md")
    lines.append("")

    # Vault briefing (reuse briefing mode logic)
    lines.append("## 已有知识库内容")
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
        elif meta.get("type") == "synthesis":
            summary = section_excerpt(body, "当前结论")[:200]
        elif meta.get("type") == "stance":
            summary = section_excerpt(body, "核心判断")[:200]
        lines.append(f"- [[{ref}]]: {summary or title}")
    if not seen_refs:
        lines.append("- （知识库中暂无相关内容）")
    lines.append("")

    # Related open questions
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

    # Protocol checklist
    lines.append("## 研究协议")
    lines.append("")
    lines.append("1. **意图扩展**：确认用户真实需求和内在模型")
    lines.append("2. **需求审计 + 假说形成 + 搜索维度规划**：形成 2-4 个可证伪假说，规划 4-6 个搜索维度（必选：竞争格局、反面与风险）")
    lines.append("3. **Vault 证据收集**：对每个假说收集 vault 中已有的确认/反驳证据")
    lines.append("4. **扇形联网研究**：按维度批量搜索（非线性逐假说），最大 3 轮，每个 F 节点标注来源维度")
    lines.append("5. **外部事实校准**：产出共识/边界/争议/假说结果四块")
    lines.append("6. **根本问题挖掘**：压缩到 1-3 根本问题")
    lines.append("7. **三剧本推演**：最可能/最危险/最乐观剧本，含量化扰动和边界条件")
    lines.append("8. **预验尸**：3 个失败情景映射账本根节点")
    lines.append("9. **收敛与报告打包**：Executive Summary + Why（含历史脉络）+ What（含竞争全景和三剧本）+ How（含路径依赖）+ 附录")
    lines.append("")
    lines.append("脚本调用：`deep_research.py init/update-ledger/record-scenarios/record-premortem/finalize-report --vault <vault> --topic \"<topic>\"`")
    lines.append("")

    return "\n".join(lines)