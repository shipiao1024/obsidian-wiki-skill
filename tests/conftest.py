"""Shared fixtures for obsidian-wiki pipeline tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts/ to sys.path so pipeline imports work
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Create a temporary vault with all required directories."""
    from pipeline.pipeline_types import WIKI_DIRS

    for d in WIKI_DIRS:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def sample_article(tmp_path):
    """Return a minimal Article instance for testing with real temp files."""
    from pipeline.pipeline_types import Article

    src_dir = tmp_path / "test-src"
    src_dir.mkdir(parents=True, exist_ok=True)
    md_path = src_dir / "article.md"
    md_path.write_text("# Test Article\n\nContent here.\n", encoding="utf-8")

    return Article(
        title="Test Article Title",
        author="Test Author",
        date="2026-05-01",
        source="https://example.com/test",
        body="## Section One\nThis is the first section with enough content for testing.\n\n## Section Two\nSecond section body text here for testing purposes.\n",
        src_dir=src_dir,
        md_path=md_path,
        quality="high",
    )


@pytest.fixture
def v2_payload():
    """Return a valid v2 compile payload with ordinal confidence labels."""
    return {
        "schema_version": "2.0",
        "result": {
            "document_outputs": {
                "brief": {
                    "one_sentence": "This is a test one-sentence summary.",
                    "key_points": ["Key point 1", "Key point 2"],
                },
                "source": {
                    "core_summary": ["Summary point 1", "Summary point 2"],
                    "knowledge_base_relation": [],
                    "contradictions": [],
                    "reinforcements": [],
                },
            },
            "knowledge_proposals": {
                "domains": [
                    {"name": "AI 工程", "confidence": "Supported", "action": "link_existing",
                     "evidence_type": "fact", "grounding_quote": "This is a test one-sentence summary."},
                ],
                "concepts": [
                    {"name": "Test Concept", "confidence": "Working", "action": "create_candidate",
                     "evidence_type": "inference", "grounding_quote": ""},
                ],
                "entities": [],
            },
            "claim_inventory": [
                {
                    "claim": "This is a high confidence test claim",
                    "claim_type": "interpretation",
                    "evidence_type": "fact",
                    "confidence": "Supported",
                    "grounding_quote": "This is a test one-sentence summary.",
                },
                {
                    "claim": "This is a medium confidence test claim",
                    "claim_type": "observation",
                    "evidence_type": "inference",
                    "confidence": "Working",
                    "grounding_quote": "",
                },
            ],
            "cross_domain_insights": [
                {
                    "mapped_concept": "Test Concept",
                    "target_domain": "认知科学",
                    "bridge_logic": "The concept maps to cognitive load theory",
                    "migration_conclusion": "Can apply cognitive load strategies",
                    "confidence": "Working",
                },
            ],
            "stance_impacts": [],
            "open_questions": ["What is the impact on X?"],
            "comparisons": [],
            "update_proposals": [],
            "review_hints": {"needs_human_review": False},
        },
    }
