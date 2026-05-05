"""Validate v2 compile output before page generation.

Performs structural validation (field existence, type, enum),
content grounding validation (quotes traceable to source text),
and evidence density checks (minimum grounded claims).
"""

from __future__ import annotations

import difflib
import re
import sys
import unicodedata

VALID_ORDINAL = {"Seeded", "Preliminary", "Working", "Supported", "Stable"}
VALID_EVIDENCE_TYPE = {"fact", "inference", "assumption", "hypothesis", "disputed", "gap"}
VALID_IMPACT = {"reinforce", "contradict", "extend", "neutral"}
VALID_ACTION = {"link_existing", "create_candidate", "promote_to_official_candidate", "no_page", "defer"}

_EVIDENCE_TYPE_MAP = {
    "observation": "fact", "empirical": "fact", "measurement": "fact", "statistical": "fact",
    "statistic": "fact", "data_point": "fact", "historical_fact": "fact", "direct_observation": "fact",
    "speculation": "hypothesis", "conjecture": "hypothesis", "prediction": "hypothesis",
    "proposed": "hypothesis", "theoretical": "hypothesis", "future_projection": "hypothesis",
    "expert_judgment": "inference", "expert_opinion": "inference", "author_inference": "inference",
    "logical_deduction": "inference", "inductive": "inference", "deductive": "inference",
    "cross_chapter_reinforcement": "inference", "synthesis": "inference", "argument": "inference",
    "reasoning": "inference", "implication": "inference", "extrapolation": "inference",
    "case_study": "inference", "anecdotal": "inference", "analogical": "inference",
    "unsupported": "assumption", "premise": "assumption", "taken_for_granted": "assumption",
    "implicit": "assumption", "axiom": "assumption", "foundational": "assumption",
    "controversial": "disputed", "debated": "disputed", "contradictory": "disputed",
    "challenged": "disputed", "contrary_evidence": "disputed", "opposing_view": "disputed",
    "missing": "gap", "absent": "gap", "unaddressed": "gap", "unknown": "gap",
    "under_researched": "gap", "lack_of_evidence": "gap", "open_question": "gap",
}

_IMPACT_MAP = {
    "推翻": "contradict", "否定": "contradict", "反驳": "contradict", "contradiction": "contradict",
    "反对": "contradict", "挑战": "contradict", "conflict": "contradict", "refute": "contradict",
    "修正": "extend", "扩展": "extend", "深化": "extend", "补充": "extend", "细化": "extend",
    "extension": "extend", "refinement": "extend", "elaboration": "extend", "nuance": "extend",
    "支持": "reinforce", "强化": "reinforce", "确认": "reinforce", "验证": "reinforce",
    "reinforcement": "reinforce", "confirmation": "reinforce", "corroboration": "reinforce",
    "中立": "neutral", "无关": "neutral", "independent": "neutral", "parallel": "neutral",
}


def _map_evidence_type(raw: str) -> str:
    """Map a custom evidence_type to a valid enum, or return default 'assumption'."""
    key = raw.lower().replace(" ", "_").replace("-", "_")
    if key in VALID_EVIDENCE_TYPE:
        return key
    mapped = _EVIDENCE_TYPE_MAP.get(key)
    if mapped:
        print(f"[validate] evidence_type mapped: {raw} → {mapped}", file=sys.stderr)
        return mapped
    for map_key, map_val in _EVIDENCE_TYPE_MAP.items():
        if map_key in key:
            print(f"[validate] evidence_type mapped: {raw} → {map_val}", file=sys.stderr)
            return map_val
    print(f"[validate] evidence_type default: {raw} → assumption", file=sys.stderr)
    return "assumption"


