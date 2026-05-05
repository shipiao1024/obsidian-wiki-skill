"""Dependency ledger for deep-research projects.

Manages an evidence dependency graph as vault pages in wiki/research/.
Node types: F (Fact), I (Inference), A (Assumption), H (Hypothesis),
C (Conclusion), G (Gap), D (Disputed).

Each node carries: ID, Type, Claim, Source, Depends_on, Required_by,
Confidence (ordinal), Status.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .shared import parse_frontmatter, sanitize_filename

NODE_TYPES = ("F", "I", "A", "H", "C", "G", "D")

NODE_TYPE_LABELS = {
    "F": "事实",
    "I": "推理",
    "A": "假设",
    "H": "假说",
    "C": "结论",
    "G": "差距",
    "D": "争议",
}

# Ordinal confidence model (replaces percentage-based labels)
ORDINAL_LEVELS = ("Seeded", "Preliminary", "Working", "Supported", "Stable")
_ORDINAL_RANK = {name: i for i, name in enumerate(ORDINAL_LEVELS)}


def confidence_label(value: str | int) -> str:
    """Return the ordinal confidence label.

    Accepts either an ordinal string or a legacy percentage (int).
    For percentage input, maps to ordinal: 0-19=Seeded, 20-39=Preliminary,
    40-59=Working, 60-79=Supported, 80+=Stable.
    """
    if isinstance(value, str):
        if value in _ORDINAL_RANK:
            return value
        # Try parsing as int
        try:
            value = int(value)
        except (ValueError, TypeError):
            return "Preliminary"
    if isinstance(value, int):
        if value < 20:
            return "Seeded"
        if value < 40:
            return "Preliminary"
        if value < 60:
            return "Working"
        if value < 80:
            return "Supported"
        return "Stable"
    return "Preliminary"


def ordinal_min(a: str, b: str) -> str:
    """Return the lower of two ordinal confidence levels."""
    return a if _ORDINAL_RANK.get(a, 0) <= _ORDINAL_RANK.get(b, 0) else b


def research_slug(topic: str) -> str:
    return sanitize_filename(topic.strip(), max_length=80)


def _ledger_path(vault: Path, slug: str) -> Path:
    d = vault / "wiki" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{slug}--ledger.md"


def _context_path(vault: Path, slug: str) -> Path:
    d = vault / "wiki" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{slug}--context.md"


def _scenarios_path(vault: Path, slug: str) -> Path:
    d = vault / "wiki" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{slug}--scenarios.md"


def _premortem_path(vault: Path, slug: str) -> Path:
    d = vault / "wiki" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{slug}--premortem.md"


def _report_path(vault: Path, slug: str) -> Path:
    d = vault / "wiki" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{slug}--report.md"


# ---------------------------------------------------------------------------
# Ledger page: init / read / update
# ---------------------------------------------------------------------------

def init_ledger_page(vault: Path, topic: str, hypotheses: list[dict]) -> Path:
    """Create a dependency ledger page with initial H nodes."""
    slug = research_slug(topic)
    path = _ledger_path(vault, slug)
    if path.exists():
        return path

    today = date.today().isoformat()
    h_lines: list[str] = []
    for i, h in enumerate(hypotheses, 1):
        claim = h.get("claim", "")
        h_type = h.get("type", "causal")
        conf = h.get("confidence", "Preliminary")
        if isinstance(conf, int):
            conf_label = confidence_label(conf)
        else:
            conf_label = confidence_label(str(conf))
        confirm_queries = h.get("confirm_queries", [])
        contradict_queries = h.get("contradict_queries", [])
        h_lines.append(f"- H-{i:02d}: {claim} | 类型: {h_type} | 置信度: {conf_label}")
        if confirm_queries:
            h_lines.append(f"  确认查询: {', '.join(confirm_queries)}")
        if contradict_queries:
            h_lines.append(f"  反驳查询: {', '.join(contradict_queries)}")

    content = (
        f"---\n"
        f'title: "{topic} 依赖账本"\n'
        f'type: "research-ledger"\n'
        f'graph_role: "research"\n'
        f'graph_include: "false"\n'
        f'lifecycle: "official"\n'
        f'research_topic: "{topic}"\n'
        f'status: "active"\n'
        f'created: "{today}"\n'
        f'last_updated: "{today}"\n'
        f'hypothesis_count: "{len(hypotheses)}"\n'
        f'fact_count: "0"\n'
        f'conclusion_count: "0"\n'
        f'---\n\n'
        f"# {topic} 依赖账本\n\n"
        f"> 创建日期：{today}\n\n"
        f"## 假说节点 (H)\n\n"
        + "\n".join(h_lines) + "\n\n"
        f"## 事实节点 (F)\n\n"
        f"（待研究轮次填充）\n\n"
        f"## 推理节点 (I)\n\n"
        f"（待填充）\n\n"
        f"## 假设节点 (A)\n\n"
        f"（待填充）\n\n"
        f"## 结论节点 (C)\n\n"
        f"（待填充）\n\n"
        f"## 差距节点 (G)\n\n"
        f"（待填充）\n\n"
        f"## 争议节点 (D)\n\n"
        f"（待填充）\n\n"
        f"## 更新记录\n\n"
        f"- {today}: 初始创建，{len(hypotheses)} 个假说\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def read_ledger(vault: Path, topic: str) -> dict:
    """Read a ledger page and parse all nodes into a structured dict."""
    slug = research_slug(topic)
    path = _ledger_path(vault, slug)
    if not path.exists():
        return {"nodes": {}, "meta": {}}

    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)

    nodes: dict[str, dict] = {}
    current_type = ""

    for line in body.splitlines():
        heading_match = re.match(r"^##\s+(事实|推理|假设|假说|结论|差距|争议)节点", line)
        if heading_match:
            label = heading_match.group(1)
            current_type = {v: k for k, v in NODE_TYPE_LABELS.items()}.get(label, "")
            continue

        node_match = re.match(r"^- ([FISHCDG]-\d+):\s*(.*)", line)
        if node_match and current_type:
            nid = node_match.group(1)
            rest = node_match.group(2)
            parts = [p.strip() for p in rest.split("|")]
            claim = parts[0] if parts else ""
            node_info: dict[str, str] = {"id": nid, "type": current_type, "claim": claim}
            for part in parts[1:]:
                if part.startswith("来源:"):
                    node_info["source"] = part[len("来源:"):].strip()
                elif part.startswith("依赖:"):
                    node_info["depends_on"] = part[len("依赖:"):].strip()
                elif part.startswith("被依赖:"):
                    node_info["required_by"] = part[len("被依赖:"):].strip()
                elif part.startswith("置信度:"):
                    # Try ordinal label first, then percentage
                    conf_str = part[len("置信度:"):].strip()
                    ordinal_match = re.search(r"(Seeded|Preliminary|Working|Supported|Stable)", conf_str)
                    if ordinal_match:
                        node_info["confidence"] = ordinal_match.group(1)
                    else:
                        pct_match = re.search(r"(\d+)", conf_str)
                        if pct_match:
                            node_info["confidence"] = confidence_label(int(pct_match.group(1)))
                elif part.startswith("类型:"):
                    node_info["hypothesis_type"] = part[len("类型:"):].strip()
                elif part.startswith("边界:"):
                    node_info["boundary"] = part[len("边界:"):].strip()
                elif part.startswith("状态:"):
                    node_info["status"] = part[len("状态:"):].strip()
            nodes[nid] = node_info

    return {"nodes": nodes, "meta": meta}


def add_fact_node(
    vault: Path,
    topic: str,
    claim: str,
    source: str,
    tier: int = 2,
    depends_on: str = "",
    required_by: str = "",
) -> str:
    """Add an F node to the ledger. Returns the node ID."""
    slug = research_slug(topic)
    path = _ledger_path(vault, slug)
    ledger = read_ledger(vault, topic)

    existing_f = [nid for nid in ledger["nodes"] if nid.startswith("F-")]
    next_num = max(int(nid.split("-")[1]) for nid in existing_f) + 1 if existing_f else 1
    nid = f"F-{next_num:02d}"

    today = date.today().isoformat()
    tier_label = f"Tier {tier}"
    node_line = f"- {nid}: {claim} | 来源: {source} | {tier_label}"
    if depends_on:
        node_line += f" | 依赖: {depends_on}"
    if required_by:
        node_line += f" | 被依赖: {required_by}"

    text = path.read_text(encoding="utf-8")
    f_section_marker = "## 事实节点 (F)\n\n"

    if "（待研究轮次填充）" in text:
        text = text.replace("（待研究轮次填充）", node_line + "\n")
    else:
        text = text.replace(f_section_marker, f_section_marker + node_line + "\n")

    # Update frontmatter fact_count
    fact_count = len(existing_f) + 1
    text = re.sub(r'fact_count: "\d+"', f'fact_count: "{fact_count}"', text)
    text = re.sub(r'last_updated: "\d{4}-\d{2}-\d{2}"', f'last_updated: "{today}"', text)

    # Append to update log
    text += f"- {today}: 添加 {nid}: {claim[:60]}\n"

    path.write_text(text, encoding="utf-8")
    return nid


def update_hypothesis_confidence(
    vault: Path,
    topic: str,
    hypothesis_id: str,
    new_confidence: str,
    reason: str = "",
) -> None:
    """Update an H node's confidence in the ledger.

    new_confidence should be an ordinal label: Seeded/Preliminary/Working/Supported/Stable.
    Legacy int values are accepted and converted via confidence_label().
    """
    slug = research_slug(topic)
    path = _ledger_path(vault, slug)
    text = path.read_text(encoding="utf-8")
    today = date.today().isoformat()

    if isinstance(new_confidence, int):
        conf_label = confidence_label(new_confidence)
    else:
        conf_label = confidence_label(str(new_confidence))

    # Find and replace the confidence field for the specific H node
    # Matches both old format (% (Label)) and new format (Label)
    pattern = re.compile(
        rf"(- {re.escape(hypothesis_id)}: .*?)\| 置信度: (?:\d+% \(\w+\)|\w+)"
    )
    match = pattern.search(text)
    if match:
        old_part = match.group(1)
        new_part = f"{old_part}| 置信度: {conf_label}"
        text = text.replace(match.group(0), new_part)

    text = re.sub(r'last_updated: "\d{4}-\d{2}-\d{2}"', f'last_updated: "{today}"', text)
    text += f"- {today}: {hypothesis_id} 置信度 → {conf_label}"
    if reason:
        text += f" — {reason[:80]}"
    text += "\n"

    path.write_text(text, encoding="utf-8")


def propagate_confidence(vault: Path, topic: str) -> dict[str, str]:
    """Propagate confidence through the dependency graph.

    Rule: a Conclusion node's confidence <= min confidence of its dependency chain.

    Returns a dict of {node_id: propagated_ordinal} for nodes that changed.
    """
    ledger = read_ledger(vault, topic)
    nodes = ledger["nodes"]

    # Build dependency graph
    deps: dict[str, list[str]] = {}
    for nid, node in nodes.items():
        dep_str = node.get("depends_on", "")
        if dep_str:
            deps[nid] = [d.strip() for d in dep_str.split(",") if d.strip()]

    changed: dict[str, str] = {}
    # Propagate for C (Conclusion) and I (Inference) nodes
    for nid, node in nodes.items():
        if node.get("type") not in ("C", "I"):
            continue
        dep_ids = deps.get(nid, [])
        if not dep_ids:
            continue
        dep_ordinals = []
        for dep_id in dep_ids:
            if dep_id in nodes:
                conf_str = nodes[dep_id].get("confidence", "Preliminary")
                dep_ordinals.append(conf_str)
        if dep_ordinals:
            propagated = dep_ordinals[0]
            for d in dep_ordinals[1:]:
                propagated = ordinal_min(propagated, d)
            current_conf = node.get("confidence", "Preliminary")
            if _ORDINAL_RANK.get(propagated, 0) < _ORDINAL_RANK.get(current_conf, 0):
                changed[nid] = propagated
                update_hypothesis_confidence(vault, topic, nid, propagated,
                                             reason=f"依赖链传播（min={propagated}）")

    return changed


def check_evidence_sufficiency(vault: Path, topic: str) -> dict:
    """Check whether the evidence sufficiency gate passes.

    Gate rules:
    1. All H nodes have been updated with findings (not Preliminary)
    2. Every branch has at least one F node
    3. No C node depends solely on A nodes
    4. Dispute block is populated (not empty placeholder)

    Returns {passed: bool, violations: list[str]}
    """
    ledger = read_ledger(vault, topic)
    nodes = ledger["nodes"]
    violations: list[str] = []

    h_nodes = {nid: n for nid, n in nodes.items() if n.get("type") == "H"}
    f_nodes = {nid: n for nid, n in nodes.items() if n.get("type") == "F"}
    c_nodes = {nid: n for nid, n in nodes.items() if n.get("type") == "C"}
    a_nodes = {nid: n for nid, n in nodes.items() if n.get("type") == "A"}
    d_nodes = {nid: n for nid, n in nodes.items() if n.get("type") == "D"}

    # Check 1: No H node still at Seeded (no evidence backing)
    for nid, node in h_nodes.items():
        conf = node.get("confidence", "Seeded")
        if conf == "Seeded":
            violations.append(f"{nid} 置信度仍为 Seeded（无证据支撑）")

    # Check 2: Every H node has at least one F node in its dependency
    for nid, node in h_nodes.items():
        dep_str = node.get("depends_on", "")
        if dep_str:
            dep_ids = [d.strip() for d in dep_str.split(",")]
            has_f = any(d in f_nodes for d in dep_ids)
            if not has_f:
                violations.append(f"{nid} 无 F 节点支持")
        elif not f_nodes:
            violations.append(f"{nid} 无任何 F 节点关联")

    # Check 3: No C node depends solely on A nodes
    for nid, node in c_nodes.items():
        dep_str = node.get("depends_on", "")
        if dep_str:
            dep_ids = [d.strip() for d in dep_str.split(",")]
            only_a = all(d in a_nodes for d in dep_ids)
            if only_a and dep_ids:
                violations.append(f"{nid} 仅依赖假设节点，缺乏事实支撑")

    # Check 4: Dispute block not empty
    if not d_nodes:
        slug = research_slug(topic)
        path = _ledger_path(vault, slug)
        text = path.read_text(encoding="utf-8")
        if "（待填充）" in text.split("## 争议节点 (D)")[1].split("##")[0]:
            violations.append("争议块为空，需记录至少一个争议点")

    return {"passed": len(violations) == 0, "violations": violations}


def scan_active_research(vault: Path) -> list[dict]:
    """Scan wiki/research/ for active research projects."""
    research_dir = vault / "wiki" / "research"
    if not research_dir.exists():
        return []

    projects: list[dict] = []
    for path in sorted(research_dir.glob("*--ledger.md")):
        text = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        if meta.get("status") in ("active", "completed"):
            projects.append({
                "topic": meta.get("research_topic", "").strip('"'),
                "slug": path.stem.replace("--ledger", ""),
                "status": meta.get("status", "active"),
                "created": meta.get("created", ""),
                "last_updated": meta.get("last_updated", ""),
                "hypothesis_count": meta.get("hypothesis_count", "0"),
                "fact_count": meta.get("fact_count", "0"),
            })

    return projects


def surgical_rollback(vault: Path, topic: str, node_id: str, reason: str = "") -> list[str]:
    """Roll back confidence for a node and propagate the impact downstream.

    Sets the node's confidence to 0 and propagates through dependents.
    Returns list of affected node IDs.
    """
    ledger = read_ledger(vault, topic)
    nodes = ledger["nodes"]

    # Find all nodes that depend on the rolled-back node
    affected: list[str] = [node_id]
    for nid, node in nodes.items():
        dep_str = node.get("depends_on", "")
        if dep_str and node_id in [d.strip() for d in dep_str.split(",")]:
            affected.append(nid)

    # Roll back: set confidence to Seeded for the root node
    update_hypothesis_confidence(vault, topic, node_id, "Seeded",
                                 reason=f"手术式回滚: {reason[:60]}")

    # Propagate impact
    propagated = propagate_confidence(vault, topic)

    return affected + list(propagated.keys())