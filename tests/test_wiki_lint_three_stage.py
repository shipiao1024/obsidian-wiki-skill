from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import wiki_lint  # noqa: E402


def _make_vault(base: Path) -> Path:
    """Create a minimal vault for lint testing."""
    if base.exists():
        shutil.rmtree(base)
    for d in [
        "raw/articles",
        "wiki/sources",
        "wiki/briefs",
        "wiki/concepts",
        "wiki/entities",
        "wiki/domains",
        "wiki/syntheses",
        "wiki/outputs",
    ]:
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / "raw" / "articles" / "article-a.md").write_text("# raw A\n", encoding="utf-8")
    (base / "wiki" / "sources" / "article-a.md").write_text(
        """---
title: "Article A"
type: "source"
quality: "high"
---

# Article A

## 核心摘要

- 摘要 A。

## 关键判断

- [interpretation|high] 端到端架构消除了模块间信息损失。
- [factual|low] 低置信判断示例。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "briefs" / "article-a.md").write_text(
        """---
title: "Article A Brief"
type: "brief"
---

# Article A Brief

一句话：摘要 A。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "concepts" / "candidate-concept.md").write_text(
        """---
title: "Candidate Concept"
type: "concept"
lifecycle: "candidate"
status: "seed"
---

# Candidate Concept

候选概念。
""",
        encoding="utf-8",
    )
    return base


class TestCollectLintData(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "lint-three-stage-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_output_has_required_fields(self) -> None:
        """collect_lint_data 输出包含所有必需顶层字段。"""
        data = wiki_lint.collect_lint_data(self.vault)
        for key in (
            "broken_links",
            "orphan_pages",
            "missing_briefs",
            "missing_sources",
            "empty_folders",
            "low_quality_sources",
            "claim_inventory_issues",
            "status_mismatch",
            "orphan_comparisons",
            "low_confidence_claims",
            "candidate_pages",
            "all_claims",
            "page_sample",
        ):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_all_claims_not_empty(self) -> None:
        """all_claims 包含从 source 页面提取的主张。"""
        data = wiki_lint.collect_lint_data(self.vault)
        self.assertGreaterEqual(len(data["all_claims"]), 2)

    def test_all_claims_structure(self) -> None:
        """每条 claim 包含 path、claim_type、confidence、claim、page_type。"""
        data = wiki_lint.collect_lint_data(self.vault)
        claim = data["all_claims"][0]
        for key in ("path", "claim_type", "confidence", "claim", "page_type"):
            self.assertIn(key, claim, f"Claim missing key: {key}")

    def test_low_confidence_claims_filtered(self) -> None:
        """low_confidence_claims 只包含 confidence=low 的主张。"""
        data = wiki_lint.collect_lint_data(self.vault)
        self.assertGreaterEqual(len(data["low_confidence_claims"]), 1)
        # low_confidence_claims 来自 all_claims 中 confidence=low 的子集
        low_texts = [lc["claim"] for lc in data["low_confidence_claims"]]
        self.assertTrue(any("低置信" in t for t in low_texts))

    def test_candidate_pages_collected(self) -> None:
        """candidate_pages 包含 lifecycle=candidate 的页面。"""
        data = wiki_lint.collect_lint_data(self.vault)
        slugs = [cp["slug"] for cp in data["candidate_pages"]]
        self.assertIn("candidate-concept", slugs)

    def test_no_missing_briefs_when_present(self) -> None:
        """当 brief 存在时，missing_briefs 为空。"""
        data = wiki_lint.collect_lint_data(self.vault)
        self.assertNotIn("article-a", data["missing_briefs"])

    def test_missing_briefs_when_absent(self) -> None:
        """当 brief 缺失时，missing_briefs 包含对应 slug。"""
        (self.vault / "raw" / "articles" / "no-brief.md").write_text("# raw\n", encoding="utf-8")
        data = wiki_lint.collect_lint_data(self.vault)
        self.assertIn("no-brief", data["missing_briefs"])

    def test_output_with_empty_vault(self) -> None:
        """空 vault 不崩溃。"""
        empty = ROOT / ".tmp-tests" / "lint-empty-vault"
        if empty.exists():
            shutil.rmtree(empty)
        for d in ["raw/articles", "wiki/sources", "wiki/briefs", "wiki/concepts",
                   "wiki/entities", "wiki/domains", "wiki/syntheses", "wiki/outputs"]:
            (empty / d).mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))

        data = wiki_lint.collect_lint_data(empty)
        self.assertEqual(data["all_claims"], [])
        self.assertEqual(data["broken_links"], [])


if __name__ == "__main__":
    unittest.main()
