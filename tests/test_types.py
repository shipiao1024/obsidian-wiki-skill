"""Tests for pipeline/pipeline_types.py — core data types and constants."""

from __future__ import annotations

import pytest

from pipeline.pipeline_types import (
    WIKI_DIRS,
    VALID_PAGE_STATUS,
    STATUS_UPGRADE_THRESHOLDS,
    Article,
)


class TestTypes:
    """T4: Core type definitions and constants."""

    def test_wiki_dirs_covers_research(self):
        """P0-1 fix: wiki/research should be in WIKI_DIRS."""
        assert "wiki/research" in WIKI_DIRS

    def test_wiki_dirs_covers_all_essential(self):
        essential = [
            "raw/articles", "raw/assets", "raw/transcripts",
            "wiki/sources", "wiki/briefs", "wiki/concepts",
            "wiki/entities", "wiki/domains", "wiki/syntheses",
            "wiki/questions", "wiki/stances", "wiki/comparisons",
            "wiki/outputs",
        ]
        for d in essential:
            assert d in WIKI_DIRS, f"Missing essential dir: {d}"

    def test_valid_page_status_includes_candidate(self):
        assert "candidate" in VALID_PAGE_STATUS

    def test_valid_page_status_includes_all_levels(self):
        for level in ("candidate", "seed", "developing", "mature", "evergreen"):
            assert level in VALID_PAGE_STATUS

    def test_status_upgrade_thresholds_keys_subset_of_valid_status(self):
        for key in STATUS_UPGRADE_THRESHOLDS:
            assert key in VALID_PAGE_STATUS or key == "candidate"

    def test_status_upgrade_thresholds_values_are_positive(self):
        """All threshold values should be positive integers."""
        for key, val in STATUS_UPGRADE_THRESHOLDS.items():
            assert isinstance(val, int)
            assert val > 0

    def test_article_dataclass_defaults(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        md_path = src_dir / "article.md"
        md_path.write_text("content", encoding="utf-8")
        article = Article(
            title="T", author="A", date="2026-01-01",
            source="http://x.com", body="b",
            src_dir=src_dir, md_path=md_path,
        )
        assert article.quality == ""
        assert article.confidence == ""
        assert article.claim_inventory == []
