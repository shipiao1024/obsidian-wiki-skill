"""Main ingestion orchestrator for the obsidian-wiki pipeline."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .pipeline_types import Article
from .text_utils import slugify_article, parse_frontmatter
from .extractors import detect_domain_mismatch, concept_slug, comparison_slug, domain_slug, entity_slug
from .vault_config import transcript_page_name
from .page_builders import (
    article_output_exists,
    build_brief_page_from_compile,
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
    """Lazy import of compile module. Direct import replaces the previous
    apply-shim indirection. Tests should mock pipeline.compile.try_llm_compile."""
    from . import compile as _compile_module
    return _compile_module


_ACTIONABLE_ORDINALS = {"Working", "Supported", "Stable"}


def _determine_lifecycle(compiled_payload: dict | None, article: Article) -> str:
    """Determine page lifecycle (official/candidate) from compile payload and confidence."""
    lifecycle = "official"
    if not compiled_payload or compiled_payload.get("schema_version") != "2.0":
        return lifecycle
    result = compiled_payload.get("result", {}) if isinstance(compiled_payload.get("result"), dict) else {}
    review_hints = result.get("review_hints", {}) if isinstance(result.get("review_hints"), dict) else {}
    needs_review = bool(review_hints.get("needs_human_review", False))
    has_actionable = any(
        isinstance(c, dict) and c.get("confidence", "").strip() in _ACTIONABLE_ORDINALS
        for c in article.claim_inventory
    )
    if needs_review or (article.confidence not in _ACTIONABLE_ORDINALS and not has_actionable):
        lifecycle = "candidate"
    return lifecycle


def _apply_purpose_filter(vault: Path, article: Article) -> bool:
    """Check if article matches purpose.md exclusion rules. Returns True if excluded."""
    purpose_path = vault / "purpose.md"
    if not purpose_path.exists():
        return False
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
    if not exclude_section:
        return False
    article_text = f"{article.title} {article.body[:1500]}"
    exclude_terms = [t.strip() for t in exclude_section.split() if len(t.strip()) >= 2]
    match_count = sum(1 for t in exclude_terms if t in article_text)
    return match_count >= 2 or (exclude_terms and match_count / len(exclude_terms) > 0.3)


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


def ingest_article(vault: Path, article: Article, force: bool, no_llm_compile: bool = False, *, compile_mode: str = "prepare-only", chunk_size: int = 500) -> dict[str, str]:
    # Auto-chunk threshold: switch to chunked-prepare for long documents
    _AUTO_CHUNK_THRESHOLD = 800
    effective_compile_mode = compile_mode
    if compile_mode == "prepare-only" and article.body and len(article.body.splitlines()) > _AUTO_CHUNK_THRESHOLD:
        effective_compile_mode = "chunked-prepare"
        print(f"[auto-chunk] {article.title}: {len(article.body.splitlines())} lines > {_AUTO_CHUNK_THRESHOLD} threshold, switching to chunked-prepare", file=sys.stderr)

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
    compiled_payload, compile_reason = _get_compile().try_llm_compile(vault, article, slug, raw_path, no_llm_compile, mode=effective_compile_mode, chunk_size=chunk_size)

    # Persist prepare-only payload to D:\tmp
    if compiled_payload and compiled_payload.get("prepare_only"):
        try:
            tmp_dir = Path("D:/tmp")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            payload_path = tmp_dir / f"{slug}_payload.json"
            payload_path.write_text(json.dumps(compiled_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[payload] Prepare-only payload saved to {payload_path}", file=sys.stderr)
        except Exception as exc:
            print(f"[payload] Failed to save payload: {exc}", file=sys.stderr)
    # Extract dominant confidence from v2 claim_inventory (ordinal labels)
    _ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result", {}) if isinstance(compiled_payload.get("result"), dict) else {}
        claim_inventory = result.get("claim_inventory", []) if isinstance(result.get("claim_inventory"), list) else []
        if claim_inventory:
            best_conf = ""
            best_rank = -1
            for claim in claim_inventory:
                if not isinstance(claim, dict):
                    continue
                c = str(claim.get("confidence", "")).strip()
                rank = _ORDINAL_RANK.get(c, -1)
                if rank > best_rank:
                    best_rank = rank
                    best_conf = c
            if best_conf:
                article.confidence = best_conf
        article.claim_inventory = claim_inventory
    lifecycle = _determine_lifecycle(compiled_payload, article)
    compiled = compile_shape_from_payload(compiled_payload)
    compile_mode = "failed"
    if compiled_payload and compiled_payload.get("prepare_only"):
        compile_mode = "prepare-only"
    elif compiled_payload and compiled_payload.get("schema_version") == "2.0":
        compile_mode = "llm-v2"
    elif compiled:
        compile_mode = "llm"

    _brief_pdf_path = ""
    if compiled:
        # Extract enhanced fields from v2 payload
        _cross_insights = []
        _article_type = ""
        if compiled_payload and compiled_payload.get("schema_version") == "2.0":
            _result = compiled_payload.get("result", {}) if isinstance(compiled_payload.get("result"), dict) else {}
            _cross_insights = _result.get("cross_domain_insights", []) if isinstance(_result.get("cross_domain_insights"), list) else []
            _ct = compiled_payload.get("compile_target", {}) if isinstance(compiled_payload.get("compile_target"), dict) else {}
            _article_type = str(_ct.get("article_type", "")).strip()
        write_page(brief_path, build_brief_page_from_compile(
            article, slug, compiled, lifecycle,
            cross_domain_insights=_cross_insights,
            article_type=_article_type,
        ), force)
        write_page(source_path, build_source_page_from_compile(vault, article, slug, compiled, lifecycle), force)
        # --- Generate brief PDF ---
        _brief_pdf_path = ""
        try:
            from .pdf_utils import brief_to_pdf as _brief_to_pdf
            pdf_result = _brief_to_pdf(brief_path, title=f"{article.title} - 简报")
            if pdf_result:
                _brief_pdf_path = str(pdf_result)
        except Exception:
            pass  # PDF generation is non-critical
    else:
        # No heuristic fallback — compile failed, return without generating pages
        return {
            "title": article.title,
            "slug": slug,
            "status": "failed",
            "compile_mode": compile_mode,
            "compile_reason": compile_reason_from_payload(compiled_payload, compile_reason),
            "skip_reason": "",
            "quality": article.quality,
            "delta_outputs": "",
        }
    domains_override = compiled_domains_from_payload(compiled_payload)
    emitted_deltas = emit_update_proposals_from_payload(
        vault=vault,
        compiled_payload=compiled_payload,
        source_slug=slug,
        article_title=article.title,
    )
    # --- purpose.md filtering: skip taxonomy pages for excluded content ---
    purpose_filter_active = _apply_purpose_filter(vault, article)

    if not purpose_filter_active:
        ensure_taxonomy_pages(
            vault,
            article,
            slug,
            force,
            domains_override=domains_override,
            compiled_payload=compiled_payload,
            source_lifecycle=lifecycle,
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
        _write_mermaid(vault)
    except Exception:
        pass  # graph rebuild is non-critical; don't block ingestion

    # --- Ensure Obsidian graph filter is configured (idempotent) ---
    try:
        from export_main_graph import write_obsidian_graph_config as _write_obsidian_config
        _write_obsidian_config(vault)
    except Exception:
        pass

    # --- Rebuild domain subgraph pages ---
    try:
        from .graph_layers import build_all_domain_subgraphs as _build_subgraphs
        _build_subgraphs(vault)
    except Exception:
        pass  # subgraph rebuild is non-critical; don't block ingestion

    # --- Claim evolution: now LLM-driven ---
    # Claim evolution analysis is no longer auto-generated after ingest.
    # Use `claim_evolution.py --collect-only` to gather claims, then let LLM
    # analyze relationships per references/prompts/claim_evolution.md.
    # Use `claim_evolution.py --apply <result.json>` to write the page.

    # --- Build ingest impact report ---
    domain_mismatch = detect_domain_mismatch(article, vault, article_domains=domains_override)
    from .ingest_report import build_ingest_impact_report, format_ingest_report
    impact = build_ingest_impact_report(
        vault, slug, article.title, compiled_payload,
        compile_mode=compile_mode, article=article, domain_mismatch=domain_mismatch,
        brief_pdf_path=_brief_pdf_path, delta_count=len(emitted_deltas),
    )
    impact_text = format_ingest_report(impact)

    # --- Detect deep research triggers ---
    try:
        from .deep_research_triggers import detect_triggers, format_trigger_suggestions
        triggers = detect_triggers(compiled_payload, vault, source_slug=slug)
        trigger_text = format_trigger_suggestions(triggers)
        if trigger_text:
            impact_text += "\n" + trigger_text
    except Exception:
        pass  # trigger detection is non-critical; don't block ingestion

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
        "brief_pdf": _brief_pdf_path,
    }