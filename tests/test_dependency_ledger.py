"""Tests for dependency_ledger module."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.dependency_ledger import (
    init_ledger_page,
    read_ledger,
    add_fact_node,
    update_hypothesis_confidence,
    check_evidence_sufficiency,
    scan_active_research,
    surgical_rollback,
    confidence_label,
    research_slug,
    ordinal_min,
)


def _make_vault(tmp: Path) -> Path:
    vault = tmp / "vault"
    for d in ("wiki/sources", "wiki/briefs", "wiki/research", "raw/articles"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    return vault


def test_confidence_label_ordinals():
    """Ordinal labels pass through unchanged."""
    assert confidence_label("Seeded") == "Seeded"
    assert confidence_label("Preliminary") == "Preliminary"
    assert confidence_label("Working") == "Working"
    assert confidence_label("Supported") == "Supported"
    assert confidence_label("Stable") == "Stable"


def test_confidence_label_legacy_ints():
    """Legacy percentage ints are mapped to ordinal labels."""
    assert confidence_label(0) == "Seeded"
    assert confidence_label(15) == "Seeded"
    assert confidence_label(25) == "Preliminary"
    assert confidence_label(45) == "Working"
    assert confidence_label(65) == "Supported"
    assert confidence_label(85) == "Stable"


def test_confidence_label_invalid():
    """Invalid input defaults to Preliminary."""
    assert confidence_label("invalid") == "Preliminary"


def test_ordinal_min():
    """ordinal_min returns the lower of two ordinal levels."""
    assert ordinal_min("Seeded", "Stable") == "Seeded"
    assert ordinal_min("Supported", "Working") == "Working"
    assert ordinal_min("Preliminary", "Preliminary") == "Preliminary"


def test_research_slug():
    assert research_slug("端到端自动驾驶") == "端到端自动驾驶"
    assert research_slug("a/b:c") == "a_b_c"


def test_init_ledger_page(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [
        {"claim": "端到端方案更适合量产", "type": "causal", "confidence": "Preliminary",
         "confirm_queries": ["端到端量产优势"], "contradict_queries": ["端到端量产困难"]},
    ]
    path = init_ledger_page(vault, "端到端自动驾驶", hypotheses)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "端到端方案更适合量产" in text
    assert "H-01" in text
    assert "Preliminary" in text


def test_init_ledger_page_legacy_int_confidence(tmp_path):
    """Legacy int confidence values are converted to ordinal labels."""
    vault = _make_vault(tmp_path)
    hypotheses = [
        {"claim": "假说A", "type": "causal", "confidence": 25},
    ]
    path = init_ledger_page(vault, "测试主题", hypotheses)
    text = path.read_text(encoding="utf-8")
    assert "Preliminary" in text  # 25 maps to Preliminary


def test_read_ledger(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [
        {"claim": "假说A", "type": "causal", "confidence": "Preliminary",
         "confirm_queries": ["q1"], "contradict_queries": ["q2"]},
    ]
    init_ledger_page(vault, "测试主题", hypotheses)
    ledger = read_ledger(vault, "测试主题")
    assert "H-01" in ledger["nodes"]
    assert ledger["nodes"]["H-01"]["claim"] == "假说A"


def test_add_fact_node(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [{"claim": "H1", "type": "causal", "confidence": "Preliminary"}]
    init_ledger_page(vault, "测试主题", hypotheses)

    nid = add_fact_node(vault, "测试主题", "Tier 1 事实确认", "sources/abc", tier=1)
    assert nid == "F-01"

    ledger = read_ledger(vault, "测试主题")
    assert "F-01" in ledger["nodes"]
    assert "Tier 1 事实确认" in ledger["nodes"]["F-01"]["claim"]

    # Add second fact
    nid2 = add_fact_node(vault, "测试主题", "第二个事实", "sources/def", tier=2)
    assert nid2 == "F-02"


def test_update_hypothesis_confidence(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [{"claim": "H1", "type": "causal", "confidence": "Preliminary"}]
    init_ledger_page(vault, "测试主题", hypotheses)

    update_hypothesis_confidence(vault, "测试主题", "H-01", "Working", "新证据确认")
    ledger = read_ledger(vault, "测试主题")
    assert ledger["nodes"]["H-01"]["confidence"] == "Working"


def test_update_hypothesis_confidence_legacy_int(tmp_path):
    """Legacy int confidence is converted to ordinal on update."""
    vault = _make_vault(tmp_path)
    hypotheses = [{"claim": "H1", "type": "causal", "confidence": "Preliminary"}]
    init_ledger_page(vault, "测试主题", hypotheses)

    update_hypothesis_confidence(vault, "测试主题", "H-01", 55)
    ledger = read_ledger(vault, "测试主题")
    assert ledger["nodes"]["H-01"]["confidence"] == "Working"  # 55 maps to Working


def test_check_evidence_sufficiency_blocks(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [{"claim": "H1", "type": "causal", "confidence": "Seeded"}]
    init_ledger_page(vault, "测试主题", hypotheses)

    result = check_evidence_sufficiency(vault, "测试主题")
    assert not result["passed"]
    assert any("Seeded" in v for v in result["violations"])


def test_scan_active_research(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [{"claim": "H1", "type": "causal", "confidence": "Preliminary"}]
    init_ledger_page(vault, "主题A", hypotheses)

    projects = scan_active_research(vault)
    assert len(projects) == 1
    assert projects[0]["topic"] == "主题A"
    assert projects[0]["status"] == "active"


def test_surgical_rollback(tmp_path):
    vault = _make_vault(tmp_path)
    hypotheses = [{"claim": "H1", "type": "causal", "confidence": "Supported"}]
    init_ledger_page(vault, "测试主题", hypotheses)

    affected = surgical_rollback(vault, "测试主题", "H-01", "核心证据被推翻")
    assert "H-01" in affected

    ledger = read_ledger(vault, "测试主题")
    assert ledger["nodes"]["H-01"]["confidence"] == "Seeded"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
