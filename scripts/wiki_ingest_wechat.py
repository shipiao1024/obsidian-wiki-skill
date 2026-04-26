#!/usr/bin/env python
"""Backward-compatibility shim: delegates to wiki_ingest and pipeline package.

All logic has been refactored into the pipeline/ package.
This file re-exports the public API so existing imports keep working.
"""

from wiki_ingest import main, parse_args  # noqa: F401
import wiki_ingest as _wi  # noqa: F401

from pipeline.shared import (  # noqa: F401
    Article,
    WIKI_DIRS,
    resolve_vault,
    sanitize_filename,
    slugify_article,
    parse_frontmatter,
    plain_text,
    detect_domains,
    extract_entities,
    extract_concepts,
    video_id_from_url,
    normalize_collection_url,
)
from pipeline.fetch import (  # noqa: F401
    collect_urls,
    collect_local_files,
    create_runtime_input_dir,
    run_fetch,
    load_articles,
    load_articles_from_urls,
    load_articles_from_inputs,
    load_articles_from_video_collection,
    update_collection_import_jobs,
    summarize_collection_statuses,
    default_tool_dir,
)
from pipeline.ingest import (  # noqa: F401
    ensure_bootstrap,
    build_agents_md,
    build_raw_page,
    copy_assets,
    build_transcript_page,
)
from pipeline.compile import (  # noqa: F401
    try_llm_compile,
    emit_update_proposals_from_payload,
)
from pipeline.apply import (  # noqa: F401
    ingest_article,
    append_log,
    rebuild_index,
    ensure_taxonomy_pages,
    ensure_synthesis_pages,
    article_output_exists,
    build_brief_page_from_compile,
    build_source_page_from_compile,
)
from pipeline.question import (  # noqa: F401
    write_question_page,
    update_question_status,
    scan_open_questions,
    check_source_answers_questions,
)

import subprocess  # noqa: F401 (used by tests for mock.patch.object)
import time  # noqa: F401
import random  # noqa: F401

# Re-export pipeline submodules as module-level attributes so that
# mock.patch.object(wiki_ingest_wechat, "load_articles_from_inputs", ...)
# works for tests that mock the shim module's attributes.
import pipeline.fetch as _fetch  # noqa: F401
import pipeline.ingest as _ingest  # noqa: F401
import pipeline.apply as _apply  # noqa: F401

# Synchronize: when tests mock attributes on this shim (e.g. load_articles_from_inputs),
# the wiki_ingest.main() call picks up the mock via its _fetch/_ingest/_apply references
# if we keep them pointing to the same module objects that the shim holds.
_wi._fetch = _fetch
_wi._ingest = _ingest
_wi._apply = _apply

if __name__ == "__main__":
    raise SystemExit(main())
