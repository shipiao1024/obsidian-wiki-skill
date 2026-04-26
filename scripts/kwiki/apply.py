from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(prog="kwiki apply", description="Apply compiled JSON to wiki pages")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument("--raw", required=True, help="Path to raw article markdown file")
    parser.add_argument("--compiled-json", required=True, help="Path to compiled JSON file")
    parser.add_argument("--force", action="store_true", help="Overwrite existing pages")
    args = parser.parse_args()

    vault = Path(args.vault)
    raw_path = Path(args.raw)
    json_path = Path(args.compiled_json)

    if not raw_path.exists():
        print(json.dumps({"status": "invalid_input", "reason": f"Raw file not found: {raw_path}"}))
        return 1
    if not json_path.exists():
        print(json.dumps({"status": "invalid_input", "reason": f"Compiled JSON not found: {json_path}"}))
        return 1

    print(json.dumps({
        "status": "stub",
        "deprecated": "Use apply_compiled_brief_source.py for full apply functionality. See references/helper-scripts.md.",
        "vault": str(vault),
        "raw": str(raw_path),
        "compiled_json": str(json_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
