"""LLM compile wrapper: try_llm_compile and payload shape helpers.

Four explicit compile modes (no auto-degradation):
  - "prepare-only" (default): generate payload for LLM agent to compile in conversation
  - "chunked-prepare": split large docs into chunks, generate per-chunk payloads
  - "api-compile": call OpenAI-compatible API directly (unattended batch)
  - "heuristic": no LLM, heuristic extraction only
"""

from __future__ import annotations

from pathlib import Path

from pipeline.shared import Article, sanitize_filename

_COMPILE_MODES = {"prepare-only", "chunked-prepare", "api-compile", "heuristic"}


def try_llm_compile(
    vault: Path,
    article: Article,
    slug: str,
    raw_path: Path,
    disabled: bool = False,
    *,
    mode: str = "prepare-only",
    chunk_size: int = 500,
) -> tuple[dict[str, object] | None, str | None]:
    """Try LLM compile with explicit mode selection.

    Args:
        disabled: Legacy flag, equivalent to mode="heuristic".
        mode: "prepare-only" | "chunked-prepare" | "api-compile" | "heuristic".
        chunk_size: Line count per chunk for chunked-prepare mode.
    """
    # Legacy compatibility: --no-llm-compile overrides mode
    if disabled:
        mode = "heuristic"

    if mode == "heuristic":
        return None, "LLM compile disabled — using heuristic fallback."

    if mode == "chunked-prepare":
        try:
            from llm_compile_ingest import prepare_chunked_payloads
            payload = prepare_chunked_payloads(
                vault=vault,
                raw_path=raw_path,
                title=article.title,
                author=article.author,
                date=article.date,
                source_url=article.source,
                slug=slug,
                chunk_size=chunk_size,
            )
            payload["prepare_only"] = True
            return payload, "chunked-prepare payloads generated. LLM should process each chunk then synthesize."
        except Exception as exc:
            return None, f"chunked-prepare failed: {exc}"

    if mode == "prepare-only":
        try:
            from llm_compile_ingest import prepare_compile_payload_v2
            payload = prepare_compile_payload_v2(
                vault=vault,
                raw_path=raw_path,
                title=article.title,
                author=article.author,
                date=article.date,
                source_url=article.source,
                slug=slug,
            )
            payload["prepare_only"] = True
            return payload, "prepare-only payload generated. LLM should compile interactively."
        except Exception as exc:
            return None, f"prepare-only failed: {exc}"

    if mode == "api-compile":
        try:
            from llm_compile_ingest import compile_article_auto as llm_compile_article
            payload = llm_compile_article(
                vault=vault,
                raw_path=raw_path,
                title=article.title,
                author=article.author,
                date=article.date,
                source_url=article.source,
                slug=slug,
                schema_version="2.0",
            )
            from .validate_compile import validate_compile_result
            is_valid, reason = validate_compile_result(payload)
            if not is_valid:
                return None, f"Compile validation failed: {reason}"
            return payload, None
        except RuntimeError as exc:
            if "not configured" in str(exc).lower():
                return None, "API key not configured. Set WECHAT_WIKI_API_KEY or use default prepare-only mode."
            return None, str(exc)
        except Exception as exc:
            return None, str(exc)

    return None, f"Unknown compile mode: {mode}"


def try_llm_compile_two_step(
    vault: Path,
    article: Article,
    slug: str,
    raw_path: Path,
    disabled: bool = False,
    *,
    mode: str = "prepare-only",
) -> tuple[dict[str, object] | None, str | None]:
    """Two-step CoT compile: extract facts first, then compile wiki structure.

    Only works in api-compile mode. Falls back to prepare-only for other modes.
    """
    if disabled:
        mode = "heuristic"

    if mode == "heuristic":
        return None, "LLM compile disabled — using heuristic fallback."

    if mode == "prepare-only":
        try:
            from llm_compile_ingest import prepare_compile_payload_v2
            payload = prepare_compile_payload_v2(
                vault=vault,
                raw_path=raw_path,
                title=article.title,
                author=article.author,
                date=article.date,
                source_url=article.source,
                slug=slug,
            )
            payload["prepare_only"] = True
            return payload, "prepare-only payload generated. LLM should compile interactively."
        except Exception as exc:
            return None, f"prepare-only failed: {exc}"

    if mode == "api-compile":
        try:
            from llm_compile_ingest import compile_article_two_step
            payload = compile_article_two_step(
                vault=vault,
                raw_path=raw_path,
                title=article.title,
                author=article.author,
                date=article.date,
                source_url=article.source,
                slug=slug,
            )
            from .validate_compile import validate_compile_result
            is_valid, reason = validate_compile_result(payload)
            if not is_valid:
                return None, f"Compile validation failed: {reason}"
            return payload, None
        except RuntimeError as exc:
            if "not configured" in str(exc).lower():
                return None, "API key not configured. Set WECHAT_WIKI_API_KEY or use default prepare-only mode."
            return None, str(exc)
        except Exception as exc:
            return None, str(exc)

    return None, f"Unknown compile mode: {mode}"


