from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import review_queue  # noqa: E402


class ReviewQueueClaimTests(unittest.TestCase):
    def test_summary_line_prefers_claims_section_for_delta_compile(self) -> None:
        body = """
## 关键判断

- [interpretation|medium] 本文认为中央计算会加强跨域协同。

## 建议修改

- 新增判断
"""
        summary = review_queue.summary_line({"type": "delta-compile"}, body)
        self.assertIn("中央计算会加强跨域协同", summary)

    def test_build_review_queue_page_collects_low_quality_sources(self) -> None:
        """低质量来源在页面中渲染为低质量来源候选段。"""
        vault = ROOT / ".tmp-tests" / "review-queue-quality-vault"
        if vault.exists():
            shutil.rmtree(vault)
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        for folder in ["outputs", "sources", "briefs", "concepts", "entities", "domains", "syntheses"]:
            (vault / "wiki" / folder).mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "sources" / "low-source.md").write_text(
            """---
title: "Low Source"
type: "source"
quality: "low"
---

# Low Source

## 核心摘要

- 这是一条低质量来源。
""",
            encoding="utf-8",
        )

        self.addCleanup(lambda: shutil.rmtree(vault, ignore_errors=True))
        page = review_queue.build_review_queue_page(vault)

        self.assertIn("## 低质量来源候选", page)
        self.assertIn("[[sources/low-source]]", page)

    def test_build_review_queue_page_renders_pending_outputs(self) -> None:
        """待处理 output 在页面中渲染为待处理段。"""
        vault = ROOT / ".tmp-tests" / "review-queue-pending-vault"
        if vault.exists():
            shutil.rmtree(vault)
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        for folder in ["outputs", "sources", "briefs", "concepts", "entities", "domains", "syntheses"]:
            (vault / "wiki" / folder).mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs" / "temp-output.md").write_text(
            """---
title: "Temp Output"
type: "query"
status: "accepted"
lifecycle: "temporary"
---

# Temp Output

引用 [[sources/source-a]] 的内容。
""",
            encoding="utf-8",
        )

        self.addCleanup(lambda: shutil.rmtree(vault, ignore_errors=True))
        page = review_queue.build_review_queue_page(vault)

        self.assertIn("## 待处理", page)
        self.assertIn("[[outputs/temp-output]]", page)

    def test_build_review_queue_page_excludes_absorbed(self) -> None:
        """已吸收的 output 不出现在待处理段。"""
        vault = ROOT / ".tmp-tests" / "review-queue-absorbed-vault"
        if vault.exists():
            shutil.rmtree(vault)
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        for folder in ["outputs", "sources", "briefs", "concepts", "entities", "domains", "syntheses"]:
            (vault / "wiki" / folder).mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs" / "absorbed-output.md").write_text(
            """---
title: "Absorbed"
type: "query"
lifecycle: "absorbed"
---

# Absorbed
""",
            encoding="utf-8",
        )

        self.addCleanup(lambda: shutil.rmtree(vault, ignore_errors=True))
        page = review_queue.build_review_queue_page(vault)

        self.assertNotIn("[[outputs/absorbed-output]]", page)
        self.assertIn("已吸收：1", page)


if __name__ == "__main__":
    unittest.main()
