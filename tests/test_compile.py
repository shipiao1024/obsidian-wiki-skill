"""Tests for pipeline/compile.py — compile shape extraction and helpers."""

from __future__ import annotations

import pytest

from pipeline.compile import (
    compile_shape_from_payload,
    compile_reason_from_payload,
    compiled_domains_from_payload,
)


class TestCompileShapeExtraction:
    """T5: compile_shape_from_payload and related helpers."""

    def test_v2_payload_extracts_brief_and_source(self, v2_payload):
        result = compile_shape_from_payload(v2_payload)
        assert result is not None
        assert "brief" in result
        assert "source" in result
        assert result["brief"]["one_sentence"] == "This is a test one-sentence summary."

    def test_v2_payload_extracts_claim_inventory(self, v2_payload):
        result = compile_shape_from_payload(v2_payload)
        assert "claim_inventory" in result
        assert len(result["claim_inventory"]) == 2

    def test_v2_payload_extracts_domains(self, v2_payload):
        result = compile_shape_from_payload(v2_payload)
        assert "AI 工程" in result["source"]["domains"]

    def test_v1_payload_falls_back_gracefully(self):
        v1_payload = {
            "schema_version": "1.0",
            "result": {
                "source": {"domains": ["Test Domain"]},
            },
        }
        result = compile_shape_from_payload(v1_payload)
        assert result is not None

    def test_none_payload_returns_none(self):
        result = compile_shape_from_payload(None)
        assert result is None

    def test_invalid_payload_returns_none(self):
        result = compile_shape_from_payload("not a dict")
        assert result is None

    def test_domains_with_no_page_action_excluded(self, v2_payload):
        v2_payload["result"]["knowledge_proposals"]["domains"].append(
            {"name": "Excluded Domain", "confidence": "Preliminary", "action": "no_page"}
        )
        result = compile_shape_from_payload(v2_payload)
        assert "Excluded Domain" not in result["source"]["domains"]

    def test_compile_reason_with_payload(self):
        reason = compile_reason_from_payload({"schema_version": "2.0"}, None)
        assert "v2" in reason

    def test_compile_reason_without_payload(self):
        reason = compile_reason_from_payload(None, "Some error")
        assert "Some error" in reason

    def test_compile_reason_no_payload_no_reason(self):
        reason = compile_reason_from_payload(None, None)
        assert "Compile failed" in reason

    def test_compiled_domains_from_v2(self, v2_payload):
        domains = compiled_domains_from_payload(v2_payload)
        assert domains is not None
        assert "AI 工程" in domains

    def test_compiled_domains_from_none(self):
        domains = compiled_domains_from_payload(None)
        assert domains is None
