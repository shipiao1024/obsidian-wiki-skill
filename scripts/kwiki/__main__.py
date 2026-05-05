"""CLI entrypoint for kwiki review commands.

v1.1 cleanup: fetch/ingest/apply stubs removed.
Only review (evolution/blind-spots) retains real functionality.
"""
from __future__ import annotations

import sys


def main() -> int:
    stages = ["review"]
    if len(sys.argv) < 2 or sys.argv[1] not in stages:
        print(f"Usage: python -m kwiki <{'|'.join(stages)}> [args...]", file=sys.stderr)
        print("Note: fetch/ingest/apply have been removed. Use wiki_ingest.py directly.", file=sys.stderr)
        return 1
    stage = sys.argv[1]
    sys.argv = sys.argv[1:]
    if stage == "review":
        from kwiki.review import main as m
    else:
        print(f"Unknown stage: {stage}", file=sys.stderr)
        return 1
    return m()


if __name__ == "__main__":
    raise SystemExit(main())
