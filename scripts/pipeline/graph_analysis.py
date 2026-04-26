"""Graph analysis: community detection, insights, and data assembly.

Simplified from original three-signal weighting:
- Edges use type distinction only (supports/contradicts/evolves/etc)
- Node degree is simple in+out count
- Community detection uses Louvain on typed edges
- Insights focus on anomalies: bridges, isolated nodes, contradictions
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .shared import parse_frontmatter, section_excerpt
from .typed_edges import collect_typed_edges, LINK_PATTERN


def scan_pages(vault: Path) -> dict[str, dict[str, str]]:
    """Collect metadata for all wiki pages."""
    pages: dict[str, dict[str, str]] = {}
    wiki_dir = vault / "wiki"
    if not wiki_dir.exists():
        return pages
    for folder in wiki_dir.iterdir():
        if not folder.is_dir():
            continue
        for fpath in sorted(folder.glob("*.md")):
            ref = f"{folder.name}/{fpath.stem}"
            text = fpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("graph_include", "true").lower() == "false":
                continue
            pages[ref] = {
                "title": meta.get("title", "").strip('"') or fpath.stem,
                "type": meta.get("type", folder.name),
                "date": meta.get("date", "").strip('"'),
                "folder": folder.name,
                "stem": fpath.stem,
                "body": body,
            }
    return pages


def compute_degree(pages: dict[str, dict[str, str]], typed_edges: list[dict[str, str]]) -> dict[str, int]:
    """Simple in+out degree count from typed edges + wikilinks."""
    degree: dict[str, int] = {}
    for e in typed_edges:
        degree[e["source"]] = degree.get(e["source"], 0) + 1
        degree[e["target"]] = degree.get(e["target"], 0) + 1
    for ref, info in pages.items():
        links = LINK_PATTERN.findall(info.get("body", ""))
        for target in links:
            target = target.strip()
            if target in pages:
                degree[ref] = degree.get(ref, 0) + 1
                degree[target] = degree.get(target, 0) + 1
    return degree


def louvain_communities(nodes: list[str], edges: list[dict[str, str]], resolution: float = 1.0) -> dict[str, int]:
    """Simple Louvain-like community detection.

    Returns {node_ref: community_id}.
    """
    # Initialize each node in its own community
    community: dict[str, int] = {n: i for i, n in enumerate(nodes)}
    adj: dict[str, dict[str, float]] = defaultdict(dict)
    total_weight = 0.0
    for e in edges:
        src, tgt = e["source"], e["target"]
        # Simple weight: 1.0 for all edges
        w = 1.0
        adj[src][tgt] = adj[src].get(tgt, 0) + w
        adj[tgt][src] = adj[tgt].get(src, 0) + w
        total_weight += w

    if total_weight == 0:
        return community

    node_strength: dict[str, float] = {}
    for n in nodes:
        node_strength[n] = sum(adj[n].values())

    improved = True
    iterations = 0
    while improved and iterations < 50:
        improved = False
        iterations += 1
        for node in nodes:
            current_comm = community[node]
            neighbor_comms: dict[int, float] = defaultdict(float)
            for neighbor, weight in adj[node].items():
                if neighbor in community:
                    neighbor_comms[community[neighbor]] += weight

            best_comm = current_comm
            best_delta = 0.0
            for comm, shared_w in neighbor_comms.items():
                if comm == current_comm:
                    continue
                comm_strength = sum(node_strength[n] for n in nodes if community[n] == comm)
                delta = shared_w - resolution * node_strength[node] * comm_strength / total_weight
                if delta > best_delta:
                    best_delta = delta
                    best_comm = comm
            if best_comm != current_comm:
                community[node] = best_comm
                improved = True

    unique_comms = sorted(set(community.values()))
    comm_map = {old: new for new, old in enumerate(unique_comms)}
    return {n: comm_map[c] for n, c in community.items()}


def detect_insights(
    pages: dict[str, dict[str, str]],
    typed_edges: list[dict[str, str]],
    communities: dict[str, int],
) -> list[dict[str, object]]:
    """Detect anomalies: bridge nodes, isolated nodes, cross-community edges."""
    insights: list[dict[str, object]] = []

    adj: dict[str, set[str]] = defaultdict(set)
    for e in typed_edges:
        adj[e["source"]].add(e["target"])
        adj[e["target"]].add(e["source"])

    # Cross-community contradicts edges (highest value anomalies)
    for e in typed_edges:
        src, tgt = e["source"], e["target"]
        if e["type"] == "contradicts" and src in communities and tgt in communities:
            if communities[src] != communities[tgt]:
                insights.append({
                    "type": "cross_community_contradiction",
                    "description": f"[[{src}]] 和 [[{tgt}]] 跨社区矛盾",
                    "nodes": [src, tgt],
                })

    # Bridge nodes: nodes with neighbors in >= 3 communities
    for node in pages:
        if node not in communities:
            continue
        neighbor_comms = set()
        for neighbor in adj[node]:
            if neighbor in communities:
                neighbor_comms.add(communities[neighbor])
        if len(neighbor_comms) >= 3:
            insights.append({
                "type": "bridge_node",
                "description": f"[[{node}]] 连接 {len(neighbor_comms)} 个社区",
                "nodes": [node],
                "bridge_communities": list(neighbor_comms),
            })

    # Isolated nodes
    for node in pages:
        if node not in communities:
            continue
        if len(adj[node]) <= 1:
            insights.append({
                "type": "isolated_node",
                "description": f"[[{node}]] 仅 {len(adj[node])} 个连接",
                "nodes": [node],
            })

    # Contradiction summary
    contradict_count = sum(1 for e in typed_edges if e["type"] == "contradicts")
    if contradict_count > 0:
        insights.append({
            "type": "contradiction_summary",
            "description": f"知识库中有 {contradict_count} 条矛盾关系",
            "count": contradict_count,
        })

    return insights[:15]


def collect_questions(vault: Path) -> list[dict[str, str]]:
    """Scan wiki/questions/ for open/partial questions."""
    questions: list[dict[str, str]] = []
    questions_dir = vault / "wiki" / "questions"
    if not questions_dir.exists():
        return questions
    for qpath in sorted(questions_dir.glob("*.md")):
        text = qpath.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        status = meta.get("status", "open")
        if status not in ("open", "partial"):
            continue
        q_text = section_excerpt(body, "问题") or meta.get("title", "").strip('"') or qpath.stem
        questions.append({
            "id": f"questions/{qpath.stem}",
            "title": meta.get("title", "").strip('"') or qpath.stem,
            "status": status,
            "question_text": q_text[:200],
        })
    return questions


def collect_contradictions(typed_edges: list[dict[str, str]]) -> list[dict[str, str]]:
    """Extract contradicts edges with source/target info."""
    contradictions: list[dict[str, str]] = []
    for e in typed_edges:
        if e["type"] == "contradicts":
            contradictions.append({
                "source": e["source"],
                "target": e["target"],
                "type": "contradicts",
            })
    return contradictions


def build_graph_data(vault: Path) -> dict[str, object]:
    """Build the full graph-data.json structure."""
    pages = scan_pages(vault)
    typed_edges = collect_typed_edges(vault)
    degree = compute_degree(pages, typed_edges)

    node_refs = list(pages.keys())
    communities = louvain_communities(node_refs, typed_edges)
    insights = detect_insights(pages, typed_edges, communities)
    questions = collect_questions(vault)
    contradictions = collect_contradictions(typed_edges)

    # Community size map
    community_sizes: dict[int, int] = defaultdict(int)
    for n, c in communities.items():
        community_sizes[c] += 1

    # Build node list
    nodes = []
    for ref, info in pages.items():
        comm = communities.get(ref, 0)
        nodes.append({
            "id": ref,
            "label": info.get("title", ref),
            "type": info.get("type", ""),
            "folder": info.get("folder", ""),
            "community": comm,
            "date": info.get("date", ""),
            "degree": degree.get(ref, 0),
            "body_excerpt": _extract_excerpt(info),
        })

    # Build edge list (using original types, not mapped to confidence)
    edges = []
    for i, e in enumerate(typed_edges):
        edges.append({
            "id": f"e{i}",
            "source": e["source"],
            "target": e["target"],
            "type": e.get("type", "mentions"),
        })

    # Build community list with labels
    community_labels: dict[int, str] = {}
    for comm_id, members in _group_by_community(communities).items():
        # Use highest-degree member's title as community label
        best = max(members, key=lambda m: degree.get(m, 0))
        label = pages.get(best, {}).get("title", best.split("/", 1)[-1])
        community_labels[comm_id] = label

    return {
        "nodes": nodes,
        "edges": edges,
        "communities": [
            {"id": c, "size": s, "label": community_labels.get(c, f"社区{c}")}
            for c, s in sorted(community_sizes.items())
        ],
        "insights": insights,
        "contradictions": contradictions,
        "questions": questions,
    }


def _extract_excerpt(info: dict[str, str]) -> str:
    """Extract a one-line excerpt from a page based on its type."""
    body = info.get("body", "")
    page_type = info.get("type", "")

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

    return excerpt[:300] if excerpt else ""


def _group_by_community(communities: dict[str, int]) -> dict[int, list[str]]:
    """Group nodes by community id."""
    groups: dict[int, list[str]] = defaultdict(list)
    for ref, comm in communities.items():
        groups[comm].append(ref)
    return dict(groups)


def write_graph_data(vault: Path) -> Path:
    """Write wiki/graph-data.json and return the path."""
    data_path = vault / "wiki" / "graph-data.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_graph_data(vault)
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data_path