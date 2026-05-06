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

import review_queue  # noqa: E402


def _make_vault(base: Path) -> Path:
    """Create a vault with pending outputs and candidate pages."""
    if base.exists():
        shutil.rmtree(base)
    for d in ["raw/articles", "wiki/sources", "wiki/briefs", "wiki/concepts",
              "wiki/entities", "wiki/domains", "wiki/syntheses", "wiki/outputs"]:
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
    (base / "wiki" / "outputs" / "temp-output.md").write_text(
        """---
title: "Temp Output"
type: "query"
status: "accepted"
lifecycle: "temporary"
date: "2026-05-01"
---

# Temp Output

引用 [[sources/source-a]] 的内容。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "outputs" / "delta-draft.md").write_text(
        """---
title: "Delta Draft"
type: "delta-compile"
status: "review-needed"
lifecycle: "review-needed"
date: "2026-05-01"
---

# Delta Draft

## 关键判断

- [interpretation|medium] 本文认为中央计算会加强跨域协同。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "outputs" / "absorbed-output.md").write_text(
        """---
title: "Absorbed Output"
type: "query"
lifecycle: "absorbed"
---

# Absorbed Output
""",
        encoding="utf-8",
    )
    (base / "wiki" / "sources" / "source-a.md").write_text(
        """---
title: "Source A"
type: "source"
quality: "high"
---

# Source A

## 核心摘要

- 摘要。
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
""",
        encoding="utf-8",
    )
    return base


class TestCollectReviewData(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "review-collect-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_output_has_required_fields(self) -> None:
        """collect_review_data 输出包含所有必需字段。"""
        data = review_queue.collect_review_data(self.vault)
        for key in ("pending_outputs", "candidate_pages", "low_confidence_claims",
                     "absorbed_count", "archived_count"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_pending_outputs_excludes_absorbed(self) -> None:
        """pending_outputs 只包含 lifecycle=temporary 或 review-needed 的项。"""
        data = review_queue.collect_review_data(self.vault)
        paths = [p["path"] for p in data["pending_outputs"]]
        self.assertIn("outputs/temp-output", paths)
        self.assertIn("outputs/delta-draft", paths)
        self.assertNotIn("outputs/absorbed-output", paths)

    def test_absorbed_count(self) -> None:
        """absorbed_count 统计 lifecycle=absorbed 的输出。"""
        data = review_queue.collect_review_data(self.vault)
        self.assertEqual(data["absorbed_count"], 1)

    def test_candidate_pages_collected(self) -> None:
        """candidate_pages 包含 lifecycle=candidate 的页面。"""
        data = review_queue.collect_review_data(self.vault)
        slugs = [cp["path"] for cp in data["candidate_pages"]]
        self.assertIn("concepts/candidate-concept", slugs)

    def test_pending_output_has_summary(self) -> None:
        """pending_outputs 每项包含 summary 字段。"""
        data = review_queue.collect_review_data(self.vault)
        for item in data["pending_outputs"]:
            self.assertIn("summary", item)

    def test_empty_vault(self) -> None:
        """空 vault 不崩溃。"""
        empty = ROOT / ".tmp-tests" / "review-empty-vault"
        if empty.exists():
            shutil.rmtree(empty)
        for d in ["raw/articles", "wiki/sources", "wiki/briefs", "wiki/concepts",
                   "wiki/entities", "wiki/domains", "wiki/syntheses", "wiki/outputs"]:
            (empty / d).mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))

        data = review_queue.collect_review_data(empty)
        self.assertEqual(data["pending_outputs"], [])
        self.assertEqual(data["absorbed_count"], 0)


class TestApplyReviewResult(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "review-apply-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_archive_action_changes_lifecycle(self) -> None:
        """archive 操作将 lifecycle 改为 archived。"""
        result = {
            "prioritized_items": [
                {"path": "outputs/temp-output", "action": "archive", "reason": "被覆盖"}
            ],
            "upgrade_recommendations": [],
            "summary": {},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        ret = review_queue.apply_review_result(self.vault, result_path)
        self.assertIn("actions", ret)
        self.assertTrue(any("archive" in a for a in ret["actions"]))

        # Verify file was modified
        content = (self.vault / "wiki" / "outputs" / "temp-output.md").read_text(encoding="utf-8")
        self.assertIn("archived", content)

    def test_approve_action_logged(self) -> None:
        """approve 操作记录到 actions 中。"""
        result = {
            "prioritized_items": [
                {"path": "outputs/temp-output", "action": "approve", "reason": "有价值"}
            ],
            "upgrade_recommendations": [],
            "summary": {"high_priority": 1},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        ret = review_queue.apply_review_result(self.vault, result_path)
        self.assertTrue(any("approve" in a for a in ret["actions"]))

    def test_upgrade_action_changes_lifecycle(self) -> None:
        """upgrade 操作将 candidate lifecycle 改为 official。"""
        result = {
            "prioritized_items": [],
            "upgrade_recommendations": [
                {"path": "concepts/candidate-concept", "action": "upgrade", "to_lifecycle": "official"}
            ],
            "summary": {},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        ret = review_queue.apply_review_result(self.vault, result_path)
        self.assertTrue(any("upgrade" in a for a in ret["actions"]))

        content = (self.vault / "wiki" / "concepts" / "candidate-concept.md").read_text(encoding="utf-8")
        self.assertIn("official", content)

    def test_skip_action_no_change(self) -> None:
        """skip 操作不修改文件。"""
        original = (self.vault / "wiki" / "outputs" / "temp-output.md").read_text(encoding="utf-8")
        result = {
            "prioritized_items": [
                {"path": "outputs/temp-output", "action": "skip", "reason": "不重要"}
            ],
            "upgrade_recommendations": [],
            "summary": {},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        review_queue.apply_review_result(self.vault, result_path)
        after = (self.vault / "wiki" / "outputs" / "temp-output.md").read_text(encoding="utf-8")
        self.assertEqual(original, after)


if __name__ == "__main__":
    unittest.main()
