from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.evolution import write_evolution_page
from pipeline.blindspots import write_blind_spots_page


def main() -> int:
    parser = argparse.ArgumentParser(prog="kwiki review", description="Run review and maintenance tasks")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument("--action", choices=["lint", "stale", "size", "queue", "evolution", "blind-spots"], default="lint", help="Review action to run")
    args = parser.parse_args()

    vault = Path(args.vault)
    if not vault.exists():
        print(json.dumps({"status": "invalid_input", "reason": f"Vault not found: {vault}"}))
        return 1

    if args.action == "evolution":
        path = write_evolution_page(vault)
        print(json.dumps({"status": "ok", "action": "evolution", "output": str(path)}, ensure_ascii=False, indent=2))
        return 0
    elif args.action == "blind-spots":
        path = write_blind_spots_page(vault)
        print(json.dumps({"status": "ok", "action": "blind-spots", "output": str(path)}, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps({
        "status": "stub",
        "action": args.action,
        "deprecated": f"Use wiki_lint.py / stale_report.py / wiki_size_report.py / review_queue.py directly for full functionality. See references/helper-scripts.md.",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
