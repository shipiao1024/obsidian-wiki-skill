"""Tests for pipeline/validate_compile.py — the compile validation gate."""

from __future__ import annotations

import copy

import pytest

from pipeline.validate_compile import validate_compile_result, grounding_validate, density_check


class TestValidateCompile:
    """T1: Validate compile result structural integrity."""

    def test_valid_v2_result_passes(self, v2_payload):
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True
        assert reason == ""

    def test_non_dict_payload_fails(self):
        is_valid, reason = validate_compile_result("not a dict")
        assert is_valid is False
        assert "not a dict" in reason

    def test_missing_schema_version_fails(self, v2_payload):
        del v2_payload["schema_version"]
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is False
        assert "schema_version" in reason

    def test_wrong_schema_version_fails(self, v2_payload):
        v2_payload["schema_version"] = "1.0"
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is False
        assert "1.0" in reason

    def test_missing_one_sentence_fails(self, v2_payload):
        v2_payload["result"]["document_outputs"]["brief"]["one_sentence"] = ""
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is False
        assert "one_sentence" in reason

    def test_empty_key_points_fails(self, v2_payload):
        v2_payload["result"]["document_outputs"]["brief"]["key_points"] = []
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is False
        assert "key_points" in reason

    def test_empty_core_summary_fails(self, v2_payload):
        v2_payload["result"]["document_outputs"]["source"]["core_summary"] = []
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is False
        assert "core_summary" in reason

    def test_invalid_confidence_in_claims_fails(self, v2_payload):
        v2_payload["result"]["claim_inventory"][0]["confidence"] = "invalid"
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is False
        assert "invalid confidence" in reason

    def test_invalid_impact_in_stance_auto_mapped(self, v2_payload):
        """After V1.3.0 enum softening, invalid impact values are auto-mapped, not hard-failed."""
        v2_payload["result"]["stance_impacts"] = [
            {"impact": "invalid_impact"}
        ]
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True
        # Invalid impact should have been mapped to "neutral"
        assert v2_payload["result"]["stance_impacts"][0]["impact"] == "neutral"

    def test_valid_stance_impacts_pass(self, v2_payload):
        v2_payload["result"]["stance_impacts"] = [
            {"impact": "reinforce"},
            {"impact": "contradict"},
            {"impact": "extend"},
            {"impact": "neutral"},
        ]
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True

    def test_non_string_open_question_auto_converted(self, v2_payload):
        """After V1.3.0, non-string open questions are auto-converted, not hard-failed."""
        v2_payload["result"]["open_questions"] = [123]
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True
        # Number should have been converted to string
        assert v2_payload["result"]["open_questions"] == ["123"]

    # --- P0-2 fix: cross_domain_insights soft validation ---

    def test_cross_domain_insights_missing_mapped_concept_skips_not_fails(self, v2_payload):
        """After P0-2 fix, malformed cross_domain_insights entries are skipped, not failed."""
        v2_payload["result"]["cross_domain_insights"] = [
            {
                "mapped_concept": "",  # missing
                "target_domain": "AI",
                "bridge_logic": "some logic",
            },
            {
                "mapped_concept": "Valid Concept",
                "target_domain": "认知科学",
                "bridge_logic": "valid bridge",
                "migration_conclusion": "can apply strategy X",
                "confidence": "Working",
            },
        ]
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True
        # The valid entry should remain
        assert len(v2_payload["result"]["cross_domain_insights"]) == 1

    def test_cross_domain_insights_all_malformed_still_passes(self, v2_payload):
        """Even if all cross_domain_insights are malformed, validation passes."""
        v2_payload["result"]["cross_domain_insights"] = [
            {"mapped_concept": "", "target_domain": "", "bridge_logic": ""},
            "not a dict",
        ]
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True
        assert v2_payload["result"]["cross_domain_insights"] == []

    def test_cross_domain_insights_invalid_confidence_skipped(self, v2_payload):
        v2_payload["result"]["cross_domain_insights"] = [
            {
                "mapped_concept": "X",
                "target_domain": "Y",
                "bridge_logic": "Z",
                "confidence": "invalid_level",
            },
        ]
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True
        assert v2_payload["result"]["cross_domain_insights"] == []

    def test_empty_payload_still_valid(self, v2_payload):
        """Minimal valid v2 payload with no optional fields."""
        v2_payload["result"]["cross_domain_insights"] = []
        v2_payload["result"]["stance_impacts"] = []
        v2_payload["result"]["open_questions"] = []
        v2_payload["result"]["claim_inventory"] = []
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True

    def test_invalid_evidence_type_in_claims_auto_mapped(self, v2_payload):
        """After V1.3.0 enum softening, invalid evidence_type is auto-mapped, not hard-failed."""
        v2_payload["result"]["claim_inventory"][0]["evidence_type"] = "invalid_type"
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is True
        # Invalid evidence_type should have been mapped to "assumption"
        assert v2_payload["result"]["claim_inventory"][0]["evidence_type"] == "assumption"

    def test_invalid_ordinal_confidence_in_proposals_fails(self, v2_payload):
        v2_payload["result"]["knowledge_proposals"]["domains"][0]["confidence"] = "high"
        is_valid, reason = validate_compile_result(v2_payload)
        assert is_valid is False
        assert "confidence" in reason


class TestGroundingValidate:
    """Tests for grounding_validate — quote traceability to source text."""

    def test_matching_quote_passes(self, v2_payload):
        raw_text = "This is a test one-sentence summary. Some other content here."
        passed, violations = grounding_validate(v2_payload, raw_text)
        assert passed is True
        assert violations == []

    def test_non_matching_quote_violates(self, v2_payload):
        raw_text = "Completely different content that does not match any quote."
        passed, violations = grounding_validate(v2_payload, raw_text)
        assert passed is False
        assert len(violations) > 0
        assert "not found in source" in violations[0]

    def test_empty_quote_not_a_violation(self, v2_payload):
        # Clear ALL grounding_quotes to test that empty quotes are not violations
        for claim in v2_payload["result"]["claim_inventory"]:
            claim["grounding_quote"] = ""
        for category in ("domains", "concepts", "entities"):
            for item in v2_payload["result"]["knowledge_proposals"].get(category, []):
                if isinstance(item, dict):
                    item["grounding_quote"] = ""
        raw_text = "Whatever content."
        passed, violations = grounding_validate(v2_payload, raw_text)
        # Empty quotes are not violations (they get [Assumption-anchored])
        assert passed is True


class TestDensityCheck:
    """Tests for density_check — evidence maturity classification."""

    def test_fact_with_grounding_is_grounded(self, v2_payload):
        maturity, warnings = density_check(v2_payload)
        assert maturity == "grounded"

    def test_all_assumption_is_raw(self, v2_payload):
        for claim in v2_payload["result"]["claim_inventory"]:
            claim["evidence_type"] = "assumption"
            claim["grounding_quote"] = ""
        maturity, warnings = density_check(v2_payload)
        assert maturity == "raw"
        assert any("Assumption-anchored" in w for w in warnings)

    def test_empty_claims_is_raw(self, v2_payload):
        v2_payload["result"]["claim_inventory"] = []
        maturity, warnings = density_check(v2_payload)
        assert maturity == "raw"

    def test_fact_without_grounding_is_compiled(self, v2_payload):
        for claim in v2_payload["result"]["claim_inventory"]:
            claim["grounding_quote"] = ""
        maturity, warnings = density_check(v2_payload)
        assert maturity == "compiled"
