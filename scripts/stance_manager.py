#!/usr/bin/env python
"""CLI entrypoint for managing Stance Pages."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.encoding_fix import fix_windows_encoding
from pipeline.stance import (
    write_stance_page,
    apply_stance_impact,
    scan_active_stances,
)


def main() -> int:
    fix_windows_encoding()
    parser = argparse.ArgumentParser(description="Manage Stance Pages")
    sub = parser.add_subparsers(dest="command")

    # list
    list_cmd = sub.add_parser("list", help="List active/challenged stances")
    list_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    list_cmd.add_argument("--json", action="store_true", help="Output as JSON")

    # create
    create_cmd = sub.add_parser("create", help="Create a new stance page")
    create_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    create_cmd.add_argument("--topic", required=True, help="The topic of the stance")
    create_cmd.add_argument("--judgement", default="", help="Core judgement text")
    create_cmd.add_argument("--confidence", default="medium", choices=["high", "medium", "low"], help="Confidence level")
    create_cmd.add_argument("--rethinking-conditions", default="", help="Conditions that would trigger re-evaluation")

    # impact
    impact_cmd = sub.add_parser("impact", help="Apply a stance impact from a new source")
    impact_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    impact_cmd.add_argument("--slug", required=True, help="Stance page slug")
    impact_cmd.add_argument("--impact", required=True, choices=["reinforce", "contradict", "extend", "neutral"], help="Impact type")
    impact_cmd.add_argument("--source-link", required=True, help="Source page link (e.g. sources/slug)")
    impact_cmd.add_argument("--note", default="", help="Impact note")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    vault = Path(args.vault)

    if args.command == "list":
        stances = scan_active_stances(vault)
        if args.json:
            print(json.dumps(stances, ensure_ascii=False, indent=2))
        else:
            for s in stances:
                print(f"  [{s['confidence']}] {s['title']}  ({s['slug']}, {s['source_count']} sources)")
            if not stances:
                print("  (no active stances)")

    elif args.command == "create":
        path = write_stance_page(
            vault,
            topic=args.topic,
            core_judgement=args.judgement,
            confidence=args.confidence,
            rethinking_conditions=args.rethinking_conditions,
        )
        print(f"Created: {path}")

    elif args.command == "impact":
        path = apply_stance_impact(
            vault,
            args.slug,
            impact=args.impact,
            source_link=args.source_link,
            note=args.note,
        )
        print(f"Updated: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
