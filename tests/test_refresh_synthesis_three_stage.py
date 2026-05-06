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

import refresh_synthesis  # noqa: E402


def _make_vault(base: Path) -> Path:
    """Create a vault with a synthesis page linked to sources."""
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
quality: "high"
one_sentence: "来源 A 的一句话结论。"
---

# Source A

## 核心摘要

- 来源 A 的核心摘要。

## 关键判断

- [interpretation|high] 端到端架构消除了模块间信息损失。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "sources" / "source-b.md").write_text(
        """---
title: "Source B"
type: "source"
quality: "medium"
---

# Source B

## 核心摘要

- 来源 B 的核心摘要。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "syntheses" / "AI--综合分析.md").write_text(
        """---
title: "AI 综合分析"
type: "synthesis"
domain: "AI"
---

# AI 综合分析

## 当前结论

- AI 领域正在快速发展。

## 相关来源

- [[sources/source-a]]
- [[sources/source-b]]
""",
        encoding="utf-8",
    )
    return base


class TestCollectSynthesisData(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "synth-collect-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_output_has_required_fields(self) -> None:
        """collect_synthesis_data 输出包含所有必需字段。"""
        synth_path = self.vault / "wiki" / "syntheses" / "AI--综合分析.md"
        data = refresh_synthesis.collect_synthesis_data(self.vault, synth_path)
        for key in ("synthesis_path", "domain", "source_count", "linked_sources", "existing_synthesis"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_linked_sources_collected(self) -> None:
        """linked_sources 包含综合页链接的所有来源。"""
        synth_path = self.vault / "wiki" / "syntheses" / "AI--综合分析.md"
        data = refresh_synthesis.collect_synthesis_data(self.vault, synth_path)
        self.assertEqual(data["source_count"], 2)
        slugs = [s["slug"] for s in data["linked_sources"]]
        self.assertIn("sources/source-a", slugs)
        self.assertIn("sources/source-b", slugs)

    def test_source_has_key_claims(self) -> None:
        """linked_sources 中的来源包含 key_claims。"""
        synth_path = self.vault / "wiki" / "syntheses" / "AI--综合分析.md"
        data = refresh_synthesis.collect_synthesis_data(self.vault, synth_path)
        source_a = next(s for s in data["linked_sources"] if s["slug"] == "sources/source-a")
        self.assertGreaterEqual(len(source_a["key_claims"]), 1)

    def test_existing_synthesis_has_conclusion(self) -> None:
        """existing_synthesis 包含当前结论。"""
        synth_path = self.vault / "wiki" / "syntheses" / "AI--综合分析.md"
        data = refresh_synthesis.collect_synthesis_data(self.vault, synth_path)
        self.assertIn("AI 领域正在快速发展", data["existing_synthesis"]["current_conclusion"])

    def test_domain_extracted(self) -> None:
        """domain 从综合页 frontmatter 中提取。"""
        synth_path = self.vault / "wiki" / "syntheses" / "AI--综合分析.md"
        data = refresh_synthesis.collect_synthesis_data(self.vault, synth_path)
        self.assertEqual(data["domain"], "AI")


class TestApplySynthesisResult(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "synth-apply-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_writes_synthesis_page(self) -> None:
        """apply_synthesis_result 写入综合页。"""
        result = {
            "domain": "AI",
            "current_conclusion": "AI 综合结论已更新。",
            "core_claims": [
                {"text": "核心判断1", "confidence": "high", "evidence_type": "consensus",
                 "supporting_sources": ["sources/source-a"]}
            ],
            "divergences": [],
            "pending_verification": [],
            "knowledge_gaps": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        synth_path = self.vault / "wiki" / "syntheses" / "AI--综合分析.md"
        refresh_synthesis.apply_synthesis_result(self.vault, result_path, synth_path)

        content = synth_path.read_text(encoding="utf-8")
        self.assertIn("AI 综合结论已更新", content)
        self.assertIn("核心判断1", content)

    def test_handles_empty_result(self) -> None:
        """空结果不崩溃。"""
        result = {
            "domain": "AI",
            "current_conclusion": "待补充。",
            "core_claims": [],
            "divergences": [],
            "pending_verification": [],
            "knowledge_gaps": [],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        synth_path = self.vault / "wiki" / "syntheses" / "AI--综合分析.md"
        refresh_synthesis.apply_synthesis_result(self.vault, result_path, synth_path)
        self.assertTrue(synth_path.exists())


if __name__ == "__main__":
    unittest.main()
