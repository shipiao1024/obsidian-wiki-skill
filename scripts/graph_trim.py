#!/usr/bin/env python
"""Demote selected low-signal wiki pages from the main graph view."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from graph_cleanup import parse_frontmatter, render_frontmatter
from pipeline.shared import resolve_vault

SOURCE_LINK = re.compile(r"\[\[sources/[^|\]]+\]\]")
PLACEHOLDER_HINTS = (
    "待后续",
    "待补充",
    "待人工",
    "待随着更多来源持续演化",
    "待验证",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Demote selected wiki pages from the main graph layer.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--demote-concept", action="append", default=[], help="Concept page title/stem to hide from main graph.")
    parser.add_argument("--demote-entity", action="append", default=[], help="Entity page title/stem to hide from main graph.")
    parser.add_argument("--demote-domain", action="append", default=[], help="Domain page title/stem to hide from main graph.")
    parser.add_argument("--demote-synthesis", action="append", default=[], help="Synthesis page title/stem to hide from main graph.")
    parser.add_argument("--apply-policy", action="store_true", help="Apply the built-in graph promotion/demotion policy.")
    parser.add_argument("--dry-run", action="store_true", help="Only report candidate changes.")
    return parser.parse_args()


def normalize(name: str) -> str:
    return name.strip().lower()


def target_map(args: argparse.Namespace) -> dict[str, set[str]]:
    return {
        "concepts": {normalize(name) for name in args.demote_concept},
        "entities": {normalize(name) for name in args.demote_entity},
        "domains": {normalize(name) for name in args.demote_domain},
        "syntheses": {normalize(name) for name in args.demote_synthesis},
    }


def matches(path: Path, targets: set[str]) -> bool:
    if not targets:
        return False
    stem = normalize(path.stem)
    if stem in targets:
        return True
    meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
    title = normalize(meta.get("title", ""))
    return title in targets


def demote(path: Path, role: str, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    meta["graph_role"] = role
    meta["graph_include"] = "false"
    updated = render_frontmatter(meta) + body.lstrip("\n")
    if updated == text:
        return False
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return True


def source_link_count(text: str) -> int:
    return len(set(SOURCE_LINK.findall(text)))


def has_placeholder(text: str) -> bool:
    return any(hint in text for hint in PLACEHOLDER_HINTS)


def apply_policy(path: Path, folder: str, dry_run: bool) -> bool:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    source_count = source_link_count(body)
    placeholder = has_placeholder(body)

    if folder in {"concepts", "entities"}:
        if source_count >= 2 and not placeholder:
            target_role = "knowledge"
            target_include = "true"
        else:
            target_role = "knowledge-candidate"
            target_include = "false"
    elif folder in {"domains", "syntheses"}:
        if source_count >= 2:
            target_role = "knowledge"
            target_include = "true"
        else:
            target_role = "knowledge-secondary"
            target_include = "false"
    else:
        return False

    meta["graph_role"] = target_role
    meta["graph_include"] = target_include
    updated = render_frontmatter(meta) + body.lstrip("\n")
    if updated == text:
        return False
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    groups = target_map(args)
    updated: list[str] = []

    if args.apply_policy:
        for folder in ["concepts", "entities", "domains", "syntheses"]:
            for path in sorted((vault / "wiki" / folder).glob("*.md")):
                if apply_policy(path, folder, dry_run=args.dry_run):
                    updated.append(str(path))

    for folder, role in [
        ("concepts", "knowledge-candidate"),
        ("entities", "knowledge-candidate"),
        ("domains", "knowledge-secondary"),
        ("syntheses", "knowledge-secondary"),
    ]:
        for path in sorted((vault / "wiki" / folder).glob("*.md")):
            if matches(path, groups[folder]):
                if demote(path, role=role, dry_run=args.dry_run):
                    updated.append(str(path))

    print(json.dumps({"updated": updated, "dry_run": args.dry_run}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
