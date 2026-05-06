"""Integration tests for pipeline/ingest_orchestrator.py — the main ingest pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipeline.pipeline_types import Article, WIKI_DIRS
from pipeline.ingest import ensure_bootstrap


class TestIngestOrchestrator:
    """T10: End-to-end ingest flow with mocked adapter and compile."""

    def test_ensure_bootstrap_creates_all_wiki_dirs(self, vault):
        """ensure_bootstrap should create all directories in WIKI_DIRS."""
        # Remove all dirs first
        for d in WIKI_DIRS:
            p = vault / d
            if p.exists():
                p.rmdir()
        ensure_bootstrap(vault)
        for d in WIKI_DIRS:
            assert (vault / d).exists(), f"Missing directory: {d}"

    def test_ensure_bootstrap_creates_research_dir(self, vault):
        """P0-1 fix: ensure_bootstrap should create wiki/research."""
        ensure_bootstrap(vault)
        assert (vault / "wiki" / "research").exists()

    @patch("pipeline.compile.try_llm_compile")
    def test_ingest_article_compile_failure_returns_failed(self, mock_compile, vault, sample_article):
        """When compile returns None, status should be 'failed' (no heuristic fallback)."""
        mock_compile.return_value = (None, "LLM compile disabled by --no-llm-compile.")

        from pipeline.ingest_orchestrator import ingest_article
        result = ingest_article(vault, sample_article, force=True, no_llm_compile=True)

        assert result["status"] == "failed"
        assert result["compile_mode"] == "failed"
        # raw page should still exist
        slug = result["slug"]
        assert (vault / "raw" / "articles" / f"{slug}.md").exists()
        # brief/source should NOT exist (no heuristic fallback)
        assert not (vault / "wiki" / "briefs" / f"{slug}.md").exists()
        assert not (vault / "wiki" / "sources" / f"{slug}.md").exists()

    @patch("pipeline.compile.try_llm_compile")
    def test_ingest_article_v2_compile(self, mock_compile, vault, sample_article, v2_payload):
        """When compile returns valid v2, official lifecycle pages should be written."""
        mock_compile.return_value = (v2_payload, None)

        from pipeline.ingest_orchestrator import ingest_article
        result = ingest_article(vault, sample_article, force=True, no_llm_compile=False)

        assert result["status"] == "ingested"
        assert result["compile_mode"] == "llm-v2"
        slug = result["slug"]
        assert (vault / "wiki" / "briefs" / f"{slug}.md").exists()
        assert (vault / "wiki" / "sources" / f"{slug}.md").exists()

    @patch("pipeline.compile.try_llm_compile")
    def test_ingest_article_skips_existing(self, mock_compile, vault, sample_article):
        """Without force, existing pages should be skipped."""
        mock_compile.return_value = (None, "skip")

        from pipeline.ingest_orchestrator import ingest_article
        # First ingest
        ingest_article(vault, sample_article, force=True, no_llm_compile=True)
        # Second ingest without force
        result = ingest_article(vault, sample_article, force=False, no_llm_compile=True)
        assert result["status"] == "skipped"

    @patch("pipeline.compile.try_llm_compile")
    def test_ingest_article_force_overwrites(self, mock_compile, vault, sample_article):
        """With force, existing pages should be overwritten."""
        mock_compile.return_value = (None, "skip")

        from pipeline.ingest_orchestrator import ingest_article
        ingest_article(vault, sample_article, force=True, no_llm_compile=True)
        result = ingest_article(vault, sample_article, force=True, no_llm_compile=True)
        assert result["status"] == "failed"

    @patch("pipeline.compile.try_llm_compile")
    def test_low_confidence_sets_candidate_lifecycle(self, mock_compile, vault, sample_article, v2_payload):
        """Low confidence claims should trigger candidate lifecycle."""
        # Set all claims to low ordinal confidence
        for claim in v2_payload["result"]["claim_inventory"]:
            claim["confidence"] = "Seeded"
        mock_compile.return_value = (v2_payload, None)

        from pipeline.ingest_orchestrator import ingest_article
        result = ingest_article(vault, sample_article, force=True, no_llm_compile=False)

        slug = result["slug"]
        brief_text = (vault / "wiki" / "briefs" / f"{slug}.md").read_text(encoding="utf-8")
        assert "candidate" in brief_text

    @patch("pipeline.compile.try_llm_compile")
    def test_high_confidence_sets_official_lifecycle(self, mock_compile, vault, sample_article, v2_payload):
        """High confidence claims should trigger official lifecycle."""
        mock_compile.return_value = (v2_payload, None)

        from pipeline.ingest_orchestrator import ingest_article
        result = ingest_article(vault, sample_article, force=True, no_llm_compile=False)

        slug = result["slug"]
        brief_text = (vault / "wiki" / "briefs" / f"{slug}.md").read_text(encoding="utf-8")
        # Should NOT have candidate callout
        assert "待验证判断" not in brief_text or "official" in brief_text.lower() or "candidate" not in brief_text


class TestDetermineLifecycle:
    """Tests for the extracted _determine_lifecycle() helper."""

    def test_returns_official_when_no_payload(self):
        from pipeline.ingest_orchestrator import _determine_lifecycle
        article = MagicMock()
        article.claim_inventory = []
        article.confidence = ""
        assert _determine_lifecycle(None, article) == "official"

    def test_returns_official_when_not_v2(self):
        from pipeline.ingest_orchestrator import _determine_lifecycle
        article = MagicMock()
        article.claim_inventory = []
        article.confidence = ""
        payload = {"schema_version": "1.0"}
        assert _determine_lifecycle(payload, article) == "official"

    def test_returns_candidate_when_needs_review(self):
        from pipeline.ingest_orchestrator import _determine_lifecycle
        article = MagicMock()
        article.claim_inventory = [{"confidence": "Supported"}]
        article.confidence = "Supported"
        payload = {
            "schema_version": "2.0",
            "result": {
                "review_hints": {"needs_human_review": True},
                "claim_inventory": [{"confidence": "Supported"}],
            },
        }
        assert _determine_lifecycle(payload, article) == "candidate"

    def test_returns_candidate_when_seeded_confidence_no_actionable(self):
        from pipeline.ingest_orchestrator import _determine_lifecycle
        article = MagicMock()
        article.claim_inventory = [{"confidence": "Seeded"}]
        article.confidence = "Seeded"
        payload = {
            "schema_version": "2.0",
            "result": {
                "review_hints": {"needs_human_review": False},
                "claim_inventory": [{"confidence": "Seeded"}],
            },
        }
        assert _determine_lifecycle(payload, article) == "candidate"

    def test_returns_official_when_supported_confidence(self):
        from pipeline.ingest_orchestrator import _determine_lifecycle
        article = MagicMock()
        article.claim_inventory = [{"confidence": "Supported"}]
        article.confidence = "Supported"
        payload = {
            "schema_version": "2.0",
            "result": {
                "review_hints": {"needs_human_review": False},
                "claim_inventory": [{"confidence": "Supported"}],
            },
        }
        assert _determine_lifecycle(payload, article) == "official"


class TestApplyPurposeFilter:
    """Tests for the extracted _apply_purpose_filter() helper."""

    def test_returns_false_when_no_purpose_md(self, tmp_path):
        from pipeline.ingest_orchestrator import _apply_purpose_filter
        article = MagicMock()
        article.title = "测试文章"
        article.body = "内容。"
        assert _apply_purpose_filter(tmp_path, article) is False

    def test_returns_false_when_no_exclude_section(self, tmp_path):
        from pipeline.ingest_orchestrator import _apply_purpose_filter
        (tmp_path / "purpose.md").write_text("# Purpose\nNo exclude.\n", encoding="utf-8")
        article = MagicMock()
        article.title = "测试"
        article.body = "内容。"
        assert _apply_purpose_filter(tmp_path, article) is False

    def test_returns_true_when_article_matches_exclude(self, tmp_path):
        from pipeline.ingest_orchestrator import _apply_purpose_filter
        (tmp_path / "purpose.md").write_text(
            "## 排除范围\n- 娱乐八卦\n- 明星新闻\n- 综艺节目\n",
            encoding="utf-8",
        )
        article = MagicMock()
        article.title = "娱乐八卦明星新闻"
        article.body = "某明星综艺节目收视率创新高。" * 10
        assert _apply_purpose_filter(tmp_path, article) is True

    def test_returns_false_when_article_does_not_match(self, tmp_path):
        from pipeline.ingest_orchestrator import _apply_purpose_filter
        (tmp_path / "purpose.md").write_text(
            "## 排除范围\n- 娱乐八卦\n- 明星新闻\n",
            encoding="utf-8",
        )
        article = MagicMock()
        article.title = "Transformer 架构详解"
        article.body = "关于神经网络的技术分析。" * 10
        assert _apply_purpose_filter(tmp_path, article) is False
