"""Deep research orchestration: init, collect vault evidence, record artifacts, finalize.

Coordinates the 9-phase research protocol via host-agent-first pattern:
scripts prepare context and persist artifacts, the host agent (LLM) does the reasoning.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .shared import parse_frontmatter, section_excerpt, sanitize_filename
from .dependency_ledger import (
    research_slug,
    init_ledger_page,
    read_ledger,
    add_fact_node,
    update_hypothesis_confidence,
    check_evidence_sufficiency,
    _ledger_path,
    _context_path,
    _scenarios_path,
    _premortem_path,
    _report_path,
)


def init_research_project(
    vault: Path,
    topic: str,
    hypotheses: list[dict],
) -> dict:
    """Initialize a deep-research project.

    Creates: ledger page + context page.
    Returns: {"ledger_path": str, "context_path": str, "slug": str}
    """
    slug = research_slug(topic)
    ledger_path = init_ledger_page(vault, topic, hypotheses)

    # Create context page with hypothesis cards and initial vault briefing
    today = date.today().isoformat()
    h_cards: list[str] = []
    for i, h in enumerate(hypotheses, 1):
        claim = h.get("claim", "")
        h_type = h.get("type", "causal")
        conf = h.get("confidence", 25)
        confirm = h.get("confirm_queries", [])
        contradict = h.get("contradict_queries", [])
        confirm_def = h.get("confirm_evidence", "")
        contradict_def = h.get("contradict_evidence", "")
        h_cards.append(
            f"### H-{i:02d}: {claim}\n\n"
            f"- 类型: {h_type}\n"
            f"- 初始置信度: {conf}%\n"
            f"- 确认证据定义: {confirm_def}\n"
            f"- 反驳证据定义: {contradict_def}\n"
            f"- 确认查询: {', '.join(confirm)}\n"
            f"- 反驳查询: {', '.join(contradict)}\n\n"
        )

    context_content = (
        f"---\n"
        f'title: "{topic} 研究上下文"\n'
        f'type: "research-context"\n'
        f'graph_role: "research"\n'
        f'graph_include: "false"\n'
        f'lifecycle: "working"\n'
        f'research_topic: "{topic}"\n'
        f'status: "active"\n'
        f'created: "{today}"\n'
        f'---\n\n'
        f"# {topic} 研究上下文\n\n"
        f"> 创建日期：{today}\n\n"
        f"## 假说卡片\n\n"
        + "\n".join(h_cards) +
        f"\n## 需求审计\n\n"
        f"（宿主 Agent 填写：表面需求 / 操作需求 / 本质需求）\n\n"
        f"## Vault Briefing\n\n"
        f"（宿主 Agent 填写：vault 已有知识概要）\n\n"
        f"## 校准块\n\n"
        f"### 共识\n\n（待填充）\n\n"
        f"### 边界\n\n（待填充）\n\n"
        f"### 争议\n\n（待填充）\n\n"
        f"### 假说结果\n\n（待填充）\n\n"
    )
    ctx_path = _context_path(vault, slug)
    ctx_path.write_text(context_content, encoding="utf-8")

    return {
        "ledger_path": str(ledger_path),
        "context_path": str(ctx_path),
        "slug": slug,
    }


def collect_vault_evidence(vault: Path, topic: str, hypothesis_claims: list[str]) -> dict:
    """Collect vault evidence for each hypothesis claim.

    Returns structured evidence per hypothesis: {claim: {confirming: [...], contradicting: [...], neutral: [...]}}
    """
    evidence: dict[str, dict] = {}

    # Gather existing source/stance/synthesis/question pages
    folders = {
        "sources": vault / "wiki" / "sources",
        "stances": vault / "wiki" / "stances",
        "questions": vault / "wiki" / "questions",
        "syntheses": vault / "wiki" / "syntheses",
        "briefs": vault / "wiki" / "briefs",
    }

    for claim in hypothesis_claims:
        claim_terms = [t for t in re.findall(r"[一-鿿]{2,8}|[A-Za-z0-9\-\+]{2,}", claim) if len(t) >= 2]
        confirming: list[dict] = []
        contradicting: list[dict] = []
        neutral: list[dict] = []

        for folder_name, folder_path in folders.items():
            if not folder_path.exists():
                continue
            for fpath in sorted(folder_path.glob("*.md")):
                text = fpath.read_text(encoding="utf-8")
                meta, body = parse_frontmatter(text)
                title = meta.get("title", "").strip('"') or fpath.stem

                score = sum(1 for t in claim_terms if t in text)
                if score == 0:
                    continue

                # Classify by contradiction keywords
                relation = section_excerpt(body, "与现有知识库的关系")
                stance_judgement = section_excerpt(body, "核心判断")
                oppose_evidence = section_excerpt(body, "反对证据（steel-man）")

                is_contradicting = (
                    "冲突" in relation or "矛盾" in relation or "反驳" in relation
                    or "反对" in stance_judgement or "挑战" in stance_judgement
                    or (oppose_evidence and "暂无" not in oppose_evidence and claim_terms and
                        any(t in oppose_evidence for t in claim_terms))
                )

                entry = {
                    "ref": f"{folder_name}/{fpath.stem}",
                    "title": title,
                    "type": meta.get("type", folder_name),
                    "score": score,
                    "excerpt": (section_excerpt(body, "核心摘要") or section_excerpt(body, "当前结论") or section_excerpt(body, "一句话结论") or body[:300])[:200],
                }

                if is_contradicting:
                    contradicting.append(entry)
                elif score >= 2:
                    confirming.append(entry)
                else:
                    neutral.append(entry)

        evidence[claim] = {
            "confirming": confirming[:5],
            "contradicting": contradicting[:3],
            "neutral": neutral[:3],
        }

    return evidence


def record_scenarios(
    vault: Path,
    topic: str,
    scenarios: list[dict],
) -> Path:
    """Record scenario stress test table as a vault page."""
    slug = research_slug(topic)
    path = _scenarios_path(vault, slug)
    today = date.today().isoformat()

    lines: list[str] = [
        f"---",
        f'title: "{topic} 情景压力测试"',
        f'type: "research-scenarios"',
        f'graph_role: "research"',
        f'graph_include: "false"',
        f'lifecycle: "working"',
        f'research_topic: "{topic}"',
        f'created: "{today}"',
        f'---',
        f"",
        f"# {topic} 情景压力测试",
        f"",
        f"> 生成日期：{today}",
        f"",
    ]

    # Table format
    lines.append("| 结论 | 基准情景 | 压力 A | 压力 B | 复合 | 边界条件 |")
    lines.append("|---|---|---|---|---|---|")

    for s in scenarios:
        conclusion = s.get("conclusion", "")
        base = s.get("base_case", "-")
        stress_a = s.get("stress_a", "-")
        stress_b = s.get("stress_b", "-")
        compound = s.get("compound", "-")
        boundary = s.get("boundary_condition", "-")
        lines.append(f"| {conclusion} | {base} | {stress_a} | {stress_b} | {compound} | {boundary} |")

    lines.append("")
    lines.append("## 情景详述")
    lines.append("")
    for s in scenarios:
        lines.append(f"### {s.get('conclusion', '')}")
        for key in ("base_case", "stress_a", "stress_b", "compound"):
            val = s.get(key, "")
            if val and val != "-":
                lines.append(f"- **{key}**: {val}")
        if s.get("boundary_condition"):
            lines.append(f"- **边界条件**: {s['boundary_condition']}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def record_premortem(
    vault: Path,
    topic: str,
    premortem: list[dict],
) -> Path:
    """Record pre-mortem failure scenarios as a vault page."""
    slug = research_slug(topic)
    path = _premortem_path(vault, slug)
    today = date.today().isoformat()

    lines: list[str] = [
        f"---",
        f'title: "{topic} 预验尸"',
        f'type: "research-premortem"',
        f'graph_role: "research"',
        f'graph_include: "false"',
        f'lifecycle: "working"',
        f'research_topic: "{topic}"',
        f'created: "{today}"',
        f'---',
        f"",
        f"# {topic} 预验尸",
        f"",
        f"> 生成日期：{today}",
        f"",
        f"> 假设主要建议已失败，以下是可能的失败路径。",
        f"",
    ]

    for i, failure in enumerate(premortem, 1):
        scenario = failure.get("scenario", "")
        mechanism = failure.get("mechanism", "")
        ledger_root = failure.get("ledger_root", "")
        resolution = failure.get("resolution", "")
        lines.append(f"### 失败情景 {i}: {scenario}")
        lines.append(f"- **机制**: {mechanism}")
        if ledger_root:
            lines.append(f"- **账本根节点**: {ledger_root}")
        if resolution:
            lines.append(f"- **应对措施**: {resolution}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def finalize_report(
    vault: Path,
    topic: str,
    report_markdown: str,
) -> Path:
    """Write the final deep research report page."""
    slug = research_slug(topic)
    path = _report_path(vault, slug)
    today = date.today().isoformat()

    # Count evidence nodes from ledger
    ledger = read_ledger(vault, topic)
    f_count = len([n for n in ledger["nodes"].values() if n.get("type") == "F"])
    h_count = len([n for n in ledger["nodes"].values() if n.get("type") == "H"])
    c_stable = len([n for n in ledger["nodes"].values()
                    if n.get("type") == "C" and int(n.get("confidence", "0")) >= 70])
    c_working = len([n for n in ledger["nodes"].values()
                     if n.get("type") == "C" and int(n.get("confidence", "0")) < 70
                     and int(n.get("confidence", "0")) >= 40])

    frontmatter = (
        f"---\n"
        f'title: "{topic} 深度研究报告"\n'
        f'type: "research-report"\n'
        f'graph_role: "knowledge"\n'
        f'graph_include: "true"\n'
        f'lifecycle: "official"\n'
        f'research_topic: "{topic}"\n'
        f'status: "seed"\n'
        f'created: "{today}"\n'
        f'last_updated: "{today}"\n'
        f'source_count: "{f_count}"\n'
        f'hypothesis_count: "{h_count}"\n'
        f'stable_conclusion_count: "{c_stable}"\n'
        f'working_hypothesis_count: "{c_working}"\n'
        f'---\n\n'
    )

    path.write_text(frontmatter + report_markdown + "\n", encoding="utf-8")
    return path


def resume_research_project(vault: Path, topic: str) -> dict:
    """Resume an existing deep-research project by reading its ledger and context.

    Returns: dict with completed phases, hypothesis confidences,
             pending phases, and context summary for the host agent.
    """
    slug = research_slug(topic)

    ledger_path = _ledger_path(vault, slug)
    if not ledger_path.exists():
        return {"error": f"No research project found for topic '{topic}' (slug: {slug})"}

    ledger = read_ledger(vault, topic)
    context_path = _context_path(vault, slug)

    # Analyze completed phases based on existing artifacts
    completed_phases: list[str] = []
    if ledger_path.exists():
        completed_phases.append("init")
    if context_path.exists():
        completed_phases.append("intent-expansion")
    # Check for vault evidence (Phase 3)
    nodes = ledger.get("nodes", {})
    f_nodes = [n for n in nodes.values() if n.get("type") == "F"]
    if f_nodes:
        completed_phases.append("vault-evidence-collection")
    # Check scenarios (Phase 7)
    if _scenarios_path(vault, slug).exists():
        completed_phases.append("scenario-stress-test")
    # Check premortem (Phase 8)
    if _premortem_path(vault, slug).exists():
        completed_phases.append("premortem")
    # Check report (Phase 9)
    if _report_path(vault, slug).exists():
        completed_phases.append("finalize-report")

    # Collect hypothesis current confidences
    hypothesis_states: list[dict] = []
    for nid, node in nodes.items():
        if node.get("type") == "H":
            hypothesis_states.append({
                "id": nid,
                "claim": node.get("claim", ""),
                "confidence": int(node.get("confidence", "0")),
                "status": "stable" if int(node.get("confidence", "0")) >= 70 else "working",
            })

    # Determine pending phases
    all_phases = [
        "init", "intent-expansion", "hypothesis-formation",
        "vault-evidence-collection", "web-research", "calibration",
        "root-questions", "scenario-stress-test", "premortem", "finalize-report",
    ]
    pending_phases = [p for p in all_phases if p not in completed_phases]

    # Read context page summary if it exists
    context_summary = ""
    if context_path.exists():
        ctx_text = context_path.read_text(encoding="utf-8")
        _, ctx_body = parse_frontmatter(ctx_text)
        context_summary = ctx_body[:500].strip()

    # Check sufficiency gate
    sufficiency = check_evidence_sufficiency(vault, topic)

    return {
        "topic": topic,
        "slug": slug,
        "completed_phases": completed_phases,
        "pending_phases": pending_phases,
        "hypothesis_states": hypothesis_states,
        "fact_node_count": len(f_nodes),
        "sufficiency_gate": "PASS" if sufficiency["passed"] else "BLOCKED",
        "sufficiency_violations": sufficiency.get("violations", []),
        "context_summary": context_summary,
        "ledger_path": str(ledger_path),
        "context_path": str(context_path) if context_path.exists() else "",
    }


def update_closure(vault: Path, topic: str) -> dict:
    """Update question pages, stance pages, index, log, and graph after research completion."""
    slug = research_slug(topic)
    ledger = read_ledger(vault, topic)

    # Collect resolved hypotheses → map to question pages
    resolved_questions: list[str] = []
    for nid, node in ledger["nodes"].items():
        if node.get("type") == "H":
            conf = int(node.get("confidence", "0"))
            if conf >= 70:
                resolved_questions.append(node.get("claim", ""))

    # Collect stance impacts from F nodes
    stance_updates: list[dict] = []
    for nid, node in ledger["nodes"].items():
        if node.get("type") != "F":
            continue
        source = node.get("source", "")
        claim = node.get("claim", "")
        # Heuristic: detect reinforce/contradict/extend keywords
        impact_type = "neutral"
        if any(kw in claim for kw in ("确认", "支持", "巩固", "验证")):
            impact_type = "reinforce"
        elif any(kw in claim for kw in ("反驳", "矛盾", "冲突", "否定")):
            impact_type = "contradict"
        elif any(kw in claim for kw in ("扩展", "补充", "延伸")):
            impact_type = "extend"
        stance_updates.append({"source": source, "impact": impact_type, "claim": claim})

    # Append to wiki/log.md
    log_path = vault / "wiki" / "log.md"
    today = date.today().isoformat()
    log_entry = (
        f"- **{today}** 深度研究完成：{topic}\n"
        f"  - 事实节点: {len([n for n in ledger['nodes'].values() if n.get('type') == 'F'])}\n"
        f"  - 结论节点: {len([n for n in ledger['nodes'].values() if n.get('type') == 'C'])}\n"
        f"  - 报告页: [[research/{slug}--report]]\n"
        f"  - 依赖账本: [[research/{slug}--ledger]]\n"
    )
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8")
        log_text += log_entry
        log_path.write_text(log_text, encoding="utf-8")

    # Update wiki/hot.md
    hot_path = vault / "wiki" / "hot.md"
    hot_entry = f"- {today}: 深度研究「{topic}」完成 → [[research/{slug}--report]]\n"
    if hot_path.exists():
        hot_text = hot_path.read_text(encoding="utf-8")
        # Replace first line if it starts with a date
        lines = hot_text.splitlines()
        if lines and lines[0].startswith("- 20"):
            lines[0] = hot_entry
        else:
            lines.insert(0, hot_entry)
        hot_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "resolved_questions": resolved_questions,
        "stance_updates": stance_updates,
    }