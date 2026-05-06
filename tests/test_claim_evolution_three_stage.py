from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import claim_evolution  # noqa: E402


def _make_vault(base: Path) -> Path:
    """Create a vault with claims in sources and syntheses."""
    if base.exists():
        shutil.rmtree(base)
    for d in ["raw/articles", "wiki/sources", "wiki/briefs", "wiki/concepts",
              "wiki/entities", "wiki/domains", "wiki/syntheses", "wiki/outputs"]:
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
    (base / "wiki" / "sources" / "source-a.md").write_text(
        """---
title: "Source A"
type: "source"
---

# Source A

## 关键判断

- [interpretation|high] 端到端架构消除了模块间信息损失。
- [factual|medium] BEV 感知精度达到 95%。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "syntheses" / "synth-b.md").write_text(
        """---
title: "Synth B"
type: "synthesis"
---

# Synth B

## 关键判断

- [interpretation|medium] 模块化架构在特定场景下信息保留更完整。
""",
        encoding="utf-8",
    )
    return base


class TestCollectAllClaims(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "claim-evo-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_collects_claims_from_sources_and_syntheses(self) -> None:
        """collect_all_claims 从 sources 和 syntheses 中提取主张。"""
        claims = claim_evolution.collect_all_claims(self.vault)
        self.assertGreaterEqual(len(claims), 3)

    def test_claim_structure(self) -> None:
        """每条 claim 包含 path、claim_type、confidence、claim_text、page_type。"""
        claims = claim_evolution.collect_all_claims(self.vault)
        claim = claims[0]
        for key in ("path", "claim_type", "confidence", "claim_text", "page_type"):
            self.assertIn(key, claim, f"Claim missing key: {key}")

    def test_page_type_correct(self) -> None:
        """来源页的 page_type 为 source，综合页为 synthesis。"""
        claims = claim_evolution.collect_all_claims(self.vault)
        types = {c["page_type"] for c in claims}
        self.assertIn("source", types)
        self.assertIn("synthesis", types)


class TestCollectClaimsJson(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "claim-json-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_output_has_required_fields(self) -> None:
        """collect_claims_json 输出包含 claims、total_count、by_confidence、by_page_type。"""
        data = claim_evolution.collect_claims_json(self.vault)
        for key in ("claims", "total_count", "by_confidence", "by_page_type"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_total_count_matches_claims(self) -> None:
        """total_count 等于 claims 列表长度。"""
        data = claim_evolution.collect_claims_json(self.vault)
        self.assertEqual(data["total_count"], len(data["claims"]))

    def test_by_confidence_sums_correctly(self) -> None:
        """by_confidence 各级别之和等于 total_count。"""
        data = claim_evolution.collect_claims_json(self.vault)
        total = data["by_confidence"]["high"] + data["by_confidence"]["medium"] + data["by_confidence"]["low"]
        self.assertEqual(total, data["total_count"])

    def test_empty_vault(self) -> None:
        """空 vault 返回空结果。"""
        empty = ROOT / ".tmp-tests" / "claim-empty-vault"
        if empty.exists():
            shutil.rmtree(empty)
        for d in ["raw/articles", "wiki/sources", "wiki/briefs", "wiki/syntheses", "wiki/outputs"]:
            (empty / d).mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))

        data = claim_evolution.collect_claims_json(empty)
        self.assertEqual(data["total_count"], 0)
        self.assertEqual(data["claims"], [])


class TestApplyClaimEvolutionResult(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "claim-apply-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_writes_claim_evolution_page(self) -> None:
        """apply_claim_evolution_result 写入 wiki/claim-evolution.md。"""
        result = {
            "relationships": [
                {
                    "left_text": "主张A",
                    "left_source": "sources/source-a",
                    "left_confidence": "high",
                    "right_text": "主张B",
                    "right_source": "sources/source-b",
                    "right_confidence": "medium",
                    "relationship": "contradict",
                    "reasoning": "逻辑矛盾。",
                }
            ],
            "statistics": {"total_pairs_analyzed": 1, "reinforce": 0, "contradict": 1, "extend": 0},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        claim_evolution.apply_claim_evolution_result(self.vault, result_path)
        page = self.vault / "wiki" / "claim-evolution.md"
        self.assertTrue(page.exists())
        content = page.read_text(encoding="utf-8")
        self.assertIn("矛盾主张", content)
        self.assertIn("sources/source-a", content)

    def test_handles_empty_relationships(self) -> None:
        """空 relationships 不崩溃。"""
        result = {"relationships": [], "statistics": {}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        claim_evolution.apply_claim_evolution_result(self.vault, result_path)
        page = self.vault / "wiki" / "claim-evolution.md"
        self.assertTrue(page.exists())


if __name__ == "__main__":
    unittest.main()
