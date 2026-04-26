from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow imports from scripts/ directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(prog="kwiki fetch", description="Fetch sources through adapters")
    parser.add_argument("--url", help="URL to fetch")
    parser.add_argument("--file", help="Local file path to fetch")
    parser.add_argument("--text", help="Plain text to ingest")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument("--work-dir", help="Working directory for adapter output")
    parser.add_argument("--source-id", help="Override source type detection")
    args = parser.parse_args()

    if not any([args.url, args.file, args.text]):
        parser.error("Must provide --url, --file, or --text")

    from source_registry import match_source_from_url, match_source_from_file
    from adapters import run_adapter_for_source

    work_dir = Path(args.work_dir) if args.work_dir else Path(args.vault) / ".tmp-kwiki-fetch"
    work_dir.mkdir(parents=True, exist_ok=True)

    if args.url:
        source_id = args.source_id or match_source_from_url(args.url) or "web_url"
        input_value = args.url
    elif args.file:
        source_id = args.source_id or match_source_from_file(Path(args.file)) or "local_file_md"
        input_value = args.file
    else:
        source_id = "plain_text"
        input_value = args.text or ""

    result = run_adapter_for_source(
        source_id=source_id,
        input_value=input_value,
        work_dir=work_dir,
    )
    if result.get("status") == "ok":
        result["deprecated"] = "Use wiki_ingest_wechat.py --url/--file/--text instead. See references/helper-scripts.md."
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
