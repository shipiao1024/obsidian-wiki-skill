#!/usr/bin/env python
"""Backfill graph_role / graph_include metadata for wiki pages."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
WIKI_FOLDERS = ["sources", "briefs", "concepts", "entities", "domains", "syntheses", "outputs"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill graph metadata for the Obsidian LLM wiki.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
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


def render_frontmatter(meta: dict[str, str]) -> str:
    order = [
        "title",
        "type",
        "status",
        "fidelity",
        "graph_role",
        "graph_include",
        "lifecycle",
        "slug",
        "created_at",
        "updated_at",
        "raw_source",
        "source_page",
        "brief_page",
        "domain",
        "author",
        "date",
        "source",
    ]
    lines = ["---"]
    emitted: set[str] = set()
    for key in order:
        if key in meta:
            lines.append(f'{key}: "{meta[key]}"')
            emitted.add(key)
    for key in sorted(meta):
        if key not in emitted:
            lines.append(f'{key}: "{meta[key]}"')
    lines.extend(["---", ""])
    return "\n".join(lines)


def classify(path: Path, meta: dict[str, str]) -> dict[str, str]:
    page_type = meta.get("type", "")
    stem = path.stem
    if stem == "index" or page_type == "system-index":
        return {"graph_role": "system", "graph_include": "false", "lifecycle": "canonical"}
    if stem == "log" or page_type == "system-log":
        return {"graph_role": "system", "graph_include": "false", "lifecycle": "canonical"}
    if page_type in {"raw-source", "source", "brief"} or "\\raw\\articles\\" in str(path):
        lifecycle = "canonical" if page_type == "raw-source" else "official"
        return {"graph_role": "document", "graph_include": "false", "lifecycle": lifecycle}
    if page_type in {"domain", "synthesis", "concept", "entity"}:
        return {"graph_role": "knowledge", "graph_include": "true", "lifecycle": "official"}
    if page_type == "output":
        return {"graph_role": "working", "graph_include": "false", "lifecycle": meta.get("lifecycle") or "temporary"}
    if page_type == "delta-compile":
        return {"graph_role": "working", "graph_include": "false", "lifecycle": meta.get("lifecycle") or "review-needed"}
    return {"graph_role": "document", "graph_include": "false", "lifecycle": meta.get("lifecycle") or "official"}


def update_page(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    if not meta:
        meta = {
            "title": "Wiki Index" if path.stem == "index" else "Wiki Log" if path.stem == "log" else path.stem,
            "type": "system-index" if path.stem == "index" else "system-log" if path.stem == "log" else "note",
        }
    meta.update(classify(path, meta))
    updated = render_frontmatter(meta) + body.lstrip("\n")
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    targets = [
        vault / "wiki" / "index.md",
        vault / "wiki" / "log.md",
    ]
    for folder in WIKI_FOLDERS:
        targets.extend(sorted((vault / "wiki" / folder).glob("*.md")))
    targets.extend(sorted((vault / "raw" / "articles").glob("*.md")))

    updated = [str(path) for path in targets if path.exists() and update_page(path)]
    print(json.dumps({"updated": updated}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
