"""Mermaid static knowledge graph generator.

Produces wiki/knowledge-graph.md with:
- subgraph grouping by community/domain (not flat LR)
- node labels carrying core judgment (not just title)
- bridge/isolated node styling
- narrative summary below the graph
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .shared import parse_frontmatter, section_excerpt
from .typed_edges import collect_typed_edges
from .graph_analysis import scan_pages, louvain_communities, detect_insights

LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")

NODE_STYLE = {
    "sources": "fill:#f0f4f8,stroke:#5a7a96",
    "briefs": "fill:#f5f5f0,stroke:#8a8a6a",
    "concepts": "fill:#f0f5f0,stroke:#5a8a6a",
    "entities": "fill:#f5f0f5,stroke:#8a6a8a",
    "domains": "fill:#f5f3f0,stroke:#8a7a5a",
    "syntheses": "fill:#f0f5f3,stroke:#6a8a7a",
    "stances": "fill:#f5f0f0,stroke:#7a5a5a",
    "questions": "fill:#f0f0f5,stroke:#6a6a8a",
    "comparisons": "fill:#f5f5f0,stroke:#8a8a6a",
}

EDGE_STYLE_MERMAID = {
    "belongs_to": "---",
    "mentions": "-->",
    "supports": "==>",
    "contradicts": "-.->|反驳|",
    "answers": "-->|回答|",
    "evolves": "==>|演化|",
}


def _read_page_excerpt(vault: Path, ref: str) -> str:
    """Read a wiki page and return a one-line excerpt based on type."""
    parts = ref.split("/", 1)
    if len(parts) < 2:
        return ""
    page_path = vault / "wiki" / parts[0] / f"{parts[1]}.md"
    if not page_path.exists():
        return ""
    text = page_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    page_type = meta.get("type", parts[0])

    if page_type == "source":
        excerpt = section_excerpt(body, "核心摘要")
    elif page_type == "brief":
        excerpt = section_excerpt(body, "一句话结论")
    elif page_type == "stance":
        excerpt = section_excerpt(body, "核心判断")
    elif page_type == "question":
        excerpt = section_excerpt(body, "问题")
    elif page_type == "synthesis":
        excerpt = section_excerpt(body, "当前结论")
    else:
        excerpt = ""

    if excerpt:
        # Take first sentence (up to first period/comma)
        for sep in ("。", "；", ".", ";"):
            idx = excerpt.find(sep)
            if idx > 0:
                excerpt = excerpt[:idx + 1]
                break
        return excerpt[:80]
    return ""


def build_mermaid_graph(vault: Path, max_nodes: int = 40) -> str:
    """Build a Mermaid graph page with subgraph grouping and narrative summary."""
    pages = scan_pages(vault)
    typed_edges = collect_typed_edges(vault)

    if not pages:
        return "---\ntitle: Knowledge Graph\ntype: system-graph\n---\n\n# 知识图谱\n\n（知识库为空）\n"

    # Compute simple degree (in+out)
    links: dict[str, set[str]] = {}
    for ref, info in pages.items():
        found: set[str] = set()
        for match in LINK_PATTERN.findall(info.get("body", "")):
            target = match.strip()
            if target in pages:
                found.add(target)
        links[ref] = found

    degree: dict[str, int] = {}
    for src, targets in links.items():
        degree[src] = degree.get(src, 0) + len(targets)
        for t in targets:
            degree[t] = degree.get(t, 0) + 1

    # Compute communities
    node_refs = list(pages.keys())
    communities = louvain_communities(node_refs, typed_edges)

    # Identify bridge nodes and isolated nodes
    adj: dict[str, set[str]] = {n: set() for n in node_refs}
    for e in typed_edges:
        adj.setdefault(e["source"], set()).add(e["target"])
        adj.setdefault(e["target"], set()).add(e["source"])
    for src, targets in links.items():
        for t in targets:
            adj.setdefault(src, set()).add(t)
            adj.setdefault(t, set()).add(src)

    bridge_nodes: set[str] = set()
    isolated_nodes: set[str] = set()
    for node in node_refs:
        if node not in communities:
            continue
        neighbor_comms = set()
        for neighbor in adj.get(node, set()):
            if neighbor in communities:
                neighbor_comms.add(communities[neighbor])
        if len(neighbor_comms) >= 3:
            bridge_nodes.add(node)
        if len(adj.get(node, set())) <= 1:
            isolated_nodes.add(node)

    # Collect contradicts edges for narrative
    contradict_edges = [e for e in typed_edges if e["type"] == "contradicts"]

    # Build community groups
    community_groups: dict[int, list[str]] = {}
    for ref, comm in communities.items():
        community_groups.setdefault(comm, []).append(ref)

    # If no communities detected, group by folder
    if not community_groups:
        for ref in node_refs:
            parts = ref.split("/", 1)
            folder = parts[0] if len(parts) > 1 else "other"
            community_groups.setdefault(hash(folder) % 1000, []).append(ref)

    # Prune to max_nodes by degree
    if len(node_refs) > max_nodes:
        sorted_nodes = sorted(node_refs, key=lambda n: degree.get(n, 0), reverse=True)
        top_nodes = set(sorted_nodes[:max_nodes])
    else:
        top_nodes = set(node_refs)

    # ID mapping (Mermaid-safe IDs)
    id_map: dict[str, str] = {}
    for idx, ref in enumerate(sorted(top_nodes)):
        id_map[ref] = f"N{idx + 1}"

    # Build Mermaid output
    lines = [
        "---",
        'title: "Knowledge Graph"',
        'type: "system-graph"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        f'generated: "{date.today().isoformat()}"',
        "---",
        "",
        "# 知识图谱",
        "",
        f"> 生成日期：{date.today().isoformat()}",
        f"> 节点数：{len(top_nodes)}，社区数：{len(community_groups)}，矛盾边：{len(contradict_edges)}",
        "",
    ]

    # Node type legend
    lines.append("## 节点类型")
    lines.append("")
    lines.append("| 颜色 | 类型 |")
    lines.append("|---|---|")
    lines.append("| 蓝色 | 来源 |")
    lines.append("| 绿色 | 概念 |")
    lines.append("| 紫色 | 实体 |")
    lines.append("| 棕色 | 域 |")
    lines.append("| 红色 | 立场 |")
    lines.append("| 靛色 | 问题 |")
    lines.append("| 青色 | 综合 |")
    lines.append("")

    # Edge type legend
    lines.append("## 关系类型")
    lines.append("")
    lines.append("| 线型 | 含义 |")
    lines.append("|---|---|")
    lines.append("| ── | 属于 |")
    lines.append("| ──> | 提及 |")
    lines.append("| ═══> | 支持 |")
    lines.append("| -··-> 反驳 | 矛盾 |")
    lines.append("| ──> 回答 | 回答 |")
    lines.append("| ═══> 演化 | 演化 |")
    lines.append("")

    # Mermaid graph with subgraphs
    lines.append("## 关系图谱")
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph TB")

    # Generate subgraphs by community
    community_labels: dict[int, str] = {}
    for comm_id, members in sorted(community_groups.items()):
        visible_members = [m for m in members if m in top_nodes]
        if not visible_members:
            continue
        # Use the highest-degree topic/source as community label
        best_member = max(visible_members, key=lambda m: degree.get(m, 0))
        parts = best_member.split("/", 1)
        label = pages.get(best_member, {}).get("title", parts[1] if len(parts) > 1 else best_member)
        # Shorten label for subgraph name
        short_label = label[:20] if len(label) > 20 else label
        # Sanitize for Mermaid subgraph name (no special chars)
        safe_name = re.sub(r'[^A-Za-z0-9一-鿿]', '_', short_label)
        community_labels[comm_id] = short_label

        lines.append(f"    subgraph {safe_name}")
        for ref in sorted(visible_members):
            if ref not in id_map:
                continue
            info = pages.get(ref, {})
            title = info.get("title", ref.split("/", 1)[-1] if "/" in ref else ref)
            # Add excerpt for source/stance/question nodes
            excerpt = _read_page_excerpt(vault, ref)
            if excerpt:
                node_label = f"{title}: {excerpt}"
            else:
                node_label = title
            # Escape quotes
            node_label = node_label.replace('"', "'")
            lines.append(f'        {id_map[ref]}["{node_label}"]')
        lines.append("    end")

    # Isolated nodes outside any subgraph
    for ref in sorted(isolated_nodes):
        if ref not in id_map or ref not in top_nodes:
            continue
        info = pages.get(ref, {})
        title = info.get("title", ref.split("/", 1)[-1] if "/" in ref else ref)
        lines.append(f'    {id_map[ref]}["{title.replace(chr(34), chr(39))}"]')

    # Style definitions
    lines.append("")
    # Node type styles
    for folder, style in NODE_STYLE.items():
        nodes_in_folder = [id_map[ref] for ref in sorted(top_nodes) if ref in id_map and ref.split("/", 1)[0] == folder]
        if nodes_in_folder:
            lines.append(f'    style {" ".join(nodes_in_folder)} {style}')

    # Bridge node style
    bridge_ids = [id_map[ref] for ref in sorted(bridge_nodes) if ref in id_map]
    if bridge_ids:
        lines.append(f'    style {" ".join(bridge_ids)} fill:#fff,stroke:#5a7a96,stroke-width:3px')

    # Isolated node style
    isolated_ids = [id_map[ref] for ref in sorted(isolated_nodes) if ref in id_map]
    if isolated_ids:
        lines.append(f'    style {" ".join(isolated_ids)} fill:#fff,stroke:#c0a0a0,stroke-dasharray: 5 5')

    # Edges
    seen_edges: set[tuple[str, str]] = set()
    for e in typed_edges:
        if e["source"] in top_nodes and e["target"] in top_nodes:
            if (e["source"], e["target"]) in seen_edges:
                continue
            seen_edges.add((e["source"], e["target"]))
            style = EDGE_STYLE_MERMAID.get(e["type"], "-->")
            src_id = id_map.get(e["source"], "")
            tgt_id = id_map.get(e["target"], "")
            if src_id and tgt_id:
                lines.append(f"    {src_id} {style} {tgt_id}")

    # Add remaining wikilinks as generic mentions
    for src, targets in links.items():
        if src not in top_nodes:
            continue
        for tgt in targets:
            if tgt not in top_nodes:
                continue
            if (src, tgt) not in seen_edges:
                src_id = id_map.get(src, "")
                tgt_id = id_map.get(tgt, "")
                if src_id and tgt_id:
                    lines.append(f"    {src_id} --> {tgt_id}")
                    seen_edges.add((src, tgt))

    lines.extend(["```", ""])

    # Narrative summary
    lines.append("## 知识库结构摘要")
    lines.append("")

    # Community summary
    comm_summaries = []
    for comm_id, members in sorted(community_groups.items()):
        visible = [m for m in members if m in top_nodes]
        if not visible:
            continue
        label = community_labels.get(comm_id, f"社区{comm_id}")
        comm_summaries.append(f"{label}({len(visible)})")

    lines.append(f"你的知识库有 **{len(community_groups)} 个主题群落**：" + "、".join(comm_summaries) + "。")
    lines.append("")

    # Bridge nodes
    if bridge_nodes:
        lines.append("**桥梁节点**：" + "、".join(
            pages.get(n, {}).get("title", n.split("/", 1)[-1]) for n in sorted(bridge_nodes) if n in top_nodes
        ) + " 连接了多个社区。")
        lines.append("")

    # Isolated nodes
    if isolated_nodes:
        lines.append("**知识缺口**：" + "、".join(
            pages.get(n, {}).get("title", n.split("/", 1)[-1]) for n in sorted(isolated_nodes) if n in top_nodes
        ) + " 是孤立节点，建议补充相关来源。")
        lines.append("")

    # Contradictions
    if contradict_edges:
        contrad_summaries = []
        for e in contradict_edges[:5]:
            src_title = pages.get(e["source"], {}).get("title", e["source"].split("/", 1)[-1])
            tgt_title = pages.get(e["target"], {}).get("title", e["target"].split("/", 1)[-1])
            contrad_summaries.append(f"{src_title} vs {tgt_title}")
        lines.append("**矛盾**：" + "、".join(contrad_summaries) + " 存在反驳关系。")
        lines.append("")

    return "\n".join(lines)


def write_knowledge_graph(vault: Path, max_nodes: int = 40) -> Path:
    """Write wiki/knowledge-graph.md and return the path."""
    page_path = vault / "wiki" / "knowledge-graph.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_mermaid_graph(vault, max_nodes=max_nodes)
    page_path.write_text(content, encoding="utf-8")
    return page_path