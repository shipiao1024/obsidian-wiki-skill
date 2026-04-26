#!/usr/bin/env python
"""Archive duplicate or stale outputs in wiki/outputs."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive duplicate outputs while keeping the newest live candidate.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--apply", action="store_true", help="Write archive changes back to files.")
    parser.add_argument(
        "--keep-per-title",
        type=int,
        default=1,
        help="How many newest non-absorbed outputs to keep for each identical title.",
    )
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
    preferred_order = [
        "title",
        "type",
        "status",
        "fidelity",
        "graph_role",
        "graph_include",
        "lifecycle",
        "slug",
        "question",
        "source_page",
        "raw_source",
        "brief_page",
        "created_at",
        "approved_at",
        "archived_at",
        "archived_reason",
        "absorbed_into",
        "updated_at",
        "domain",
        "author",
        "date",
        "source",
    ]
    lines = ["---"]
    emitted: set[str] = set()
    for key in preferred_order:
        if key in meta:
            lines.append(f'{key}: "{meta[key]}"')
            emitted.add(key)
    for key in sorted(meta):
        if key not in emitted:
            lines.append(f'{key}: "{meta[key]}"')
    lines.extend(["---", ""])
    return "\n".join(lines)


def archive_body(body: str, kept_ref: str) -> str:
    note = [
        "## 归档记录",
        "",
        f"- 已归档，保留最新候选：[[outputs/{kept_ref}]]",
        f"- 归档时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    if "## 归档记录" in body:
        return body
    return body.rstrip() + "\n\n" + "\n".join(note)


def rebuild_index(vault: Path) -> None:
    from apply_approved_delta import rebuild_index as apply_rebuild_index

    apply_rebuild_index(vault)


def append_log(vault: Path, archived: list[tuple[str, str]]) -> None:
    if not archived:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"## [{timestamp}] archive_outputs | duplicate cleanup", ""]
    for stem, kept in archived:
        lines.append(f"- archived: [[outputs/{stem}]]")
        lines.append(f"- kept: [[outputs/{kept}]]")
    lines.extend(["", ""])
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    output_paths = sorted((vault / "wiki" / "outputs").glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)

    by_title: defaultdict[str, list[Path]] = defaultdict(list)
    for path in output_paths:
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = meta.get("title") or path.stem
        by_title[title].append(path)

    archived: list[tuple[str, str]] = []
    report: dict[str, object] = {"candidates": {}, "archived": []}
    for title, paths in sorted(by_title.items()):
        live_paths: list[Path] = []
        absorbed_paths: list[Path] = []
        for path in paths:
            meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
            lifecycle = meta.get("lifecycle", "")
            if lifecycle == "absorbed":
                absorbed_paths.append(path)
            elif lifecycle != "archived":
                live_paths.append(path)
        if len(live_paths) <= args.keep_per_title:
            continue

        keep = live_paths[: args.keep_per_title]
        archive_targets = live_paths[args.keep_per_title :]
        report["candidates"][title] = {
            "keep": [path.stem for path in keep],
            "archive": [path.stem for path in archive_targets],
            "absorbed": [path.stem for path in absorbed_paths],
        }
        if args.apply:
            kept_ref = keep[0].stem
            for path in archive_targets:
                meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
                meta["status"] = "accepted" if meta.get("status") == "review-needed" else meta.get("status", "draft")
                meta["lifecycle"] = "archived"
                meta["archived_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                meta["archived_reason"] = f"duplicate-of:{kept_ref}"
                path.write_text(render_frontmatter(meta) + archive_body(body, kept_ref).lstrip("\n"), encoding="utf-8")
                archived.append((path.stem, kept_ref))
                report["archived"].append({"slug": path.stem, "kept": kept_ref})

    if args.apply and archived:
        rebuild_index(vault)
        append_log(vault, archived)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
