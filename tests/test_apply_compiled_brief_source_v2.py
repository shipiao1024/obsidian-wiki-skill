from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import apply_compiled_brief_source  # noqa: E402


class ApplyCompiledV2Tests(unittest.TestCase):
    def test_load_compiled_json_any_wraps_v2_payload(self) -> None:
        tmp_dir = ROOT / ".tmp-tests"
        tmp_dir.mkdir(exist_ok=True)
        path = tmp_dir / "compiled-v2.json"
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        path.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "document_outputs": {
                        "brief": {
                            "one_sentence": "一句话",
                            "key_points": ["a"],
                            "who_should_read": [],
                            "why_revisit": [],
                        },
                        "source": {
                            "core_summary": ["b"],
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
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        payload = apply_compiled_brief_source.load_compiled_json_any(path)

        self.assertEqual(payload["schema_version"], "2.0")
        self.assertIn("document_outputs", payload["result"])

    def test_build_delta_page_from_update_proposal_renders_review_needed_page(self) -> None:
        slug, page = apply_compiled_brief_source.build_delta_page_from_update_proposal(
            proposal={
                "target_page": "wiki/syntheses/自动驾驶--综合分析.md",
                "target_type": "synthesis",
                "action": "draft_delta",
                "reason": "需要补充综合判断",
                "confidence": "Working",
                "evidence": ["证据句一", "证据句二"],
                "patch": {
                    "mode": "draft_note",
                    "summary_delta": ["新增判断"],
                    "questions_open": ["待验证问题"],
                },
            },
            source_slug="2026-04-23--example",
            article_title="示例文章",
        )

        self.assertIn("delta-", slug)
        self.assertIn('type: "delta-compile"', page)
        self.assertIn('status: "review-needed"', page)
        self.assertIn("## 建议修改", page)

    def test_build_delta_page_from_update_proposal_includes_claim_inventory(self) -> None:
        slug, page = apply_compiled_brief_source.build_delta_page_from_update_proposal(
            proposal={
                "target_page": "wiki/sources/example.md",
                "target_type": "source",
                "action": "append_section_note",
                "reason": "补充来源页判断",
                "confidence": "Supported",
                "evidence": ["证据句"],
                "claims": [
                    {
                        "claim": "本文认为中央计算会加强跨域协同。",
                        "claim_type": "interpretation",
                        "confidence": "Working",
                    }
                ],
                "patch": {"mode": "draft_note"},
            },
            source_slug="2026-04-23--example",
            article_title="示例文章",
        )

        self.assertIn("## 关键判断", page)
        self.assertIn("interpretation", page)
        self.assertIn("中央计算会加强跨域协同", page)


if __name__ == "__main__":
    unittest.main()
