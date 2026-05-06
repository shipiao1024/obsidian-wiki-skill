from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from pipeline.ingest_report import collect_ingest_data  # noqa: E402


def _make_vault(base: Path, slug: str = "test-article") -> Path:
    """Create a minimal vault with one source, one question, one stance."""
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
        "wiki/questions",
        "wiki/stances",
    ]:
        (base / d).mkdir(parents=True, exist_ok=True)

    (base / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
    (base / "wiki" / "sources" / f"{slug}.md").write_text(
        """---
title: "Test Article"
type: "source"
quality: "high"
domains: "AI"
---

# Test Article

## 核心摘要

- 这是测试摘要。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "sources" / "other-source.md").write_text(
        """---
title: "Other Source"
type: "source"
quality: "medium"
domains: "AI"
---

# Other Source

## 核心摘要

- 另一篇来源。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "questions" / "q-test.md").write_text(
        """---
title: "Test Question"
type: "question"
status: "open"
origin_source: "sources/test-article"
---

# Test Question

## 问题

- 测试问题内容？
""",
        encoding="utf-8",
    )
    (base / "wiki" / "stances" / "s-test.md").write_text(
        """---
title: "Test Stance"
type: "stance"
impacts: "sources/test-article: reinforce"
---

# Test Stance
""",
        encoding="utf-8",
    )
    return base


class TestCollectIngestData(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "ingest-report-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_output_has_required_fields(self) -> None:
        """collect 输出包含所有必需顶层字段。"""
        data = collect_ingest_data(self.vault, "test-article", "Test Article")
        for key in (
            "new_source",
            "compiled_payload",
            "existing_sources",
            "existing_questions",
            "existing_stances",
            "recent_activity",
        ):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_new_source_metadata(self) -> None:
        """new_source 包含 slug、title、domains、quality。"""
        data = collect_ingest_data(self.vault, "test-article", "Test Article")
        ns = data["new_source"]
        self.assertEqual(ns["slug"], "test-article")
        self.assertEqual(ns["title"], "Test Article")
        self.assertIn("AI", ns["domains"])
        self.assertEqual(ns["quality"], "high")

    def test_excludes_current_slug_from_existing_sources(self) -> None:
        """existing_sources 不包含当前 slug。"""
        data = collect_ingest_data(self.vault, "test-article", "Test Article")
        slugs = [s["slug"] for s in data["existing_sources"]]
        self.assertNotIn("sources/test-article", slugs)
        self.assertIn("sources/other-source", slugs)

    def test_existing_sources_count(self) -> None:
        """existing_sources 包含除当前 slug 外的所有来源。"""
        data = collect_ingest_data(self.vault, "test-article", "Test Article")
        self.assertEqual(len(data["existing_sources"]), 1)

    def test_questions_collected(self) -> None:
        """existing_questions 包含 vault 中的问题页。"""
        data = collect_ingest_data(self.vault, "test-article", "Test Article")
        self.assertEqual(len(data["existing_questions"]), 1)
        self.assertEqual(data["existing_questions"][0]["stem"], "q-test")

    def test_stances_collected(self) -> None:
        """existing_stances 包含 vault 中的立场页。"""
        data = collect_ingest_data(self.vault, "test-article", "Test Article")
        self.assertEqual(len(data["existing_stances"]), 1)
        self.assertEqual(data["existing_stances"][0]["stem"], "s-test")

    def test_compiled_payload_passthrough(self) -> None:
        """compiled_payload 中的数据正确传递到输出。"""
        payload = {
            "result": {
                "knowledge_proposals": {"concepts": [{"name": "X", "action": "create_candidate"}]},
                "open_questions": ["Q1?"],
                "cross_domain_insights": [{"mapped_concept": "A", "target_domain": "B"}],
                "stance_impacts": [],
            }
        }
        data = collect_ingest_data(self.vault, "test-article", "Test Article", compiled_payload=payload)
        self.assertEqual(data["compiled_payload"]["open_questions"], ["Q1?"])
        self.assertEqual(len(data["compiled_payload"]["cross_domain_insights"]), 1)

    def test_output_with_empty_vault(self) -> None:
        """空 vault（无 sources/questions/stances 目录）时不崩溃。"""
        empty = ROOT / ".tmp-tests" / "ingest-report-empty-vault"
        if empty.exists():
            shutil.rmtree(empty)
        for d in ["raw/articles", "wiki/sources", "wiki/briefs"]:
            (empty / d).mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))

        data = collect_ingest_data(empty, "no-such-slug", "No Title")
        self.assertEqual(data["existing_sources"], [])
        self.assertEqual(data["existing_questions"], [])
        self.assertEqual(data["existing_stances"], [])
        self.assertEqual(data["recent_activity"], [])


if __name__ == "__main__":
    unittest.main()
