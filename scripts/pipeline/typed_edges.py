"""Typed edges for the knowledge graph.

Each wiki link is classified into a relationship type:
  belongs_to   — taxonomy page → domain
  mentions     — source/brief → concept/entity/domain
  supports     — stance → source (reinforce)
  contradicts  — stance → source (contradict)
  answers      — source → question
  evolves      — synthesis → source
  tests        — research ledger → question (hypothesis tests question)
  informs      — research report → stance (research informs stance)
"""

from __future__ import annotations

import re
from pathlib import Path

from .shared import parse_frontmatter, section_excerpt

EDGE_TYPES = ("belongs_to", "mentions", "supports", "contradicts", "answers", "evolves", "tests", "informs")

LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")


def classify_edge(source_ref: str, source_meta: dict[str, str], target_ref: str, target_meta: dict[str, str]) -> str:
    """Classify a wiki link between two pages into an edge type."""
    source_type = source_meta.get("type", "")
    target_type = target_meta.get("type", "")

    # Domain membership
    if source_type in ("concept", "entity") and target_ref.startswith("domains/"):
        return "belongs_to"
    if target_type == "concept" and source_ref.startswith("domains/"):
        return "belongs_to"

    # Source → taxonomy
    if source_type in ("source", "brief") and target_ref.startswith(("concepts/", "entities/", "domains/")):
        return "mentions"

    # Stance → source
    if source_type == "stance":
        if target_ref.startswith("sources/"):
            # Check the stance body for impact type
            return "supports"  # default, will be refined below

    # Source answers question
    if source_type == "source" and target_ref.startswith("questions/"):
        return "answers"

    # Synthesis evolves from sources
    if source_type == "synthesis" and target_ref.startswith("sources/"):
        return "evolves"

    # Research hypothesis tests a question
    if source_type == "research-ledger" and target_ref.startswith("questions/"):
        return "tests"

    # Research report informs a stance
    if source_type == "research-report" and target_ref.startswith("stances/"):
        return "informs"

    return "mentions"


def refine_stance_edge(source_path: Path, target_ref: str) -> str:
    """Check stance body to determine if the source link supports or contradicts.

    Priority: update log explicit records > section text matching.
    """
    text = source_path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)

    target_stem = target_ref.split("/", 1)[1] if "/" in target_ref else target_ref

    # Priority 1: check update log for explicit impact records
    update_section = section_excerpt(body, "更新记录")
    for line in update_section.splitlines():
        if target_stem in line:
            if "contradict" in line.lower() or "反驳" in line or "反对" in line:
                return "contradicts"
            if "reinforce" in line.lower() or "支持" in line or "巩固" in line or "extend" in line.lower() or "延伸" in line:
                return "supports"

    # Priority 2: fall back to section text matching
    support_section = section_excerpt(body, "支持证据")
    contradict_section = section_excerpt(body, "反对证据（steel-man）")

    if target_stem in contradict_section:
        return "contradicts"
    if target_stem in support_section:
        return "supports"
    return "supports"


def collect_typed_edges(vault: Path) -> list[dict[str, str]]:
    """Scan the knowledge layer and classify all outbound links into typed edges."""
    knowledge_folders = ("concepts", "entities", "domains", "syntheses", "questions", "stances", "research")
    document_folders = ("sources", "briefs")

    # Collect all pages with metadata
    pages: dict[str, dict[str, str]] = {}
    page_paths: dict[str, Path] = {}

    for folders in (knowledge_folders, document_folders):
        for folder in folders:
            dir_path = vault / "wiki" / folder
            if not dir_path.exists():
                continue
            for path in sorted(dir_path.glob("*.md")):
                ref = f"{folder}/{path.stem}"
                text = path.read_text(encoding="utf-8")
                meta, _ = parse_frontmatter(text)
                if meta.get("graph_include", "true").lower() == "false":
                    continue
                pages[ref] = meta
                page_paths[ref] = path

    edges: list[dict[str, str]] = []

    for source_ref, source_meta in pages.items():
        source_path = page_paths[source_ref]
        text = source_path.read_text(encoding="utf-8")
        links = LINK_PATTERN.findall(text)

        for target_ref in links:
            if target_ref not in pages:
                continue

            target_meta = pages[target_ref]
            edge_type = classify_edge(source_ref, source_meta, target_ref, target_meta)

            # Refine stance edges
            if source_meta.get("type") == "stance" and target_ref.startswith("sources/"):
                edge_type = refine_stance_edge(source_path, target_ref)

            edges.append({
                "source": source_ref,
                "target": target_ref,
                "type": edge_type,
            })

    return edges


def build_typed_graph_page(vault: Path) -> str:
    """Build a typed-edges Mermaid graph view page."""
    from datetime import date
    today = date.today().isoformat()

    edges = collect_typed_edges(vault)

    # Collect nodes from edges
    node_refs = set()
    for edge in edges:
        node_refs.add(edge["source"])
        node_refs.add(edge["target"])

    # Build node metadata
    nodes: dict[str, dict[str, str]] = {}
    for ref in sorted(node_refs):
        folder = ref.split("/", 1)[0]
        stem = ref.split("/", 1)[1]
        path = vault / "wiki" / folder / f"{stem}.md"
        if path.exists():
            text = path.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            nodes[ref] = {
                "label": meta.get("title", "").strip('"') or stem,
                "folder": folder,
            }
        else:
            nodes[ref] = {"label": stem, "folder": folder}

    # Mermaid edge style per type
    EDGE_STYLE = {
        "belongs_to": "--",
        "mentions": "-->",
        "supports": "==>",
        "contradicts": "-.->|contradicts|",
        "answers": "-->|answers|",
        "evolves": "==>|evolves|",
        "tests": "-->|tests|",
        "informs": "==>|informs|",
    }

    id_map = {ref: f"N{idx + 1}" for idx, ref in enumerate(sorted(nodes.keys()))}

    lines = [
        "---",
        'title: "Typed Edges Graph"',
        'type: "system-typed-graph"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        f'generated: "{today}"',
        "---",
        "",
        "# 关系类型图谱",
        "",
        f"> 生成日期：{today}",
        "",
        "## 边类型说明",
        "",
        "| 类型 | 含义 |",
        "|---|---|",
        "| belongs_to | 概念/实体属于某个域 |",
        "| mentions | 来源/简报提及概念/实体/域 |",
        "| supports | 立场支持某个来源 |",
        "| contradicts | 立场反对某个来源 |",
        "| answers | 来源回答了某个问题 |",
        "| evolves | 综合分析源自某个来源 |",
        "| tests | 研究假说测试某个问题 |",
        "| informs | 研究报告影响某个立场 |",
        "",
        "## Mermaid 关系图谱",
        "",
        "```mermaid",
        "graph LR",
    ]

    for ref in sorted(nodes.keys()):
        label = nodes[ref]["label"].replace('"', "'")
        lines.append(f'  {id_map[ref]}["{label}"]')

    for edge in edges:
        style = EDGE_STYLE.get(edge["type"], "-->")
        lines.append(f"  {id_map[edge['source']]} {style} {id_map[edge['target']]}")

    lines.extend(["```", ""])

    # Edge list
    lines.append("## 关系清单")
    lines.append("")
    for edge in edges:
        lines.append(f"- [[{edge['source']}]] → [[{edge['target']}]] ({edge['type']})")
    lines.append("")

    return "\n".join(lines)


def write_typed_graph_page(vault: Path) -> Path:
    """Write wiki/typed-graph.md and return the path."""
    page_path = vault / "wiki" / "typed-graph.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_typed_graph_page(vault)
    page_path.write_text(content, encoding="utf-8")
    return page_path