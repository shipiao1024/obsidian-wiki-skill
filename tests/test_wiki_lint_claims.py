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

    def test_wiki_lint_reports_claim_conflicts(self) -> None:
        vault = ROOT / ".tmp-tests" / "lint-claims-conflict-vault"
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "briefs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "domains").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "syntheses").mkdir(parents=True, exist_ok=True)
        (vault / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
        (vault / "wiki" / "outputs" / "delta-a.md").write_text(
            """---
title: "Delta A"
type: "delta-compile"
status: "review-needed"
lifecycle: "review-needed"
---

# Delta Proposal

## 关键判断

- [interpretation|medium] 中央计算会加强跨域协同与统一编排。

## 证据

- 证据 A
""",
            encoding="utf-8",
        )
        (vault / "wiki" / "outputs" / "delta-b.md").write_text(
            """---
title: "Delta B"
type: "delta-compile"
status: "review-needed"
lifecycle: "review-needed"
---

# Delta Proposal

## 关键判断

- [interpretation|medium] 中央计算不会加强跨域协同，只会增加分裂。

## 证据

- 证据 B
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

        self.assertIn("claim_conflicts", report)
        self.assertTrue(any("跨域协同" in item for item in report["claim_conflicts"]))

    def test_wiki_lint_reports_claim_conflicts_between_source_and_synthesis(self) -> None:
        vault = ROOT / ".tmp-tests" / "lint-claims-knowledge-vault"
        (vault / "raw" / "articles").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "outputs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "sources").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "briefs").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "domains").mkdir(parents=True, exist_ok=True)
        (vault / "wiki" / "syntheses").mkdir(parents=True, exist_ok=True)
        (vault / "raw" / "articles" / "example.md").write_text("# raw\n", encoding="utf-8")
        (vault / "wiki" / "sources" / "source-a.md").write_text(
            """---
title: "Source A"
type: "source"
---

# Source A

## 关键判断

- [interpretation|medium] 中央计算会加强跨域协同与统一编排。
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

- [interpretation|medium] 中央计算不会加强跨域协同，只会增加分裂。
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

        self.assertTrue(any("source-a" in item and "synth-b" in item for item in report["claim_conflicts"]))


if __name__ == "__main__":
    unittest.main()
