"""Main ingestion orchestrator for the obsidian-wiki pipeline."""

from __future__ import annotations

import re
from pathlib import Path

from .types import Article
from .text_utils import slugify_article, parse_frontmatter
from .extractors import detect_domains, detect_domain_mismatch, concept_slug, comparison_slug, domain_slug, entity_slug
from .vault_config import transcript_page_name
from .page_builders import (
    article_output_exists,
    build_brief_page,
    build_brief_page_from_compile,
    build_source_page,
    build_source_page_from_compile,
    write_page,
)
from .taxonomy import (
    ensure_taxonomy_pages,
    ensure_synthesis_pages,
    ensure_comparison_page,
)
from .index_log import update_hot_cache


def _get_compile():
    """Lazy import of compile module via apply shim to support mock.patch on pipeline.apply."""
    from . import apply as _apply_shim
    return _apply_shim
from .ingest import (
    build_raw_page,
    build_transcript_page,
    copy_assets,
    copy_directory_contents,
)
from .compile import (
    compile_reason_from_payload,
    compile_shape_from_payload,
    compiled_domains_from_payload,
    emit_update_proposals_from_payload,
)


def ingest_article(vault: Path, article: Article, force: bool, no_llm_compile: bool) -> dict[str, str]:
    slug = slugify_article(article.date, article.title)
    raw_path = vault / "raw" / "articles" / f"{slug}.md"
    transcript_path = vault / "raw" / "transcripts" / f"{slug}--{transcript_page_name(article)}.md"
    assets_dir = vault / "raw" / "assets" / slug
    brief_path = vault / "wiki" / "briefs" / f"{slug}.md"
    source_path = vault / "wiki" / "sources" / f"{slug}.md"

    if not force and article_output_exists(vault, slug):
        return {
            "title": article.title,
            "slug": slug,
            "status": "skipped",
            "compile_mode": "skipped",
            "compile_reason": "skipped",
            "skip_reason": "raw/source/brief already exist",
            "quality": article.quality,
            "delta_outputs": "",
        }

    copy_assets(article.src_dir / "images", assets_dir, force)
    copy_directory_contents(article.src_dir / "attachments", assets_dir, force)
    if article.transcript_body:
        write_page(transcript_path, build_transcript_page(article, slug), force)
    write_page(raw_path, build_raw_page(article, slug, assets_dir), force)
    compiled_payload, compile_reason = _get_compile().try_llm_compile(vault, article, slug, raw_path, no_llm_compile)
    # Extract dominant confidence from v2 claim_inventory
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result", {}) if isinstance(compiled_payload.get("result"), dict) else {}
        claim_inventory = result.get("claim_inventory", []) if isinstance(result.get("claim_inventory"), list) else []
        if claim_inventory:
            conf_counts: dict[str, int] = {}
            for claim in claim_inventory:
                if not isinstance(claim, dict):
                    continue
                c = str(claim.get("confidence", "")).strip().lower()
                if c in ("high", "medium", "low"):
                    conf_counts[c] = conf_counts.get(c, 0) + 1
            if conf_counts:
                # high > medium > low priority
                for level in ("high", "medium", "low"):
                    if level in conf_counts:
                        article.confidence = level
                        break
    compiled = compile_shape_from_payload(compiled_payload)
    compile_mode = "heuristic"
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        compile_mode = "llm-v2"
    elif compiled:
        compile_mode = "llm"

    if compiled:
        write_page(brief_path, build_brief_page_from_compile(article, slug, compiled), force)
        write_page(source_path, build_source_page_from_compile(vault, article, slug, compiled), force)
    else:
        write_page(brief_path, build_brief_page(article, slug, compile_mode="heuristic"), force)
        write_page(source_path, build_source_page(vault, article, slug, compile_mode="heuristic"), force)
    domains_override = compiled_domains_from_payload(compiled_payload)
    emitted_deltas = emit_update_proposals_from_payload(
        vault=vault,
        compiled_payload=compiled_payload,
        source_slug=slug,
        article_title=article.title,
    )
    # --- purpose.md filtering: skip taxonomy pages for excluded content ---
    purpose_path = vault / "purpose.md"
    purpose_filter_active = False
    if purpose_path.exists():
        purpose_text = purpose_path.read_text(encoding="utf-8")
        exclude_section = ""
        in_exclude = False
        for line in purpose_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## 排除范围"):
                in_exclude = True
                continue
            if stripped.startswith("## ") and in_exclude:
                in_exclude = False
                continue
            if in_exclude and stripped.startswith("- "):
                exclude_section += stripped[2:] + " "
        if exclude_section:
            article_text = f"{article.title} {article.body[:1500]}"
            exclude_terms = [t.strip() for t in exclude_section.split() if len(t.strip()) >= 2]
            match_count = sum(1 for t in exclude_terms if t in article_text)
            if match_count >= 2 or (exclude_terms and match_count / len(exclude_terms) > 0.3):
                purpose_filter_active = True

    if not purpose_filter_active:
        ensure_taxonomy_pages(
            vault,
            article,
            slug,
            force,
            domains_override=domains_override,
            compiled_payload=compiled_payload,
        )
    ensure_synthesis_pages(vault, article, slug, domains_override=domains_override)

    # --- Auto-create question pages from open_questions ---
    open_questions = []
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result", {})
        open_questions = result.get("open_questions", []) if isinstance(result, dict) else []
    from .question import write_question_page as _write_question_page, check_source_answers_questions as _check_answers, update_question_status as _update_q_status, question_slug as _q_slug
    for q_text in open_questions[:5]:
        if isinstance(q_text, str) and q_text.strip():
            _write_question_page(vault, question=q_text.strip(), origin_source=f"sources/{slug}")
    # Check if new source answers any open/partial questions
    source_keywords = re.findall(r"[一-鿿]{2,8}|[A-Za-z0-9\-+]{2,}", f"{article.title} {article.body[:800]}")
    answered_slugs = _check_answers(vault, article.title, slug, source_keywords)
    for q_slug in answered_slugs[:3]:
        _update_q_status(vault, q_slug, new_status="partial", update_note=f"来自 sources/{slug} 提供了部分线索")

    # --- Auto-detect stance impacts from stance_impacts ---
    stance_impacts = []
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result", {})
        stance_impacts = result.get("stance_impacts", []) if isinstance(result, dict) else []
    from .stance import apply_stance_impact as _apply_stance_impact, stance_slug as _stance_slug
    for impact_entry in stance_impacts[:5]:
        if not isinstance(impact_entry, dict):
            continue
        topic = str(impact_entry.get("stance_topic", "")).strip()
        impact = str(impact_entry.get("impact", "neutral")).strip()
        evidence = str(impact_entry.get("evidence", "")).strip()
        if not topic or impact == "neutral" or impact not in ("reinforce", "contradict", "extend"):
            continue
        s_slug = _stance_slug(topic)
        stance_page = vault / "wiki" / "stances" / f"{s_slug}.md"
        if stance_page.exists():
            _apply_stance_impact(vault, s_slug, impact=impact, source_link=f"sources/{slug}", note=evidence)

    # --- Auto-create comparison pages from v2 compile comparisons ---
    comparisons = []
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result", {}) if isinstance(compiled_payload.get("result"), dict) else {}
        comparisons = result.get("comparisons", []) if isinstance(result.get("comparisons"), list) else []
    for comp_entry in comparisons[:3]:
        if not isinstance(comp_entry, dict):
            continue
        subject_a = str(comp_entry.get("subject_a", "")).strip()
        subject_b = str(comp_entry.get("subject_b", "")).strip()
        dimensions = [str(d).strip() for d in comp_entry.get("dimensions", []) if isinstance(d, str) and d.strip()]
        if subject_a and subject_b:
            ensure_comparison_page(vault, subject_a, subject_b, slug, dimensions=dimensions)

    update_hot_cache(vault, article.title, slug, compile_mode)

    # --- Rebuild knowledge graph after ingestion ---
    try:
        from .graph_mermaid import write_knowledge_graph as _write_mermaid
        from .graph_analysis import write_graph_data as _write_graph_data
        from .graph_html import write_graph_html as _write_graph_html
        _write_mermaid(vault)
        _write_graph_data(vault)
        _write_graph_html(vault)
    except Exception:
        pass  # graph rebuild is non-critical; don't block ingestion

    # --- Build ingest impact report ---
    domain_mismatch = detect_domain_mismatch(article, vault)
    from .ingest_report import build_ingest_impact_report, format_ingest_report
    impact = build_ingest_impact_report(
        vault, slug, article.title, compiled_payload,
        compile_mode=compile_mode, article=article, domain_mismatch=domain_mismatch,
    )
    impact_text = format_ingest_report(impact)

    return {
        "title": article.title,
        "slug": slug,
        "status": "ingested",
        "compile_mode": compile_mode,
        "compile_reason": compile_reason_from_payload(compiled_payload, compile_reason),
        "skip_reason": "",
        "quality": article.quality,
        "delta_outputs": ",".join(path.name for path in emitted_deltas),
        "impact_report": impact_text,
    }