def compile_reason_from_payload(compiled_payload: dict[str, object] | None, compile_reason: str | None) -> str:
    if compiled_payload:
        if compiled_payload.get("prepare_only"):
            return "prepare-only payload generated."
        if compiled_payload.get("schema_version") == "2.0":
            return "LLM compile v2 succeeded."
        return "LLM compile succeeded."
    if compile_reason:
        return compile_reason
    return "Compile failed — no pages generated."


def compile_shape_from_payload(compiled_payload: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(compiled_payload, dict):
        return None
    # Prepare-only and chunked-prepare payloads skip page generation
    if compiled_payload.get("prepare_only"):
        return None
    if compiled_payload.get("schema_version") != "2.0":
        result = compiled_payload.get("result")
        return result if isinstance(result, dict) else compiled_payload
    result = compiled_payload.get("result")
    if not isinstance(result, dict):
        return None
    document_outputs = result.get("document_outputs") if isinstance(result.get("document_outputs"), dict) else {}
    source = document_outputs.get("source") if isinstance(document_outputs.get("source"), dict) else {}
    knowledge_proposals = result.get("knowledge_proposals") if isinstance(result.get("knowledge_proposals"), dict) else {}
    domains: list[str] = []
    candidate_concepts: list[str] = []
    candidate_entities: list[str] = []
    for item in knowledge_proposals.get("domains", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
        action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
        if name and action != "no_page":
            domains.append(name)
    for item in knowledge_proposals.get("concepts", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
        action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
        if name and action == "create_candidate":
            candidate_concepts.append(name)
    for item in knowledge_proposals.get("entities", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
        action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
        if name and action == "create_candidate":
            candidate_entities.append(name)
    claim_inventory_raw = result.get("claim_inventory") if isinstance(result, dict) else []
    claim_inventory = [c for c in claim_inventory_raw if isinstance(c, dict)] if isinstance(claim_inventory_raw, list) else []
    return {
        "brief": document_outputs.get("brief", {}),
        "source": {
            "core_summary": source.get("core_summary", []),
            "candidate_concepts": candidate_concepts,
            "candidate_entities": candidate_entities,
            "domains": domains,
            "knowledge_base_relation": source.get("knowledge_base_relation", []),
            "contradictions": source.get("contradictions", []),
            "reinforcements": source.get("reinforcements", []),
        },
        "claim_inventory": claim_inventory,
    }


def compiled_domains_from_payload(compiled_payload: dict[str, object] | None) -> list[str] | None:
    if not isinstance(compiled_payload, dict):
        return None
    if compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result")
        knowledge_proposals = result.get("knowledge_proposals") if isinstance(result, dict) else {}
        items = knowledge_proposals.get("domains") if isinstance(knowledge_proposals, dict) else []
        values: list[str] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
                action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
                if name and action != "no_page":
                    values.append(name)
        return values or None
    result = compiled_payload.get("result")
    compiled_source = result.get("source") if isinstance(result, dict) else None
    compiled_domains = compiled_source.get("domains") if isinstance(compiled_source, dict) else None
    if isinstance(compiled_domains, list):
        values = [item for item in compiled_domains if isinstance(item, str) and item.strip()]
        return values or None
    return None


def promoted_taxonomy_names_from_payload(
    compiled_payload: dict[str, object] | None,
    kind: str,
) -> list[str]:
    if not isinstance(compiled_payload, dict) or compiled_payload.get("schema_version") != "2.0":
        return []
    result = compiled_payload.get("result")
    knowledge_proposals = result.get("knowledge_proposals") if isinstance(result, dict) else {}
    proposals = knowledge_proposals.get(kind) if isinstance(knowledge_proposals, dict) else []
    names: list[str] = []
    if not isinstance(proposals, list):
        return names
    for item in proposals:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
        action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
        if name and action == "promote_to_official_candidate" and name not in names:
            names.append(name)
    return names


def build_delta_page_from_update_proposal_local(
    proposal: dict[str, object],
    source_slug: str,
    article_title: str,
) -> tuple[str, str]:
    target_page = proposal.get("target_page", "").strip() if isinstance(proposal.get("target_page"), str) else ""
    target_type = proposal.get("target_type", "").strip() if isinstance(proposal.get("target_type"), str) else "source"
    action = proposal.get("action", "").strip() if isinstance(proposal.get("action"), str) else "draft_delta"
    reason = proposal.get("reason", "").strip() if isinstance(proposal.get("reason"), str) else "待人工审核。"
    confidence = proposal.get("confidence", "Preliminary")
    evidence = proposal.get("evidence", []) if isinstance(proposal.get("evidence"), list) else []
    patch = proposal.get("patch") if isinstance(proposal.get("patch"), dict) else {}
    claims = proposal.get("claims") if isinstance(proposal.get("claims"), list) else []
    # Determine if this delta has actual draft content (for review queue prioritization)
    summary_delta = patch.get("summary_delta", []) if isinstance(patch.get("summary_delta"), list) else []
    content = patch.get("content", []) if isinstance(patch.get("content"), list) else []
    questions_open = patch.get("questions_open", []) if isinstance(patch.get("questions_open"), list) else []
    has_draft = bool(summary_delta or content or questions_open)
    slug = sanitize_filename(f"delta-{source_slug}-{Path(target_page).stem or target_type}")
    lines = [
        "---",
        f'title: "{article_title} Delta Proposal"',
        'type: "delta-compile"',
        'status: "review-needed"',
        'lifecycle: "review-needed"',
        'graph_role: "working"',
        'graph_include: "false"',
        f'source_page: "wiki/sources/{source_slug}.md"',
        f'target_page: "{target_page}"',
        f'target_type: "{target_type}"',
        f'has_draft: "{str(has_draft).lower()}"',
        "---",
        "",
        "# Delta Proposal",
        "",
        "## 目标页面",
        "",
        f"- `{target_page or 'unknown'}`",
        "",
        "## 动作",
        "",
        f"- `{action}`",
        "",
        "## 原因",
        "",
        f"- {reason}",
        "",
        "## 置信度",
        "",
        f"- {confidence}",
        "",
        "## 证据",
        "",
    ]
    lines.extend(f"- {item}" for item in evidence[:6])
    if not evidence:
        lines.append("- 待人工补充证据。")
    lines.extend(["", "## 关键判断", ""])
    wrote_claim = False
    for item in claims[:6]:
        if not isinstance(item, dict):
            continue
        claim = item.get("claim", "").strip() if isinstance(item.get("claim"), str) else ""
        claim_type = item.get("claim_type", "").strip() if isinstance(item.get("claim_type"), str) else "interpretation"
        confidence_label = item.get("confidence", "low")
        if claim:
            lines.append(f"- [{claim_type}|{confidence_label}] {claim}")
            wrote_claim = True
    if not wrote_claim:
        lines.append("- 待人工补充关键判断。")
    lines.extend(["", "## 建议修改", ""])
    lines.extend(f"- {item}" for item in summary_delta[:6])
    lines.extend(f"- {item}" for item in content[:6])
    lines.extend(f"- 待验证：{item}" for item in questions_open[:4])
    if not summary_delta and not content and not questions_open:
        lines.append("- 待人工补充草稿内容。")
    lines.append("")
    return slug, "\n".join(lines)


def emit_update_proposals_from_payload(
    *,
    vault: Path,
    compiled_payload: dict[str, object] | None,
    source_slug: str,
    article_title: str,
) -> list[Path]:
    if not isinstance(compiled_payload, dict) or compiled_payload.get("schema_version") != "2.0":
        return []
    result = compiled_payload.get("result")
    proposals = result.get("update_proposals") if isinstance(result, dict) else []
    claim_inventory = result.get("claim_inventory") if isinstance(result, dict) else []
    claim_items = claim_inventory if isinstance(claim_inventory, list) else []
    normalized_claims = [item for item in claim_items if isinstance(item, dict)]
    if not isinstance(proposals, list):
        return []
    outputs_dir = vault / "wiki" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    emitted: list[Path] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        materialized = dict(proposal)
        if not isinstance(materialized.get("claims"), list):
            materialized["claims"] = normalized_claims
        slug, page = build_delta_page_from_update_proposal_local(materialized, source_slug, article_title)
        path = outputs_dir / f"{slug}.md"
        path.write_text(page, encoding="utf-8")
        emitted.append(path)
    return emitted