"""Graph analysis: page scanning and community detection.

Provides shared utilities for Mermaid graph generation and domain subgraphs.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .shared import parse_frontmatter
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
                "meta": meta,
            }
    return pages


def louvain_communities(
    nodes: list[str],
    typed_edges: list[dict[str, str]],
    resolution: float = 1.0,
) -> dict[str, int]:
    """Simplified single-pass Louvain community detection."""
    community: dict[str, int] = {n: i for i, n in enumerate(nodes)}

    adj: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for e in typed_edges:
        src, tgt = e["source"], e["target"]
        if src in community and tgt in community:
            adj[src][tgt] += 1.0
            adj[tgt][src] += 1.0

    total_weight = sum(sum(v.values()) for v in adj.values()) / 2
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
