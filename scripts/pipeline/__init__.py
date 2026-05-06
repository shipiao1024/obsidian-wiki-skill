"""Pipeline package: modular stages for wiki ingestion.

Core modules:
  pipeline_types.py      — Article dataclass, WIKI_DIRS, constants
  text_utils.py         — regex helpers, plain_text, parse_frontmatter, section_excerpt
  extractors.py         — detect_domains, extract_concepts/entities, taxonomy helpers
  vault_config.py       — resolve_vault, multi-vault registry, video/transcript helpers
  shared.py             — re-export shim (backward compat)
  page_builders.py      — page content generation, merge/replace, write/upsert
  taxonomy.py           — ensure_taxonomy/synthesis/comparison_pages, status upgrade
  ingest_orchestrator.py — ingest_article main orchestrator
  index_log.py          — rebuild_index, append_log, update_hot_cache
  apply.py              — re-export shim (backward compat)
  output/               — 9 query output mode subpackage
"""

from pipeline.pipeline_types import Article, WIKI_DIRS
from pipeline.fetch import (
    collect_urls,
    collect_local_files,
    create_runtime_input_dir,
    load_articles,
    load_articles_from_inputs,
    load_articles_from_urls,
    update_collection_import_jobs,
    summarize_collection_statuses,
)
from pipeline.ingest import ensure_bootstrap, build_raw_page, build_transcript_page
from pipeline.compile import try_llm_compile, try_llm_compile_two_step
from pipeline.ingest_orchestrator import ingest_article
from pipeline.index_log import rebuild_index, append_log

__all__ = [
    "Article",
    "WIKI_DIRS",
    "collect_urls",
    "collect_local_files",
    "create_runtime_input_dir",
    "load_articles",
    "load_articles_from_inputs",
    "load_articles_from_urls",
    "update_collection_import_jobs",
    "summarize_collection_statuses",
    "ensure_bootstrap",
    "build_raw_page",
    "build_transcript_page",
    "try_llm_compile",
    "try_llm_compile_two_step",
    "ingest_article",
    "rebuild_index",
    "append_log",
]