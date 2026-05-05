#!/usr/bin/env python
"""Export a knowledge-layer main graph view page for Obsidian."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
KNOWLEDGE_FOLDERS = ("concepts", "entities", "domains", "syntheses")

OBSIDIAN_FILTERS = {
    "filters": [
        {"query": 'path:"wiki/concepts"'},
        {"query": 'path:"wiki/entities"'},
        {"query": 'path:"wiki/domains"'},
        {"query": 'path:"wiki/syntheses"'},
    ],
    "unfilters": [
        {"query": 'path:"wiki/index.md"'},
        {"query": 'path:"wiki/log.md"'},
        {"query": 'path:"wiki/outputs"'},
        {"query": 'path:"wiki/briefs"'},
        {"query": 'path:"wiki/sources"'},
        {"query": 'path:"raw/articles"'},
    ],
}

OBSIDIAN_SEARCH_FILTER = 'path:"wiki/concepts" OR path:"wiki/entities" OR path:"wiki/domains" OR path:"wiki/syntheses"'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a main graph markdown page for the Obsidian LLM wiki.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--output", type=Path, help="Optional explicit output markdown path.")
    parser.add_argument("--typed-edges", action="store_true", help="Also generate wiki/typed-graph.md with classified edge types.")
    parser.add_argument("--write-obsidian-config", action="store_true", help="Write graph filter config into .obsidian/graph.json and saved local graphs.")
    return parser.parse_args()



def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, text[match.end():]


def graph_node_label(path: Path, meta: dict[str, str]) -> str:
    return meta.get("title") or path.stem


def collect_main_graph(vault: Path) -> dict[str, object]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[tuple[str, str]] = []
    for folder in KNOWLEDGE_FOLDERS:
        base = vault / "wiki" / folder
        if not base.exists():
            continue
        for path in sorted(base.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if meta.get("graph_include", "true").lower() == "false":
                continue
            ref = f"{folder}/{path.stem}"
            nodes[ref] = {"label": graph_node_label(path, meta), "folder": folder, "body": body}
    for ref, node in nodes.items():
        for link in LINK_PATTERN.findall(str(node["body"])):
            if link in nodes:
                edge = (ref, link)
                if edge not in edges:
                    edges.append(edge)
        node.pop("body", None)
    return {"nodes": nodes, "edges": edges}


def mermaid_id(index: int) -> str:
    return f"N{index + 1}"


def build_graph_view_page(graph: dict[str, object]) -> str:
    nodes = graph.get("nodes", {})
    edges = graph.get("edges", [])
    refs = list(nodes.keys())
    id_map = {ref: mermaid_id(idx) for idx, ref in enumerate(refs)}
    lines = [
        "---",
        'title: "Main Graph View"',
        'type: "system-graph-view"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        "---",
        "",
        "# 主图谱视角",
        "",
        "这个页面只展示知识层：`concepts / entities / domains / syntheses`。",
        "",
        "## Obsidian 使用",
        "",
        "全局图建议只保留：",
        '- `path:"wiki/concepts"`',
        '- `path:"wiki/entities"`',
        '- `path:"wiki/domains"`',
        '- `path:"wiki/syntheses"`',
        "",
        "全局图建议排除：",
        '- `path:"wiki/index.md"`',
        '- `path:"wiki/log.md"`',
        '- `path:"wiki/outputs"`',
        '- `path:"wiki/briefs"`',
        '- `path:"wiki/sources"`',
        '- `path:"raw/articles"`',
        "",
        "## Mermaid 主图谱",
        "",
        "```mermaid",
        "graph LR",
    ]
    if refs:
        for ref in refs:
            label = str(nodes[ref]["label"]).replace('"', "'")
            lines.append(f'  {id_map[ref]}["{label}"]')
        for source, target in edges:
            lines.append(f"  {id_map[source]} --> {id_map[target]}")
    else:
        lines.append("  Empty[\"暂无知识层节点\"]")
    lines.extend(["```", "", "## 节点清单", ""])
    if refs:
        for ref in refs:
            lines.append(f"- [[{ref}]]")
    else:
        lines.append("- 当前没有可纳入主图谱的知识层页面。")
    lines.append("")
    return "\n".join(lines)


def write_obsidian_graph_config(vault: Path) -> list[str]:
    """Write graph filter config into .obsidian/ so the native graph view only shows knowledge layer.

    Obsidian's graph.json is overwritten on startup, so we use the `search` field
    which persists. We also create a named saved graph view in .obsidian/graphs/.

    Creates:
      - .obsidian/graph.json — global graph with search filter
      - .obsidian/graphs/knowledge-layer.json — saved local graph view
    """
    obsidian_dir = vault / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    written = []

    # Global graph config — use `search` field (persists across Obsidian restarts)
    global_graph_path = obsidian_dir / "graph.json"
    existing = {}
    if global_graph_path.exists():
        try:
            existing = json.loads(global_graph_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing["search"] = OBSIDIAN_SEARCH_FILTER
    existing["hideUnresolved"] = True
    existing["showOrphans"] = False
    global_graph_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append(str(global_graph_path))

    # Saved local graph — ASCII filename for Obsidian compatibility
    graphs_dir = obsidian_dir / "graphs"
    graphs_dir.mkdir(parents=True, exist_ok=True)
    local_graph = {
        "collapse-filter": True,
        "search": OBSIDIAN_SEARCH_FILTER,
        "showTags": False,
        "showAttachments": False,
        "hideUnresolved": True,
        "showOrphans": False,
        "collapse-color-groups": True,
        "colorGroups": [
            {"query": 'path:"wiki/domains"', "color": {"r": 138, "g": 122, "b": 90, "a": 1}},
            {"query": 'path:"wiki/concepts"', "color": {"r": 90, "g": 138, "b": 106, "a": 1}},
            {"query": 'path:"wiki/entities"', "color": {"r": 138, "g": 106, "b": 138, "a": 1}},
            {"query": 'path:"wiki/syntheses"', "color": {"r": 106, "g": 138, "b": 122, "a": 1}},
        ],
        "collapse-display": True,
        "showArrow": True,
        "textFadeMultiplier": -0.5,
        "nodeSizeMultiplier": 1.0,
        "lineSizeMultiplier": 1.0,
        "collapse-forces": True,
        "centerStrength": 0.55,
        "repelStrength": 10.0,
        "linkStrength": 1.0,
        "linkDistance": 250,
        "scale": 0.8,
        "close": True,
    }
    local_graph_path = graphs_dir / "knowledge-layer.json"
    local_graph_path.write_text(json.dumps(local_graph, ensure_ascii=False, indent=2), encoding="utf-8")
    written.append(str(local_graph_path))

    return written


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    output = args.output.resolve() if args.output else (vault / "wiki" / "graph-view.md")
    graph = collect_main_graph(vault)
    page = build_graph_view_page(graph)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    result = {"output": str(output), "node_count": len(graph["nodes"]), "edge_count": len(graph["edges"])}

    if args.typed_edges:
        from pipeline.typed_edges import write_typed_graph_page
        typed_path = write_typed_graph_page(vault)
        result["typed_graph"] = str(typed_path)

    if args.write_obsidian_config:
        config_paths = write_obsidian_graph_config(vault)
        result["obsidian_config"] = config_paths

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
