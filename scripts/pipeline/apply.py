"""Backward-compatibility shim — all functions re-exported from split modules.

The original apply.py has been split into:
  pipeline/page_builders.py      — page content generation, merge/replace, write/upsert
  pipeline/taxonomy.py           — ensure_taxonomy/synthesis/comparison_pages, status upgrade
  pipeline/ingest_orchestrator.py — ingest_article orchestrator
  pipeline/index_log.py          — rebuild_index, append_log, update_hot_cache

This shim preserves all existing import paths (from pipeline.apply import ...).
"""

from .page_builders import (
    merge_links_section,
    replace_links_section,
    render_frontmatter,
    build_brief_page_from_compile,
    build_source_page_from_compile,
    build_concept_page,
    build_entity_page,
    build_domain_page,
    build_synthesis_page,
    build_comparison_page,
    write_page,
    upsert_page,
    article_output_exists,
)
from .taxonomy import (
    ensure_comparison_page,
    check_and_upgrade_status,
    ensure_taxonomy_pages,
    ensure_synthesis_pages,
)
from .compile import (
    try_llm_compile,
    try_llm_compile_two_step,
    compile_reason_from_payload,
    compile_shape_from_payload,
    compiled_domains_from_payload,
    emit_update_proposals_from_payload,
    promoted_taxonomy_names_from_payload,
)
from .ingest import (
    build_raw_page,
    build_transcript_page,
    copy_assets,
    copy_directory_contents,
)
from .ingest_orchestrator import (
    ingest_article,
)
from .index_log import (
    rebuild_index,
    append_log,
    update_hot_cache,
)

__all__ = [
    "merge_links_section",
    "replace_links_section",
    "render_frontmatter",
    "build_brief_page_from_compile",
    "build_source_page_from_compile",
    "build_concept_page",
    "build_entity_page",
    "build_domain_page",
    "build_synthesis_page",
    "build_comparison_page",
    "write_page",
    "upsert_page",
    "article_output_exists",
    "ensure_comparison_page",
    "check_and_upgrade_status",
    "ensure_taxonomy_pages",
    "ensure_synthesis_pages",
    "ingest_article",
    "rebuild_index",
    "append_log",
    "update_hot_cache",
    "try_llm_compile",
    "try_llm_compile_two_step",
    "compile_reason_from_payload",
    "compile_shape_from_payload",
    "compiled_domains_from_payload",
    "emit_update_proposals_from_payload",
    "promoted_taxonomy_names_from_payload",
    "build_raw_page",
    "build_transcript_page",
    "copy_assets",
    "copy_directory_contents",
]
