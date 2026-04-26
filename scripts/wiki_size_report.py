#!/usr/bin/env python
"""Report the current size of the local wiki to judge whether index-first querying is still enough."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from pipeline.shared import resolve_vault


WIKI_FOLDERS = ["sources", "briefs", "concepts", "entities", "domains", "syntheses", "outputs"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report wiki size and rough context pressure.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--warn-pages", type=int, default=120, help="Warn when wiki page count exceeds this value.")
    parser.add_argument("--warn-tokens", type=int, default=80000, help="Warn when estimated wiki tokens exceed this value.")
    return parser.parse_args()



def estimate_tokens(chars: int) -> int:
    return max(1, round(chars / 2.5))


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    wiki_stats: dict[str, dict[str, int]] = {}
    total_pages = 0
    total_chars = 0
    for folder in WIKI_FOLDERS:
        chars = 0
        count = 0
        for path in (vault / "wiki" / folder).glob("*.md"):
            count += 1
            chars += len(path.read_text(encoding="utf-8"))
        wiki_stats[folder] = {
            "pages": count,
            "chars": chars,
            "est_tokens": estimate_tokens(chars),
        }
        total_pages += count
        total_chars += chars

    index_path = vault / "wiki" / "index.md"
    index_chars = len(index_path.read_text(encoding="utf-8")) if index_path.exists() else 0
    index_tokens = estimate_tokens(index_chars)
    total_tokens = estimate_tokens(total_chars)

    mode = "GREEN"
    advice = "当前仍适合 index-first + 定向读页，不必急着引入额外检索基础设施。"
    if total_pages > args.warn_pages or total_tokens > args.warn_tokens:
        mode = "YELLOW"
        advice = "知识库正在逼近 index-only 的舒适区边界，建议开始准备本地搜索或更强的候选筛选。"
    if total_pages > args.warn_pages * 2 or total_tokens > args.warn_tokens * 2:
        mode = "RED"
        advice = "知识库已经明显超过 index-first 的舒适区，建议引入 qmd 或等价的本地搜索层。"

    print(
        json.dumps(
            {
                "vault": str(vault),
                "status": mode,
                "advice": advice,
                "summary": {
                    "wiki_pages": total_pages,
                    "wiki_chars": total_chars,
                    "wiki_est_tokens": total_tokens,
                    "index_chars": index_chars,
                    "index_est_tokens": index_tokens,
                },
                "by_folder": wiki_stats,
                "thresholds": {
                    "warn_pages": args.warn_pages,
                    "warn_tokens": args.warn_tokens,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
