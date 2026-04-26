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

    def test_build_review_queue_prioritizes_conflicted_delta_outputs(self) -> None:
        vault = ROOT / ".tmp-tests" / "review-queue-conflict-vault"
        if vault.exists():
            shutil.rmtree(vault)
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        for folder in ["outputs", "sources", "briefs", "concepts", "entities", "domains", "syntheses"]:
            (vault / "wiki" / folder).mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs" / "delta-z.md").write_text(
            """---
title: "Delta Z"
type: "delta-compile"
status: "review-needed"
lifecycle: "review-needed"
---

# Delta Proposal

## 关键判断

- [interpretation|medium] 中央计算会加强跨域协同与统一编排。
""",
            encoding="utf-8",
        )
        (vault / "wiki" / "outputs" / "delta-a.md").write_text(
            """---
title: "Delta A"
type: "delta-compile"
status: "review-needed"
lifecycle: "review-needed"
---

# Delta Proposal

## 关键判断

- [interpretation|medium] 这里只是普通待处理草稿。
""",
            encoding="utf-8",
        )
        (vault / "wiki" / "sources" / "source-a.md").write_text(
            """---
title: "Source A"
type: "source"
---

# Source A

## 关键判断

- [interpretation|medium] 中央计算不会加强跨域协同，只会增加分裂。
""",
            encoding="utf-8",
        )

        self.addCleanup(lambda: shutil.rmtree(vault, ignore_errors=True))
        report, _ = review_queue.build_review_queue(vault)

        self.assertEqual(report["pending"][0]["slug"], "delta-z")
        self.assertIn("delta-z", report["conflicted_outputs"])

    def test_build_review_queue_renders_conflicted_section(self) -> None:
        vault = ROOT / ".tmp-tests" / "review-queue-section-vault"
        if vault.exists():
            shutil.rmtree(vault)
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        for folder in ["outputs", "sources", "briefs", "concepts", "entities", "domains", "syntheses"]:
            (vault / "wiki" / folder).mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs" / "delta-z.md").write_text(
            """---
title: "Delta Z"
type: "delta-compile"
status: "review-needed"
lifecycle: "review-needed"
---

# Delta Proposal

## 关键判断

- [interpretation|medium] 中央计算会加强跨域协同与统一编排。
""",
            encoding="utf-8",
        )
        (vault / "wiki" / "sources" / "source-a.md").write_text(
            """---
title: "Source A"
type: "source"
---

# Source A

## 关键判断

- [interpretation|medium] 中央计算不会加强跨域协同，只会增加分裂。
""",
            encoding="utf-8",
        )

        self.addCleanup(lambda: shutil.rmtree(vault, ignore_errors=True))
        _, page = review_queue.build_review_queue(vault)

        self.assertIn("## 冲突候选", page)
        self.assertIn("[[outputs/delta-z]]", page)

    def test_build_review_queue_collects_low_quality_sources(self) -> None:
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
        report, page = review_queue.build_review_queue(vault)

        self.assertEqual(report["low_quality_sources"], ["low-source"])
        self.assertIn("## 低质量来源候选", page)
        self.assertIn("[[sources/low-source]]", page)


if __name__ == "__main__":
    unittest.main()
