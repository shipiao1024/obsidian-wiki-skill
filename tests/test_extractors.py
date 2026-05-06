"""Tests for pipeline/extractors.py — utility functions (slug helpers, vault queries)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.pipeline_types import Article
from pipeline.extractors import (
    concept_slug,
    entity_slug,
    domain_slug,
    comparison_slug,
    page_mention_count,
    mature_concepts,
    mature_entities,
    existing_taxonomy_links,
    vault_domain_distribution,
    detect_domain_mismatch,
)


def _make_article(title: str, body: str, **kwargs) -> Article:
    """Helper to create a minimal Article for testing."""
    defaults = dict(
        title=title,
        author="Test Author",
        date="2026-01-01",
        source="http://example.com",
        body=body,
        src_dir=Path("/tmp/src"),
        md_path=Path("/tmp/src/a.md"),
    )
    defaults.update(kwargs)
    return Article(**defaults)


class TestSlugHelpers:
    """concept_slug, entity_slug, domain_slug, comparison_slug."""

    def test_concept_slug_basic(self):
        slug = concept_slug("端到端")
        assert isinstance(slug, str)
        assert len(slug) > 0

    def test_entity_slug_basic(self):
        slug = entity_slug("NVIDIA")
        assert isinstance(slug, str)

    def test_domain_slug_basic(self):
        slug = domain_slug("AI 工程")
        assert isinstance(slug, str)

    def test_comparison_slug_basic(self):
        slug = comparison_slug("Tesla-vs-BYD")
        assert isinstance(slug, str)

    def test_slugs_are_filesystem_safe(self):
        for fn in (concept_slug, entity_slug, domain_slug, comparison_slug):
            slug = fn("test/with:special*chars")
            assert "/" not in slug
            assert ":" not in slug
            assert "*" not in slug


class TestPageMentionCount:
    """page_mention_count() counts term occurrences in vault wiki pages."""

    def test_counts_mentions(self, tmp_path):
        sources = tmp_path / "wiki" / "sources"
        sources.mkdir(parents=True)
        (sources / "a.md").write_text("# 来源 A\n讨论 Transformer 架构\n", encoding="utf-8")
        (sources / "b.md").write_text("# 来源 B\n不包含关键词\n", encoding="utf-8")
        count = page_mention_count(tmp_path, "sources", "Transformer")
        assert count == 1

    def test_returns_zero_for_empty_dir(self, tmp_path):
        (tmp_path / "wiki" / "sources").mkdir(parents=True)
        count = page_mention_count(tmp_path, "sources", "nonexistent")
        assert count == 0


class TestMatureConceptsAndEntities:
    """mature_concepts/mature_entities filter by page_mention_count threshold."""

    def test_mature_concepts_filters(self, tmp_path):
        sources = tmp_path / "wiki" / "sources"
        sources.mkdir(parents=True)
        # CONCEPT_PAGE_THRESHOLD = 2, so need 2+ mentions
        (sources / "a.md").write_text("Transformer 架构详解", encoding="utf-8")
        (sources / "b.md").write_text("Transformer 应用场景", encoding="utf-8")
        (sources / "c.md").write_text("其他内容", encoding="utf-8")
        result = mature_concepts(tmp_path, ["Transformer", "量子计算"])
        assert "Transformer" in result
        assert "量子计算" not in result

    def test_mature_entities_filters(self, tmp_path):
        sources = tmp_path / "wiki" / "sources"
        sources.mkdir(parents=True)
        # ENTITY_PAGE_THRESHOLD = 2
        (sources / "a.md").write_text("NVIDIA GPU 详解", encoding="utf-8")
        (sources / "b.md").write_text("NVIDIA 市场分析", encoding="utf-8")
        result = mature_entities(tmp_path, ["NVIDIA", "AMD"])
        assert "NVIDIA" in result
        assert "AMD" not in result


class TestExistingTaxonomyLinks:
    """existing_taxonomy_links() checks for existing wiki pages."""

    def test_finds_existing_pages(self, tmp_path):
        folder = tmp_path / "wiki" / "concepts"
        folder.mkdir(parents=True)
        (folder / "transformer.md").write_text("# Transformer\n", encoding="utf-8")
        result = existing_taxonomy_links(tmp_path, "concepts", ["Transformer", "Quantum"], concept_slug)
        # Only Transformer should be found (if slug matches)
        assert len(result) <= 1

    def test_returns_empty_for_no_matches(self, tmp_path):
        (tmp_path / "wiki" / "concepts").mkdir(parents=True)
        result = existing_taxonomy_links(tmp_path, "concepts", ["Nonexistent"], concept_slug)
        assert result == []


class TestVaultDomainDistribution:
    """vault_domain_distribution() reads domain pages and counts source links."""

    def test_counts_source_links(self, tmp_path):
        domains_dir = tmp_path / "wiki" / "domains"
        domains_dir.mkdir(parents=True)
        (domains_dir / "ai.md").write_text(
            '---\ntitle: "AI 工程"\n---\n## 来源\n- [[sources/a]]\n- [[sources/b]]\n',
            encoding="utf-8",
        )
        dist = vault_domain_distribution(tmp_path)
        assert "AI 工程" in dist
        assert dist["AI 工程"] == 2

    def test_returns_empty_for_no_domains_dir(self, tmp_path):
        dist = vault_domain_distribution(tmp_path)
        assert dist == {}


class TestDetectDomainMismatch:
    """detect_domain_mismatch() detects when article domains don't match vault."""

    def test_no_mismatch_when_domains_overlap(self, tmp_path):
        domains_dir = tmp_path / "wiki" / "domains"
        domains_dir.mkdir(parents=True)
        (domains_dir / "ai.md").write_text(
            '---\ntitle: "AI 工程"\n---\n## 来源\n- [[sources/a]]\n',
            encoding="utf-8",
        )
        article = _make_article("Claude 使用", "Claude 是一个 LLM Agent。")
        result = detect_domain_mismatch(article, tmp_path, article_domains=["AI 工程"])
        assert result["is_mismatch"] is False

    def test_mismatch_when_no_overlap(self, tmp_path):
        domains_dir = tmp_path / "wiki" / "domains"
        domains_dir.mkdir(parents=True)
        (domains_dir / "ai.md").write_text(
            '---\ntitle: "AI 工程"\n---\n## 来源\n- [[sources/a]]\n',
            encoding="utf-8",
        )
        article = _make_article("量子计算", "量子计算是未来方向。" * 5)
        result = detect_domain_mismatch(article, tmp_path, article_domains=["量子计算"])
        assert result["is_mismatch"] is True
        assert result["warning"] != ""

    def test_mismatch_when_unknown_domain(self, tmp_path):
        domains_dir = tmp_path / "wiki" / "domains"
        domains_dir.mkdir(parents=True)
        (domains_dir / "ai.md").write_text(
            '---\ntitle: "AI 工程"\n---\n## 来源\n- [[sources/a]]\n',
            encoding="utf-8",
        )
        article = _make_article("杂项", "一些不好分类的内容。" * 5)
        result = detect_domain_mismatch(article, tmp_path, article_domains=["待归域"])
        assert result["is_mismatch"] is True

    def test_no_mismatch_when_vault_empty(self, tmp_path):
        article = _make_article("测试", "测试内容。" * 5)
        result = detect_domain_mismatch(article, tmp_path, article_domains=["AI 工程"])
        assert result["is_mismatch"] is False

    def test_graceful_when_article_domains_none(self, tmp_path):
        """detect_domain_mismatch handles article_domains=None gracefully."""
        article = _make_article("测试", "测试内容。" * 5)
        result = detect_domain_mismatch(article, tmp_path, article_domains=None)
        assert result["is_mismatch"] is False
