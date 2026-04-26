#!/usr/bin/env python
"""CLI entrypoint for managing the Question Ledger.

Supports listing open questions, creating new questions,
and checking if a source answers any existing questions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.question import (
    write_question_page,
    update_question_status,
    scan_open_questions,
    check_source_answers_questions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the Question Ledger")
    sub = parser.add_subparsers(dest="command")

    # list
    list_cmd = sub.add_parser("list", help="List open/partial questions")
    list_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    list_cmd.add_argument("--json", action="store_true", help="Output as JSON")

    # create
    create_cmd = sub.add_parser("create", help="Create a new question")
    create_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    create_cmd.add_argument("--question", required=True, help="The question text")
    create_cmd.add_argument("--origin-source", default="", help="Origin source page link")
    create_cmd.add_argument("--origin-query", default="", help="Origin query text")
    create_cmd.add_argument("--partial-answer", default="", help="Partial answer if known")
    create_cmd.add_argument("--known-clues", default="", help="Known clues")
    create_cmd.add_argument("--needed-materials", default="", help="What materials are needed")

    # check
    check_cmd = sub.add_parser("check", help="Check if a source answers any open questions")
    check_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    check_cmd.add_argument("--source-title", required=True, help="Source article title")
    check_cmd.add_argument("--source-slug", required=True, help="Source article slug")
    check_cmd.add_argument("--keywords", nargs="+", help="Source keywords for matching")

    # resolve
    resolve_cmd = sub.add_parser("resolve", help="Mark a question as resolved")
    resolve_cmd.add_argument("--vault", required=True, help="Path to Obsidian vault")
    resolve_cmd.add_argument("--slug", required=True, help="Question page slug")
    resolve_cmd.add_argument("--note", default="", help="Resolution note")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    vault = Path(args.vault)

    if args.command == "list":
        questions = scan_open_questions(vault)
        if args.json:
            print(json.dumps(questions, ensure_ascii=False, indent=2))
        else:
            for q in questions:
                print(f"  [{q['status']}] {q['title']}  ({q['slug']})")
            if not questions:
                print("  (no open questions)")

    elif args.command == "create":
        path = write_question_page(
            vault,
            question=args.question,
            origin_source=args.origin_source,
            origin_query=args.origin_query,
            partial_answer=args.partial_answer,
            known_clues=args.known_clues,
            needed_materials=args.needed_materials,
        )
        print(f"Created: {path}")

    elif args.command == "check":
        keywords = args.keywords or []
        matched = check_source_answers_questions(
            vault,
            source_title=args.source_title,
            source_slug=args.source_slug,
            source_keywords=keywords,
        )
        if matched:
            print(f"Source may address {len(matched)} question(s):")
            for slug in matched:
                print(f"  - {slug}")
        else:
            print("No matching open questions found.")

    elif args.command == "resolve":
        path = update_question_status(
            vault,
            args.slug,
            new_status="resolved",
            update_note=args.note or "Resolved",
        )
        print(f"Updated: {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
