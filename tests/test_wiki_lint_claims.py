from __future__ import annotations

import json
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import wiki_lint  # noqa: E402


class WikiLintClaimTests(unittest.TestCase):
    def test_wiki_lint_reports_low_quality_sources(self) -> None:
        vault = ROOT / ".tmp-tests" / "lint-low-quality-vault"
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "briefs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "domains").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "syntheses").mkdir(parents=True, exist_ok=True)
        (vault / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
        (vault / "wiki" / "sources" / "low-source.md").write_text(
            """---
title: "Low Source"
type: "source"
quality: "low"
---

# Low Source

## 核心摘要

- 正文噪声较多。
""",
            encoding="utf-8",
        )

        stream = StringIO()
        argv = sys.argv[:]
        try:
            sys.argv = ["wiki_lint.py", "--vault", str(vault)]
            with redirect_stdout(stream):
                wiki_lint.main()
        finally:
            sys.argv = argv
        report = json.loads(stream.getvalue())

        self.assertIn("low_quality_sources", report)
        self.assertTrue(any("low-source" in item for item in report["low_quality_sources"]))

    def test_wiki_lint_reports_claim_inventory_issues(self) -> None:
        vault = ROOT / ".tmp-tests" / "lint-claims-vault"
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "briefs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "domains").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "syntheses").mkdir(parents=True, exist_ok=True)
        (vault / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
        (vault / "wiki" / "outputs" / "delta-example.md").write_text(
            """---
title: "Delta Example"
type: "delta-compile"
status: "review-needed"
lifecycle: "review-needed"
---

# Delta Proposal

## 关键判断

- [interpretation|low] 这是一个低置信度判断。
- [factual|medium] 这是一个没有证据块支撑的判断。

## 证据

- 只有一条笼统证据
""",
            encoding="utf-8",
        )

        stream = StringIO()
        argv = sys.argv[:]
        try:
            sys.argv = ["wiki_lint.py", "--vault", str(vault)]
            with redirect_stdout(stream):
                wiki_lint.main()
        finally:
            sys.argv = argv
        report = json.loads(stream.getvalue())

        self.assertIn("claim_inventory_issues", report)
        self.assertTrue(any("low confidence" in item for item in report["claim_inventory_issues"]))

    def test_collect_only_returns_all_claims(self) -> None:
        """--collect-only 输出包含 all_claims 字段，含所有页面的主张。"""
        vault = ROOT / ".tmp-tests" / "lint-collect-claims-vault"
        for d in ["raw/articles", "wiki/outputs", "wiki/sources", "wiki/briefs",
                   "wiki/concepts", "wiki/entities", "wiki/domains", "wiki/syntheses"]:
            (vault / d).mkdir(parents=True, exist_ok=True)
        (vault / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
        (vault / "wiki" / "sources" / "source-a.md").write_text(
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
        (vault / "wiki" / "syntheses" / "synth-b.md").write_text(
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

        stream = StringIO()
        argv = sys.argv[:]
        try:
            sys.argv = ["wiki_lint.py", "--vault", str(vault), "--collect-only"]
            with redirect_stdout(stream):
                wiki_lint.main()
        finally:
            sys.argv = argv
        report = json.loads(stream.getvalue())

        self.assertIn("all_claims", report)
        self.assertTrue(len(report["all_claims"]) >= 3, f"Expected >= 3 claims, got {len(report['all_claims'])}")
        # Verify claim structure
        claim = report["all_claims"][0]
        self.assertIn("path", claim)
        self.assertIn("claim_type", claim)
        self.assertIn("confidence", claim)
        self.assertIn("claim", claim)
        self.assertIn("page_type", claim)

    def test_collect_only_returns_low_confidence_claims(self) -> None:
        """--collect-only 输出的 low_confidence_claims 只含 confidence=low 的主张。"""
        vault = ROOT / ".tmp-tests" / "lint-low-conf-vault"
        for d in ["raw/articles", "wiki/outputs", "wiki/sources", "wiki/briefs",
                   "wiki/concepts", "wiki/entities", "wiki/domains", "wiki/syntheses"]:
            (vault / d).mkdir(parents=True, exist_ok=True)
        (vault / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
        (vault / "wiki" / "sources" / "mixed-source.md").write_text(
            """---
title: "Mixed Source"
type: "source"
---

# Mixed Source

## 关键判断

- [interpretation|high] 高置信主张。
- [factual|low] 低置信主张。
- [causal|medium] 中置信主张。
""",
            encoding="utf-8",
        )

        stream = StringIO()
        argv = sys.argv[:]
        try:
            sys.argv = ["wiki_lint.py", "--vault", str(vault), "--collect-only"]
            with redirect_stdout(stream):
                wiki_lint.main()
        finally:
            sys.argv = argv
        report = json.loads(stream.getvalue())

        self.assertIn("low_confidence_claims", report)
        self.assertEqual(len(report["low_confidence_claims"]), 1)
        # low_confidence_claims 来自 collect_lint_data，不含 confidence 字段
        # 但 claim 文本应包含低置信内容
        self.assertIn("低置信", report["low_confidence_claims"][0]["claim"])

    def test_collect_only_includes_candidate_pages(self) -> None:
        """--collect-only 输出包含 candidate_pages 字段。"""
        vault = ROOT / ".tmp-tests" / "lint-candidate-vault"
        for d in ["raw/articles", "wiki/outputs", "wiki/sources", "wiki/briefs",
                   "wiki/concepts", "wiki/entities", "wiki/domains", "wiki/syntheses"]:
            (vault / d).mkdir(parents=True, exist_ok=True)
        (vault / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
        (vault / "wiki" / "concepts" / "candidate-concept.md").write_text(
            """---
title: "Candidate Concept"
type: "concept"
lifecycle: "candidate"
status: "seed"
---

# Candidate Concept

候选概念页面。
""",
            encoding="utf-8",
        )

        stream = StringIO()
        argv = sys.argv[:]
        try:
            sys.argv = ["wiki_lint.py", "--vault", str(vault), "--collect-only"]
            with redirect_stdout(stream):
                wiki_lint.main()
        finally:
            sys.argv = argv
        report = json.loads(stream.getvalue())

        self.assertIn("candidate_pages", report)
        self.assertTrue(any(cp["slug"] == "candidate-concept" for cp in report["candidate_pages"]))


if __name__ == "__main__":
    unittest.main()
