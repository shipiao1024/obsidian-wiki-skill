from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import llm_compile_ingest  # noqa: E402


class NormalizeResultV2Tests(unittest.TestCase):
    def test_normalize_result_v2_returns_wrapped_schema(self) -> None:
        result = llm_compile_ingest.normalize_result_v2(
            {
                "version": "2.0",
                "compile_target": {
                    "vault": "D:/vault",
                    "raw_path": "D:/vault/raw/articles/example.md",
                    "slug": "example",
                    "title": "示例文章",
                    "author": "作者",
                    "date": "2026-04-23",
                    "source_url": "https://mp.weixin.qq.com/s/example",
                },
                "document_outputs": {
                    "brief": {
                        "one_sentence": "一句话结论",
                        "key_points": ["要点一", "要点二"],
                        "who_should_read": ["读者"],
                        "why_revisit": ["原因"],
                    },
                    "source": {
                        "core_summary": ["摘要一"],
                        "knowledge_base_relation": ["补充了旧判断"],
                        "contradictions": [],
                        "reinforcements": ["强化了已有结论"],
                    },
                },
                "knowledge_proposals": {
                    "domains": [
                        {
                            "name": "自动驾驶",
                            "action": "link_existing",
                            "reason": "主题高度相关",
                            "confidence": "Supported",
                            "evidence_type": "fact",
                            "grounding_quote": "一句话结论",
                            "evidence": ["证据句"],
                        }
                    ],
                    "concepts": [],
                    "entities": [],
                },
                "update_proposals": [
                    {
                        "target_page": "wiki/syntheses/自动驾驶--综合分析.md",
                        "target_type": "synthesis",
                        "action": "draft_delta",
                        "reason": "需要补充综合判断",
                        "confidence": "Working",
                        "evidence": ["证据句"],
                        "patch": {
                            "mode": "draft_note",
                            "summary_delta": ["新增判断"],
                            "questions_open": ["待验证问题"],
                        },
                    }
                ],
                "claim_inventory": [
                    {
                        "claim": "本文提出新判断",
                        "claim_type": "interpretation",
                        "evidence_type": "inference",
                        "confidence": "Working",
                        "grounding_quote": "证据原文",
                        "evidence": ["证据句"],
                        "suggested_destination": ["source", "synthesis"],
                    }
                ],
                "open_questions": ["还有哪些来源支持该判断？"],
                "cross_domain_insights": [],
                "stance_impacts": [],
                "review_hints": {
                    "priority": "medium",
                    "needs_human_review": True,
                    "suggested_review_targets": ["wiki/syntheses/自动驾驶--综合分析.md"],
                },
            }
        )

        self.assertEqual(result["version"], "2.0")
        self.assertEqual(result["document_outputs"]["brief"]["one_sentence"], "一句话结论")
        self.assertEqual(result["knowledge_proposals"]["domains"][0]["action"], "link_existing")
        self.assertEqual(result["update_proposals"][0]["patch"]["mode"], "draft_note")

    def test_normalize_result_v2_requires_brief_and_source_content(self) -> None:
        with self.assertRaises(RuntimeError):
            llm_compile_ingest.normalize_result_v2(
                {
                    "version": "2.0",
                    "compile_target": {
                        "vault": "D:/vault",
                        "raw_path": "D:/vault/raw/articles/example.md",
                        "slug": "example",
                        "title": "示例文章",
                        "author": "",
                        "date": "",
                        "source_url": "",
                    },
                    "document_outputs": {
                        "brief": {
                            "one_sentence": "",
                            "key_points": [],
                            "who_should_read": [],
                            "why_revisit": [],
                        },
                        "source": {
                            "core_summary": [],
                            "knowledge_base_relation": [],
                            "contradictions": [],
                            "reinforcements": [],
                        },
                    },
                    "knowledge_proposals": {"domains": [], "concepts": [], "entities": []},
                    "update_proposals": [],
                    "claim_inventory": [],
                    "open_questions": [],
                    "review_hints": {
                        "priority": "low",
                        "needs_human_review": False,
                        "suggested_review_targets": [],
                    },
                }
            )

    def test_coerce_confidence_legacy_values(self) -> None:
        """Legacy high/medium/low values are mapped to ordinal labels."""
        self.assertEqual(llm_compile_ingest.coerce_confidence("high"), "Supported")
        self.assertEqual(llm_compile_ingest.coerce_confidence("medium"), "Working")
        self.assertEqual(llm_compile_ingest.coerce_confidence("low"), "Preliminary")

    def test_coerce_confidence_ordinal_values(self) -> None:
        """Ordinal labels pass through unchanged."""
        self.assertEqual(llm_compile_ingest.coerce_confidence("Seeded"), "Seeded")
        self.assertEqual(llm_compile_ingest.coerce_confidence("Preliminary"), "Preliminary")
        self.assertEqual(llm_compile_ingest.coerce_confidence("Working"), "Working")
        self.assertEqual(llm_compile_ingest.coerce_confidence("Supported"), "Supported")
        self.assertEqual(llm_compile_ingest.coerce_confidence("Stable"), "Stable")

    def test_coerce_confidence_invalid_defaults_to_preliminary(self) -> None:
        self.assertEqual(llm_compile_ingest.coerce_confidence("invalid"), "Preliminary")
        self.assertEqual(llm_compile_ingest.coerce_confidence(None), "Preliminary")
        self.assertEqual(llm_compile_ingest.coerce_confidence(42), "Preliminary")

    def test_coerce_evidence_type_valid(self) -> None:
        self.assertEqual(llm_compile_ingest.coerce_evidence_type("fact"), "fact")
        self.assertEqual(llm_compile_ingest.coerce_evidence_type("inference"), "inference")
        self.assertEqual(llm_compile_ingest.coerce_evidence_type("assumption"), "assumption")

    def test_coerce_evidence_type_invalid_defaults_to_assumption(self) -> None:
        self.assertEqual(llm_compile_ingest.coerce_evidence_type("invalid"), "assumption")
        self.assertEqual(llm_compile_ingest.coerce_evidence_type(None), "assumption")

    def test_normalize_claim_inventory_adds_evidence_type_and_grounding(self) -> None:
        """Claims without evidence_type/grounding_quote get defaults."""
        claims = llm_compile_ingest.normalize_claim_inventory(
            [{"claim": "test claim", "claim_type": "fact", "confidence": "Working"}]
        )
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["evidence_type"], "assumption")  # default
        self.assertEqual(claims[0]["grounding_quote"], "")  # default
        self.assertEqual(claims[0]["confidence"], "Working")

    def test_normalize_proposal_list_adds_evidence_fields(self) -> None:
        """Proposals get evidence_type and grounding_quote fields."""
        proposals = llm_compile_ingest.normalize_proposal_list(
            [{"name": "test", "action": "link", "reason": "because", "confidence": "Supported"}]
        )
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["evidence_type"], "assumption")
        self.assertEqual(proposals[0]["grounding_quote"], "")
        self.assertEqual(proposals[0]["confidence"], "Supported")


if __name__ == "__main__":
    unittest.main()
