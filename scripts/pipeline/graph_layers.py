"""Layered subgraph pages for Obsidian graph visualization.

When a wiki grows large, the Obsidian native graph becomes cluttered.
This module creates domain-specific subgraph pages that show only
relevant nodes, using Obsidian's Mermaid code blocks or structured
link sections.

Usage:
    build_domain_subgraph(vault, "AI安全")
    # Creates: wiki/domains/AI安全--子图.md
"""

from __future__ import annotations

import re
from pathlib import Path

from .shared import parse_frontmatter, sanitize_filename


def collect_domain_nodes(
    vault: Path,
    domain_name: str,
) -> dict[str, list[str]]:
    """Collect all nodes related to a domain, grouped by type."""
    nodes: dict[str, list[str]] = {
        "concepts": [],
        "entities": [],
        "sources": [],
        "syntheses": [],
        "briefs": [],
    }

    domain_slug = sanitize_filename(domain_name)
    domain_ref = f"domains/{domain_slug}"

    wiki_dir = vault / "wiki"
    if not wiki_dir.exists():
        return nodes

    # Scan all wiki pages for links to this domain
    for folder_name in ("concepts", "entities", "sources", "syntheses", "briefs"):
        folder = wiki_dir / folder_name
        if not folder.exists():
            continue
        for md_path in sorted(folder.glob("*.md")):
            text = md_path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)

            # Skip if graph_include is false
            if meta.get("graph_include", "true").lower() == "false":
                continue

            # Check if this page references the domain
            if domain_name in body or domain_slug in body or domain_ref in body:
                title = meta.get("title", "").strip('"') or md_path.stem
                nodes[folder_name].append(title)

    return nodes


def build_domain_subgraph_page(
    vault: Path,
    domain_name: str,
) -> str:
    """Build a subgraph visualization page for a domain.

    Creates a Mermaid graph showing only nodes related to this domain,
    grouped by type with color coding.
    """
    nodes = collect_domain_nodes(vault, domain_name)

    # Build Mermaid graph
    mermaid_lines: list[str] = ["graph TD"]

    # Add nodes by type with subgraph grouping
    type_colors = {
        "concepts": "#4A90D9",
        "entities": "#7B68EE",
        "sources": "#2ECC71",
        "syntheses": "#E67E22",
        "briefs": "#95A5A6",
    }
    type_labels = {
        "concepts": "概念",
        "entities": "实体",
        "sources": "来源",
        "syntheses": "综合",
        "briefs": "简报",
    }

    node_id_map: dict[str, str] = {}
    node_counter = 0

    for node_type, titles in nodes.items():
        if not titles:
            continue
        color = type_colors.get(node_type, "#999")
        label = type_labels.get(node_type, node_type)
        mermaid_lines.append(f"    subgraph {label}")
        for title in titles[:10]:  # Limit per type to keep graph readable
            node_id = f"N{node_counter}"
            node_id_map[title] = node_id
            safe_title = title.replace('"', "'")[:30]
            mermaid_lines.append('        {}["{}"]'.format(node_id, safe_title))
            node_counter += 1
        mermaid_lines.append("    end")

    # Add edges from wikilinks between included nodes
    wiki_dir = vault / "wiki"
    added_edges: set[tuple[str, str]] = set()
    for folder_name in nodes:
        folder = wiki_dir / folder_name
        if not folder.exists():
            continue
        for md_path in folder.glob("*.md"):
            text = md_path.read_text(encoding="utf-8")
            _, body = parse_frontmatter(text)
            source_title = None
            for title in nodes[folder_name]:
                if sanitize_filename(title) == md_path.stem:
                    source_title = title
                    break
            if not source_title or source_title not in node_id_map:
                continue

            # Find wikilinks
            links = re.findall(r"\[\[([^\]|]+)", body)
            for link in links:
                link = link.strip()
                if link in node_id_map and link != source_title:
                    edge = (node_id_map[source_title], node_id_map[link])
                    if edge not in added_edges:
                        added_edges.add(edge)
                        mermaid_lines.append(f"    {edge[0]} --> {edge[1]}")

    mermaid_block = "\n".join(mermaid_lines)

    # Build page content
    total_nodes = sum(len(v) for v in nodes.values())
    lines = [
        "---",
        f'title: "{domain_name} 子图"',
        'type: "subgraph"',
        'graph_role: "visualization"',
        'graph_include: "false"',
        f'domain: "{domain_name}"',
        "---",
        "",
        f"# {domain_name} 子图",
        "",
        f"共 {total_nodes} 个相关节点。",
        "",
        "```mermaid",
        mermaid_block,
        "```",
        "",
        "## 节点列表",
        "",
    ]

    for node_type, titles in nodes.items():
        if not titles:
            continue
        label = type_labels.get(node_type, node_type)
        lines.append(f"### {label} ({len(titles)})")
        lines.append("")
        for title in titles:
            lines.append(f"- {title}")
        lines.append("")

    return "\n".join(lines)


def build_all_domain_subgraphs(vault: Path) -> list[Path]:
    """Build subgraph pages for all domains in the vault."""
    domains_dir = vault / "wiki" / "domains"
    if not domains_dir.exists():
        return []

    output_dir = vault / "wiki" / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for domain_path in sorted(domains_dir.glob("*.md")):
        domain_name = domain_path.stem
        page = build_domain_subgraph_page(vault, domain_name)
        out_path = output_dir / f"{sanitize_filename(domain_name)}--子图.md"
        out_path.write_text(page, encoding="utf-8")
        paths.append(out_path)

    return paths
