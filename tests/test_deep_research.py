"""Tests for deep_research pipeline module."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.deep_research import (
    init_research_project,
    collect_vault_evidence,
    record_scenarios,
    record_premortem,
    finalize_report,
    update_closure,
)
from pipeline.dependency_ledger import read_ledger, add_fact_node


def _make_vault(tmp: Path) -> Path:
    vault = tmp / "vault"
    for d in ("wiki/sources", "wiki/briefs", "wiki/research",
              "wiki/questions", "wiki/stances", "wiki/syntheses", "raw/articles"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    return vault


def _write_source(vault: Path, slug: str, title: str, body: str) -> Path:
    path = vault / "wiki" / "sources" / f"{slug}.md"
    path.write_text(
        f"---\ntitle: \"{title}\"\ntype: \"source\"\nquality: \"high\"\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_init_research_project(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [
        {"claim": "端到端更适合量产", "type": "causal", "confidence": 25,
         "confirm_queries": ["端到端量产优势"], "contradict_queries": ["端到端量产困难"],
         "confirm_evidence": "量产数据", "contradict_evidence": "量产失败案例"},
    ]
    result = init_research_project(vault, "自动驾驶", hypotheses)
    assert "ledger_path" in result
    assert "context_path" in result
    assert Path(result["ledger_path"]).exists()
    assert Path(result["context_path"]).exists()


def test_collect_vault_evidence(tmp_path):
    vault = _make_vault(tmp_path)
    _write_source(vault, "src1", "端到端量产优势",
                  "## 核心摘要\n端到端方案在量产中表现出色\n\n## 与现有知识库的关系\n巩固现有观点")
    _write_source(vault, "src2", "端到端量产困难",
                  "## 核心摘要\n端到端方案在极端天气下不可靠\n\n## 与现有知识库的关系\n与已有知识冲突")

    evidence = collect_vault_evidence(vault, "自动驾驶", ["端到端量产"])
    assert "端到端量产" in evidence
    # Should have both confirming and contradicting evidence
    claim_evidence = evidence["端到端量产"]
    assert len(claim_evidence["confirming"]) + len(claim_evidence["contradicting"]) > 0


def test_record_scenarios(tmp_path):
    vault = _make_vault(tmp_path)
    scenarios = [
        {
            "conclusion": "端到端可以量产",
            "base_case": "Holds",
            "stress_a": "Partial",
            "stress_b": "Fails",
            "compound": "Fails",
            "boundary_condition": "仅限 L2+ 场景",
        }
    ]
    path = record_scenarios(vault, "自动驾驶", scenarios)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "端到端可以量产" in text
    assert "Holds" in text
    assert "仅限 L2+ 场景" in text


def test_record_premortem(tmp_path):
    vault = _make_vault(tmp_path)
    premortem = [
        {
            "scenario": "量产延迟",
            "mechanism": "供应链问题",
            "ledger_root": "H-01",
            "resolution": "建立备用供应商",
        }
    ]
    path = record_premortem(vault, "自动驾驶", premortem)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "量产延迟" in text
    assert "H-01" in text


def test_finalize_report(tmp_path):
    vault = _make_vault(tmp_path)
    # Init project first so ledger exists
    hypotheses = [{"claim": "H1", "type": "causal", "confidence": 25}]
    init_research_project(vault, "自动驾驶", hypotheses)
    add_fact_node(vault, "自动驾驶", "事实1", "sources/abc", tier=1)

    report_md = "# 自动驾驶 深度研究报告\n\n## Why\n根本问题..."
    result = finalize_report(vault, "自动驾驶", report_md)
    path = Path(result["report_path"])
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "research-report" in text
    assert "根本问题" in text
    assert "report_path" in result


def test_update_closure(tmp_path):
    vault = _make_vault(tmp_path)
    # Create minimal log and hot files
    (vault / "wiki" / "log.md").write_text("", encoding="utf-8")
    (vault / "wiki" / "hot.md").write_text("- 2026-01-01: 旧条目\n", encoding="utf-8")

    hypotheses = [{"claim": "H1", "type": "causal", "confidence": 25}]
    init_research_project(vault, "自动驾驶", hypotheses)

    result = update_closure(vault, "自动驾驶")
    assert "resolved_questions" in result
    assert "stance_updates" in result

    # Check log was updated
    log_text = (vault / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "深度研究完成" in log_text

    # Check hot was updated
    hot_text = (vault / "wiki" / "hot.md").read_text(encoding="utf-8")
    assert "自动驾驶" in hot_text


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
