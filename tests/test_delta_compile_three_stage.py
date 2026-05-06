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

import delta_compile  # noqa: E402


def _make_vault(base: Path) -> Path:
    """Create a vault with sources, index, and log for delta compile testing."""
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
domains: "AI"
---

# Source A

## 核心摘要

- 来源 A 的核心摘要。

## 关键判断

- [interpretation|high] 端到端架构消除了模块间信息损失。
""",
        encoding="utf-8",
    )
    (base / "wiki" / "domains" / "AI.md").write_text(
        """---
title: "AI"
type: "domain"
---

# AI 领域

- [[sources/source-a]]
""",
        encoding="utf-8",
    )
    (base / "wiki" / "index.md").write_text(
        """---
title: "知识库索引"
---

# 知识库索引

## sources

- [[sources/source-a]] — Source A (AI)
""",
        encoding="utf-8",
    )
    (base / "wiki" / "log.md").write_text(
        """---
title: "操作日志"
---

# 操作日志

## [2026-05-01 10:00] query: 端到端架构
## [2026-05-01 11:00] ingest: Source A
""",
        encoding="utf-8",
    )
    return base


class TestCollectDeltaData(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "delta-collect-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_output_has_required_fields(self) -> None:
        """collect_delta_data 输出包含所有必需字段。"""
        data = delta_compile.collect_delta_data(self.vault, query="端到端架构")
        for key in ("query_signals", "source_signals", "total_queries", "total_sources"):
            self.assertIn(key, data, f"Missing key: {key}")

    def test_query_signals_populated(self) -> None:
        """传入 query 时，query_signals 非空。"""
        data = delta_compile.collect_delta_data(self.vault, query="端到端架构")
        self.assertGreaterEqual(len(data["query_signals"]), 1)
        self.assertEqual(data["query_signals"][0]["query"], "端到端架构")

    def test_source_signals_populated(self) -> None:
        """传入 source_title 时，source_signals 非空。"""
        data = delta_compile.collect_delta_data(self.vault, source_title="Source A")
        self.assertGreaterEqual(len(data["source_signals"]), 1)
        self.assertEqual(data["source_signals"][0]["title"], "Source A")

    def test_source_signal_has_domains(self) -> None:
        """source_signals 中的来源包含 domains 字段。"""
        data = delta_compile.collect_delta_data(self.vault, source_title="Source A")
        src = data["source_signals"][0]
        self.assertIn("domains", src)

    def test_auto_mode_uses_log(self) -> None:
        """不传 query/source_title 时，从 log.md 自动提取。"""
        data = delta_compile.collect_delta_data(self.vault)
        # log.md 中有 query 和 ingest 记录
        self.assertIsInstance(data["query_signals"], list)
        self.assertIsInstance(data["source_signals"], list)

    def test_empty_vault_no_crash(self) -> None:
        """空 vault 传入显式 query 时不崩溃。"""
        empty = ROOT / ".tmp-tests" / "delta-empty-vault"
        if empty.exists():
            shutil.rmtree(empty)
        for d in ["raw/articles", "wiki/sources", "wiki/briefs", "wiki/domains"]:
            (empty / d).mkdir(parents=True, exist_ok=True)
        (empty / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
        (empty / "wiki" / "log.md").write_text("# Log\n", encoding="utf-8")
        self.addCleanup(lambda: shutil.rmtree(empty, ignore_errors=True))

        data = delta_compile.collect_delta_data(empty, query="test")
        self.assertEqual(data["total_queries"], 1)


class TestApplyDeltaResult(unittest.TestCase):
    def setUp(self) -> None:
        self.vault = _make_vault(ROOT / ".tmp-tests" / "delta-apply-vault")
        self.addCleanup(lambda: shutil.rmtree(self.vault, ignore_errors=True))

    def test_writes_delta_page(self) -> None:
        """apply_delta_result 写入 delta-compile 页面。"""
        result = {
            "drafts": [
                {
                    "type": "query",
                    "question": "端到端架构的优劣？",
                    "conclusion": "端到端架构有优有劣。",
                    "key_points": ["优势1", "劣势1"],
                    "evidence_refs": ["sources/source-a"],
                    "reasoning": "基于来源 A 的分析。",
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        generated = delta_compile.apply_delta_result(self.vault, result_path)
        self.assertGreaterEqual(len(generated), 1)

        # generated 包含完整文件路径（含 .md），直接验证存在
        for path_str in generated:
            out_path = Path(path_str)
            self.assertTrue(out_path.exists(), f"Expected {out_path} to exist")

    def test_handles_empty_drafts(self) -> None:
        """空 drafts 不崩溃。"""
        result = {"drafts": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
            result_path = Path(f.name)
        self.addCleanup(result_path.unlink)

        generated = delta_compile.apply_delta_result(self.vault, result_path)
        self.assertEqual(generated, [])


if __name__ == "__main__":
    unittest.main()
