from __future__ import annotations

import sys


def main() -> int:
    stages = ["fetch", "ingest", "apply", "review"]
    if len(sys.argv) < 2 or sys.argv[1] not in stages:
        print(f"Usage: python -m kwiki <{'|'.join(stages)}> [args...]", file=sys.stderr)
        return 1
    stage = sys.argv[1]
    sys.argv = sys.argv[1:]
    if stage == "fetch":
        from kwiki.fetch import main as m
    elif stage == "ingest":
        from kwiki.ingest import main as m
    elif stage == "apply":
        from kwiki.apply import main as m
    elif stage == "review":
        from kwiki.review import main as m
    else:
        print(f"Unknown stage: {stage}", file=sys.stderr)
        return 1
    return m()


if __name__ == "__main__":
    raise SystemExit(main())
