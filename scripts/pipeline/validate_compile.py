"""Validate v2 compile output before page generation.

If validation fails, the ingest pipeline falls back to heuristic
(brief + source pages without LLM-compiled proposals).
"""

from __future__ import annotations

VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_IMPACT = {"reinforce", "contradict", "extend", "neutral"}
VALID_ACTION = {"link_existing", "create_candidate", "promote_to_official_candidate", "no_page", "defer"}


def validate_compile_result(payload: dict) -> tuple[bool, str]:
    """Validate v2 compile output structure and field legality.

    Returns (is_valid, reason). Validation failure triggers heuristic fallback.
    """
    if not isinstance(payload, dict):
        return False, "payload is not a dict"

    # Must have schema_version == "2.0"
    version = str(payload.get("schema_version", "")).strip()
    if version != "2.0":
        return False, f"schema_version is '{version}', expected '2.0'"

    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload

    # Must have document_outputs.brief.one_sentence (non-empty)
    doc_out = result.get("document_outputs") if isinstance(result.get("document_outputs"), dict) else {}
    brief = doc_out.get("brief") if isinstance(doc_out.get("brief"), dict) else {}
    one_sentence = str(brief.get("one_sentence", "")).strip()
    if not one_sentence:
        return False, "document_outputs.brief.one_sentence is empty"

    # Must have document_outputs.brief.key_points (non-empty list)
    key_points = brief.get("key_points")
    if not isinstance(key_points, list) or len(key_points) == 0:
        return False, "document_outputs.brief.key_points is empty or not a list"

    # Must have document_outputs.source.core_summary (non-empty list)
    source = doc_out.get("source") if isinstance(doc_out.get("source"), dict) else {}
    core_summary = source.get("core_summary")
    if not isinstance(core_summary, list) or len(core_summary) == 0:
        return False, "document_outputs.source.core_summary is empty or not a list"

    # Validate stance_impacts entries
    stance_impacts = result.get("stance_impacts") if isinstance(result.get("stance_impacts"), list) else []
    for entry in stance_impacts:
        if not isinstance(entry, dict):
            continue
        impact = str(entry.get("impact", "")).strip().lower()
        if impact and impact not in VALID_IMPACT:
            return False, f"stance_impacts contains invalid impact '{impact}'"

    # Validate open_questions is a string list
    open_questions = result.get("open_questions") if isinstance(result.get("open_questions"), list) else []
    for q in open_questions:
        if not isinstance(q, str):
            return False, "open_questions contains non-string entry"

    # Validate confidence values in proposals and claims
    proposals = result.get("knowledge_proposals") if isinstance(result.get("knowledge_proposals"), dict) else {}
    for category in ("domains", "concepts", "entities"):
        items = proposals.get(category) if isinstance(proposals.get(category), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            conf = str(item.get("confidence", "")).strip().lower()
            if conf and conf not in VALID_CONFIDENCE:
                return False, f"knowledge_proposals.{category} contains invalid confidence '{conf}'"

    update_proposals = result.get("update_proposals") if isinstance(result.get("update_proposals"), list) else []
    for item in update_proposals:
        if not isinstance(item, dict):
            continue
        conf = str(item.get("confidence", "")).strip().lower()
        if conf and conf not in VALID_CONFIDENCE:
            return False, f"update_proposals contains invalid confidence '{conf}'"

    claim_inventory = result.get("claim_inventory") if isinstance(result.get("claim_inventory"), list) else []
    for item in claim_inventory:
        if not isinstance(item, dict):
            continue
        conf = str(item.get("confidence", "")).strip().lower()
        if conf and conf not in VALID_CONFIDENCE:
            return False, f"claim_inventory contains invalid confidence '{conf}'"

    # Validate cross_domain_insights structure
    cross_insights = result.get("cross_domain_insights") if isinstance(result.get("cross_domain_insights"), list) else []
    for item in cross_insights:
        if not isinstance(item, dict):
            return False, "cross_domain_insights contains non-dict entry"
        mapped_concept = str(item.get("mapped_concept", "")).strip()
        target_domain = str(item.get("target_domain", "")).strip()
        bridge_logic = str(item.get("bridge_logic", "")).strip()
        if not mapped_concept:
            return False, "cross_domain_insights entry missing mapped_concept"
        if not target_domain:
            return False, "cross_domain_insights entry missing target_domain"
        if not bridge_logic:
            return False, "cross_domain_insights entry missing bridge_logic"
        conf = str(item.get("confidence", "")).strip().lower()
        if conf and conf not in VALID_CONFIDENCE:
            return False, f"cross_domain_insights contains invalid confidence '{conf}'"

    return True, ""