def _map_impact(raw: str) -> str:
    """Map a descriptive impact to a valid enum, or return default 'neutral'."""
    raw_lower = raw.lower().strip()
    if raw_lower in VALID_IMPACT:
        return raw_lower
    mapped = _IMPACT_MAP.get(raw_lower)
    if mapped:
        print(f"[validate] impact mapped: {raw} → {mapped}", file=sys.stderr)
        return mapped
    for key, val in _IMPACT_MAP.items():
        if key in raw_lower:
            print(f"[validate] impact mapped: {raw} → {val}", file=sys.stderr)
            return val
    print(f"[validate] impact default: {raw} → neutral", file=sys.stderr)
    return "neutral"


# ---------------------------------------------------------------------------
# Structural validation
# ---------------------------------------------------------------------------

def validate_compile_result(payload: dict) -> tuple[bool, str]:
    """Validate v2 compile output structure and field legality.

    Returns (is_valid, reason).
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

    # Validate stance_impacts entries (auto-map invalid impact values)
    stance_impacts = result.get("stance_impacts") if isinstance(result.get("stance_impacts"), list) else []
    for entry in stance_impacts:
        if not isinstance(entry, dict):
            continue
        impact = str(entry.get("impact", "")).strip()
        if impact and impact.lower() not in VALID_IMPACT:
            entry["impact"] = _map_impact(impact)

    # Validate open_questions — auto-convert objects to strings
    open_questions = result.get("open_questions") if isinstance(result.get("open_questions"), list) else []
    converted_oq = []
    needs_conversion = False
    for q in open_questions:
        if isinstance(q, str):
            converted_oq.append(q)
        elif isinstance(q, dict):
            text = q.get("question") or q.get("text") or str(q)
            converted_oq.append(text)
            needs_conversion = True
        else:
            converted_oq.append(str(q))
            needs_conversion = True
    if needs_conversion:
        result["open_questions"] = converted_oq
        print("[validate] Converted open_questions objects to strings", file=sys.stderr)

    # Validate knowledge_proposals: ordinal confidence + evidence_type
    proposals = result.get("knowledge_proposals") if isinstance(result.get("knowledge_proposals"), dict) else {}
    for category in ("domains", "concepts", "entities"):
        items = proposals.get(category) if isinstance(proposals.get(category), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            conf = str(item.get("confidence", "")).strip()
            if conf and conf not in VALID_ORDINAL:
                return False, f"knowledge_proposals.{category} contains invalid confidence '{conf}'"
            etype = str(item.get("evidence_type", "")).strip().lower()
            if etype and etype not in VALID_EVIDENCE_TYPE:
                item["evidence_type"] = _map_evidence_type(etype)

    # Validate update_proposals: ordinal confidence
    update_proposals = result.get("update_proposals") if isinstance(result.get("update_proposals"), list) else []
    for item in update_proposals:
        if not isinstance(item, dict):
            continue
        conf = str(item.get("confidence", "")).strip()
        if conf and conf not in VALID_ORDINAL:
            return False, f"update_proposals contains invalid confidence '{conf}'"

    # Validate claim_inventory: ordinal confidence + evidence_type (auto-map)
    claim_inventory = result.get("claim_inventory") if isinstance(result.get("claim_inventory"), list) else []
    for item in claim_inventory:
        if not isinstance(item, dict):
            continue
        conf = str(item.get("confidence", "")).strip()
        if conf and conf not in VALID_ORDINAL:
            return False, f"claim_inventory contains invalid confidence '{conf}'"
        etype = str(item.get("evidence_type", "")).strip().lower()
        if etype and etype not in VALID_EVIDENCE_TYPE:
            item["evidence_type"] = _map_evidence_type(etype)

    # Validate cross_domain_insights structure (soft validation)
    cross_insights = result.get("cross_domain_insights") if isinstance(result.get("cross_domain_insights"), list) else []
    valid_cross_insights = []
    for item in cross_insights:
        if not isinstance(item, dict):
            continue
        mapped_concept = str(item.get("mapped_concept", "")).strip()
        target_domain = str(item.get("target_domain", "")).strip()
        bridge_logic = str(item.get("bridge_logic", "")).strip()
        migration_conclusion = str(item.get("migration_conclusion", "")).strip()
        if not mapped_concept or not target_domain or not bridge_logic:
            continue
        # migration_conclusion is required — skip insights without it
        if not migration_conclusion:
            continue
        conf = str(item.get("confidence", "")).strip()
        if conf and conf not in VALID_ORDINAL:
            continue
        valid_cross_insights.append(item)
    if cross_insights and len(valid_cross_insights) != len(cross_insights):
        result["cross_domain_insights"] = valid_cross_insights

    return True, ""


# ---------------------------------------------------------------------------
# Grounding validation
# ---------------------------------------------------------------------------

def _normalize_for_match(text: str) -> str:
    """Normalize text for fuzzy matching: Unicode NFC, strip Markdown formatting, normalize punctuation."""
    # Unicode NFC normalization (composed form)
    text = unicodedata.normalize("NFC", text)
    # Strip Markdown formatting: **bold**, __bold__, `code`, *italic*, _italic_
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    # Normalize dash variants: – — ― → -
    text = re.sub(r"[–—―]", "-", text)
    # Normalize quote variants: curly double/single -> straight
    text = re.sub("[“”„‟]", '"', text)
    text = re.sub("[‘’‚‛]", "'", text)
    # Remove standalone page/line numbers (PDF headers/footers)
    text = re.sub(r"(?<=\n)\s*\d{1,5}\s*(?=\n)", "", text)
    # Fix mid-sentence line breaks (keep paragraph-level double newlines)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    # Traditional → Simplified Chinese (common 200 chars inline table)
    text = _trad_to_simp(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Inline Traditional→Simplified Chinese mapping (most common chars)
_TRAD_SIMP_MAP = str.maketrans(
    "萬與來專對從開時書會發無國過話說學應關點經問題動產場種實區結強進當務頭長將車體還這邊運裝設認條達際斷檢擔權",
    "万与来专对从开时书会发无国过话说学应关点经问题动产场种实区结强进当务头长将车体还这边运装设认条达际断检担权"
)


def _trad_to_simp(text: str) -> str:
    """Best-effort Traditional → Simplified Chinese conversion."""
    try:
        import opencc
        cc = opencc.OpenCC("t2s")
        return cc.convert(text)
    except ImportError:
        return text.translate(_TRAD_SIMP_MAP)


def grounding_validate(payload: dict, raw_text: str, transcript_stage: str | None = None) -> tuple[bool, list[str]]:
    """Check that grounding_quote values appear in the source text.

    Returns (passed, violations). A violation means the LLM may have
    fabricated a quote that does not exist in the original article.
    Empty grounding_quotes are NOT violations (they get marked
    [Assumption-anchored] downstream).

    When transcript_stage == "asr", falls back to fuzzy matching
    (difflib.SequenceMatcher threshold 0.85) after exact match fails.
    """
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    violations: list[str] = []
    normalized_source = _normalize_for_match(raw_text)
    fuzzy_threshold = 0.85 if transcript_stage == "asr" else 0.0

    # Check claim_inventory
    claims = result.get("claim_inventory") if isinstance(result.get("claim_inventory"), list) else []
    for i, item in enumerate(claims):
        if not isinstance(item, dict):
            continue
        quote = str(item.get("grounding_quote", "")).strip()
        if not quote:
            continue  # empty quote is allowed, not a violation
        normalized_quote = _normalize_for_match(quote)
        if normalized_quote not in normalized_source:
            # Try substring match with first 30 chars as fallback
            snippet = normalized_quote[:30]
            if snippet and snippet not in normalized_source:
                # Try fuzzy matching for ASR sources
                if fuzzy_threshold > 0:
                    ratio = difflib.SequenceMatcher(None, normalized_quote, normalized_source).find_longest_match(0, len(normalized_quote), 0, len(normalized_source))
                    if ratio.size / len(normalized_quote) >= fuzzy_threshold:
                        continue  # fuzzy match acceptable for ASR
                    violations.append(
                        f"claim_inventory[{i}] grounding_quote not found (ASR fuzzy match failed, ratio={ratio.size / len(normalized_quote):.2f}): '{quote[:60]}...'"
                    )
                else:
                    violations.append(
                        f"claim_inventory[{i}] grounding_quote not found in source: '{quote[:60]}...'"
                    )

    # Check knowledge_proposals
    proposals = result.get("knowledge_proposals") if isinstance(result.get("knowledge_proposals"), dict) else {}
    for category in ("domains", "concepts", "entities"):
        items = proposals.get(category) if isinstance(proposals.get(category), list) else []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            quote = str(item.get("grounding_quote", "")).strip()
            if not quote:
                continue
            normalized_quote = _normalize_for_match(quote)
            if normalized_quote not in normalized_source:
                snippet = normalized_quote[:30]
                if snippet and snippet not in normalized_source:
                    if fuzzy_threshold > 0:
                        ratio = difflib.SequenceMatcher(None, normalized_quote, normalized_source).find_longest_match(0, len(normalized_quote), 0, len(normalized_source))
                        if ratio.size / len(normalized_quote) >= fuzzy_threshold:
                            continue
                        violations.append(
                            f"knowledge_proposals.{category}[{i}] grounding_quote not found (ASR fuzzy match failed): '{quote[:60]}...'"
                        )
                    else:
                        violations.append(
                            f"knowledge_proposals.{category}[{i}] grounding_quote not found in source: '{quote[:60]}...'"
                        )

    return len(violations) == 0, violations


# ---------------------------------------------------------------------------
# Evidence density check
# ---------------------------------------------------------------------------

_ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}


def density_check(payload: dict) -> tuple[str, list[str]]:
    """Evidence density check. Returns (maturity_level, warnings).

    maturity_level:
      - "grounded": has fact/inference claims with grounding quotes
      - "compiled": has claims but none fully grounded
      - "raw": no claims or all assumption/hypothesis without grounding
    """
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    claims = result.get("claim_inventory") if isinstance(result.get("claim_inventory"), list) else []
    warnings: list[str] = []

    if not claims:
        return "raw", ["claim_inventory is empty"]

    fact_count = 0
    inference_count = 0
    grounded_count = 0
    assumption_anchored_count = 0

    for item in claims:
        if not isinstance(item, dict):
            continue
        etype = str(item.get("evidence_type", "")).strip().lower()
        quote = str(item.get("grounding_quote", "")).strip()
        if etype == "fact":
            fact_count += 1
        elif etype == "inference":
            inference_count += 1
        if etype in ("fact", "inference") and quote:
            grounded_count += 1
        if etype in ("assumption", "hypothesis") and not quote:
            assumption_anchored_count += 1

    # Determine maturity
    if grounded_count > 0:
        maturity = "grounded"
    elif fact_count + inference_count > 0:
        maturity = "compiled"
        warnings.append("fact/inference claims exist but none have grounding_quote")
    else:
        maturity = "raw"
        warnings.append("no fact/inference claims — all conclusions are [Assumption-anchored]")

    if assumption_anchored_count > 0:
        warnings.append(f"{assumption_anchored_count} claims are [Assumption-anchored] (no grounding_quote)")

    return maturity, warnings


def max_confidence_ordinal(payload: dict) -> str:
    """Return the highest confidence ordinal found in claim_inventory."""
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    claims = result.get("claim_inventory") if isinstance(result.get("claim_inventory"), list) else []
    best_rank = -1
    best_label = "Seeded"
    for item in claims:
        if not isinstance(item, dict):
            continue
        conf = str(item.get("confidence", "")).strip()
        rank = _ORDINAL_RANK.get(conf, 0)
        if rank > best_rank:
            best_rank = rank
            best_label = conf
    return best_label
