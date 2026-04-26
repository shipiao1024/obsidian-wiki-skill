from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(prog="kwiki ingest", description="Write raw sources into vault")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument("--raw", help="Path to raw article markdown file")
    args = parser.parse_args()

    from pipeline.ingest import ensure_bootstrap
    vault = Path(args.vault)
    ensure_bootstrap(vault)

    result = {"status": "stub", "vault": str(vault), "deprecated": "Use wiki_ingest.py or wiki_ingest_wechat.py instead. See references/helper-scripts.md."}
    if args.raw:
        raw_path = Path(args.raw)
        if not raw_path.exists():
            result = {"status": "invalid_input", "reason": f"File not found: {raw_path}"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("ok", "stub") else 1


if __name__ == "__main__":
    raise SystemExit(main())
