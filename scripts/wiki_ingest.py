#!/usr/bin/env python
"""Thin orchestrator for wiki ingestion.

This script is the primary entrypoint for `fetch+heuristic` and
`fetch+api-compile` workflows. It delegates to the pipeline package
for all substantive work.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pipeline.fetch as _fetch
import pipeline.ingest as _ingest
import pipeline.apply as _apply
from pipeline.shared import slugify_article, resolve_vault, detect_domains

SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_TOOL_DIR = SKILL_DIR / ".tools" / "wechat-article-for-ai"
_DEFAULT_DEPS_DIR = SKILL_DIR / ".python-packages"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Supporting script for fetch+heuristic or fetch+api-compile into an Obsidian LLM wiki."
    )
    parser.add_argument("urls", nargs="*", help="mp.weixin.qq.com article URLs.")
    parser.add_argument("-f", "--file", type=Path, help="Text file with one URL per line.")
    parser.add_argument("--text", action="append", default=[], help="Plain text source input. Can be provided multiple times.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument(
        "--tool-dir",
        type=Path,
        default=os.environ.get("KWIKI_WECHAT_TOOL_DIR") or os.environ.get("WECHAT_ARTICLE_FOR_AI_DIR") or (_DEFAULT_TOOL_DIR if _DEFAULT_TOOL_DIR.exists() else None),
        help="Path to cloned wechat-article-for-ai repo. Auto-detected from skill .tools/ if env var unset.",
    )
    parser.add_argument(
        "--deps-dir",
        type=Path,
        default=os.environ.get("KWIKI_DEPS_DIR") or os.environ.get("WECHAT_ARTICLE_PYTHONPATH") or (_DEFAULT_DEPS_DIR if _DEFAULT_DEPS_DIR.exists() else None),
        help="Optional dependency directory to prepend to PYTHONPATH. Auto-detected from skill .python-packages/ if env var unset.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Existing wechat-article-for-ai output dir. Skips fetching.",
    )
    parser.add_argument("--work-dir", type=Path, help="Staging output directory.")
    parser.add_argument("--python", default=sys.executable, help="Python executable.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing raw/wiki pages.")
    parser.add_argument(
        "--collection-limit",
        type=int,
        help="Limit collection imports per run; clamped to 20.",
    )
    parser.add_argument(
        "--collection-delay-seconds",
        type=float,
        default=1.0,
        help="Sleep between collection video requests.",
    )
    parser.add_argument(
        "--collection-failure-threshold",
        type=int,
        default=3,
        help="Pause collection import after this many consecutive failures.",
    )
    parser.add_argument(
        "--collection-backoff-seconds",
        type=float,
        default=5.0,
        help="Base backoff after a failed collection item.",
    )
    parser.add_argument(
        "--collection-jitter-seconds",
        type=float,
        default=0.5,
        help="Random jitter added on top of collection backoff.",
    )
    parser.add_argument(
        "--collection-platform-cooldown-seconds",
        type=int,
        default=1800,
        help="Cooldown duration written after repeated collection failures.",
    )
    parser.add_argument("--no-images", action="store_true", help="Do not download images when fetching.")
    parser.add_argument("--no-headless", action="store_true", help="Show browser for CAPTCHA handling.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose upstream logging.")
    parser.add_argument("--no-llm-compile", action="store_true", help="Disable LLM-based brief/source compilation and always use heuristic fallback.")
    return parser.parse_args()



def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    vault.mkdir(parents=True, exist_ok=True)
    _ingest.ensure_bootstrap(vault)

    cleanup: callable | None = None
    collection_contexts: list[dict[str, object]] = []
    if args.input_dir:
        input_dir = args.input_dir.resolve()
        articles = _fetch.load_articles(input_dir)
    else:
        if args.work_dir:
            input_dir = args.work_dir.resolve()
            input_dir.mkdir(parents=True, exist_ok=True)
        else:
            runtime_root = Path.cwd() / ".runtime-fetch"
            input_dir, cleanup = _fetch.create_runtime_input_dir(runtime_root)
        articles = _fetch.load_articles_from_inputs(args, input_dir, vault=vault, collection_contexts=collection_contexts)

    if not articles:
        collections = _fetch.summarize_collection_statuses(collection_contexts)
        if collection_contexts:
            _fetch.update_collection_import_jobs(collection_contexts, {})
            print(json.dumps({"ingested": [], "collections": collections}, ensure_ascii=False, indent=2))
            if cleanup:
                cleanup()
            return 0
        raise SystemExit(f"No article markdown found in {input_dir}")

    # Re-resolve vault using domain detection from the first article
    if not args.vault and articles:
        article_domains = detect_domains(articles[0])
        domain_vault = resolve_vault(article_domains=article_domains)
        if domain_vault != vault:
            vault = domain_vault
            vault.mkdir(parents=True, exist_ok=True)
            _ingest.ensure_bootstrap(vault)
            print(f"Auto-routed to vault: {vault} (matched domains: {', '.join(article_domains)})", file=sys.stderr)

    manifest = []
    log_entries: list[tuple[str, str, str]] = []
    collection_results: dict[tuple[str, str], list[dict[str, str]]] = {}
    for article in articles:
        result = _apply.ingest_article(vault, article, args.force, args.no_llm_compile)
        manifest.append(
            {
                "title": result["title"],
                "raw": str(vault / "raw" / "articles" / f'{result["slug"]}.md'),
                "source": str(vault / "wiki" / "sources" / f'{result["slug"]}.md'),
                "brief": str(vault / "wiki" / "briefs" / f'{result["slug"]}.md'),
                "status": result["status"],
                "compile_mode": result["compile_mode"],
                "compile_reason": result["compile_reason"],
                "skip_reason": result["skip_reason"],
                "quality": result["quality"],
            }
        )
        log_entries.append((result["title"], result["slug"], result["quality"]))
        if article.collection_source_kind and article.collection_source_url and article.collection_video_id:
            key = (article.collection_source_kind, article.collection_source_url)
            collection_results.setdefault(key, []).append(
                {
                    "video_id": article.collection_video_id,
                    "source_slug": result["slug"],
                    "status": result["status"],
                }
            )

    _apply.rebuild_index(vault)
    _apply.append_log(vault, log_entries)
    if collection_contexts:
        collection_run_results: dict[tuple[str, str], list[dict[str, str]]] = {}
        for key, items in collection_results.items():
            collection_run_results[key] = list(items)
        for context in collection_contexts:
            source_kind = str(context.get("source_kind", "") or "")
            source_url = str(context.get("source_url", "") or "")
            if source_kind and source_url:
                context["run_results"] = collection_run_results.get((source_kind, source_url), [])
        _fetch.update_collection_import_jobs(collection_contexts, collection_results)
    collections = _fetch.summarize_collection_statuses(collection_contexts)

    print(json.dumps({"ingested": manifest, "collections": collections}, ensure_ascii=False, indent=2))
    if cleanup:
        cleanup()
    return 1 if any(m["status"] == "skipped" for m in manifest) and not any(m["status"] == "ingested" for m in manifest) else 0


if __name__ == "__main__":
    raise SystemExit(main())