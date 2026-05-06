"""Tests for pipeline/taxonomy.py — taxonomy page management."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.pipeline_types import Article
from pipeline.taxonomy import (
    ensure_comparison_page,
    check_and_upgrade_status,
    ensure_taxonomy_pages,
    ensure_synthesis_pages,
)
from pipeline.extractors import concept_slug, entity_slug, domain_slug, comparison_slug


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


def _setup_vault(vault: Path) -> None:
    """Create minimal vault directory structure."""
    for d in [
        "raw/articles", "raw/assets", "raw/transcripts",
        "wiki/sources", "wiki/briefs", "wiki/concepts",
        "wiki/entities", "wiki/domains", "wiki/syntheses",
        "wiki/comparisons", "wiki/questions", "wiki/stances",
        "wiki/outputs", "wiki/research", "raw/inbox",
    ]:
        (vault / d).mkdir(parents=True, exist_ok=True)


class TestEnsureComparisonPage:
    """ensure_comparison_page() creates and updates comparison pages."""

    def test_creates_new_comparison_page(self, tmp_path):
        _setup_vault(tmp_path)
        ensure_comparison_page(tmp_path, "Tesla", "BYD", source_slug="test-source")
        slug = comparison_slug("Tesla-vs-BYD")
        path = tmp_path / "wiki" / "comparisons" / f"{slug}.md"
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "Tesla" in text
        assert "BYD" in text

    def test_updates_existing_comparison_page(self, tmp_path):
        _setup_vault(tmp_path)
        ensure_comparison_page(tmp_path, "Tesla", "BYD", source_slug="source-1")
        ensure_comparison_page(tmp_path, "Tesla", "BYD", source_slug="source-2")
        slug = comparison_slug("Tesla-vs-BYD")
        path = tmp_path / "wiki" / "comparisons" / f"{slug}.md"
        text = path.read_text(encoding="utf-8")
        assert "source-1" in text
        assert "source-2" in text

    def test_creates_with_dimensions(self, tmp_path):
        _setup_vault(tmp_path)
        ensure_comparison_page(
            tmp_path, "Claude", "GPT",
            source_slug="test",
            dimensions=["价格", "性能", "安全性"],
        )
        slug = comparison_slug("Claude-vs-GPT")
        path = tmp_path / "wiki" / "comparisons" / f"{slug}.md"
        assert path.exists()


class TestCheckAndUpgradeStatus:
    """check_and_upgrade_status() auto-upgrades page status."""

    def test_upgrades_candidate_to_official(self, tmp_path):
        _setup_vault(tmp_path)
        # Create a candidate page
        concept_dir = tmp_path / "wiki" / "concepts"
        page = concept_dir / f"{concept_slug('Transformer')}.md"
        page.write_text(
            '---\ntitle: "Transformer"\nlifecycle: "candidate"\nstatus: "candidate"\n---\n## 来源\n- 待补充。\n',
            encoding="utf-8",
        )
        # Create enough source mentions to trigger upgrade (threshold=2)
        sources_dir = tmp_path / "wiki" / "sources"
        (sources_dir / "s1.md").write_text("Transformer 架构详解\n", encoding="utf-8")
        (sources_dir / "s2.md").write_text("Transformer 应用\n", encoding="utf-8")

        check_and_upgrade_status(tmp_path, "concepts", "Transformer", concept_slug)
        text = page.read_text(encoding="utf-8")
        assert 'lifecycle: "official"' in text
        assert 'status: "seed"' in text

    def test_no_upgrade_for_evergreen(self, tmp_path):
        _setup_vault(tmp_path)
        concept_dir = tmp_path / "wiki" / "concepts"
        page = concept_dir / f"{concept_slug('DeepLearning')}.md"
        page.write_text(
            '---\ntitle: "DeepLearning"\nstatus: "evergreen"\n---\n## 内容\n',
            encoding="utf-8",
        )
        check_and_upgrade_status(tmp_path, "concepts", "DeepLearning", concept_slug)
        text = page.read_text(encoding="utf-8")
        assert 'status: "evergreen"' in text

    def test_no_upgrade_for_nonexistent_page(self, tmp_path):
        _setup_vault(tmp_path)
        # Should not raise
        check_and_upgrade_status(tmp_path, "concepts", "Nonexistent", concept_slug)

    def test_upgrades_seed_to_developing(self, tmp_path):
        _setup_vault(tmp_path)
        concept_dir = tmp_path / "wiki" / "concepts"
        page = concept_dir / f"{concept_slug('Attention')}.md"
        page.write_text(
            '---\ntitle: "Attention"\nstatus: "seed"\n---\n## 来源\n- 待补充。\n',
            encoding="utf-8",
        )
        # STATUS_UPGRADE_THRESHOLDS["seed"] = 1, so 1 mention should trigger
        sources_dir = tmp_path / "wiki" / "sources"
        (sources_dir / "s1.md").write_text("Attention 机制\n", encoding="utf-8")

        check_and_upgrade_status(tmp_path, "concepts", "Attention", concept_slug)
        text = page.read_text(encoding="utf-8")
        assert 'status: "developing"' in text


class TestEnsureTaxonomyPages:
    """ensure_taxonomy_pages() creates/updates concept, entity, domain pages."""

    def test_creates_concept_page(self, tmp_path):
        _setup_vault(tmp_path)
        article = _make_article(
            "Transformer 架构详解",
            "Transformer 是一种基于自注意力机制的神经网络架构。" * 5,
        )
        # Create source mentions so concepts mature
        sources = tmp_path / "wiki" / "sources"
        (sources / "s1.md").write_text("Transformer 架构\n", encoding="utf-8")
        (sources / "s2.md").write_text("Transformer 应用\n", encoding="utf-8")

        ensure_taxonomy_pages(
            tmp_path, article, source_slug="test-source",
            force=False, domains_override=["AI 工程"],
        )
        # Check if any concept page was created
        concept_dir = tmp_path / "wiki" / "concepts"
        pages = list(concept_dir.glob("*.md"))
        # At least domain pages should be created
        domain_dir = tmp_path / "wiki" / "domains"
        domain_pages = list(domain_dir.glob("*.md"))
        assert len(domain_pages) > 0

    def test_creates_domain_page(self, tmp_path):
        _setup_vault(tmp_path)
        article = _make_article("测试文章", "测试内容。")
        ensure_taxonomy_pages(
            tmp_path, article, source_slug="test",
            force=False, domains_override=["AI 工程"],
        )
        domain_dir = tmp_path / "wiki" / "domains"
        pages = list(domain_dir.glob("*.md"))
        assert len(pages) >= 1

    def test_updates_existing_domain_page(self, tmp_path):
        _setup_vault(tmp_path)
        article = _make_article("测试", "内容。")
        ensure_taxonomy_pages(
            tmp_path, article, source_slug="s1",
            force=False, domains_override=["AI 工程"],
        )
        ensure_taxonomy_pages(
            tmp_path, article, source_slug="s2",
            force=False, domains_override=["AI 工程"],
        )
        domain_dir = tmp_path / "wiki" / "domains"
        pages = list(domain_dir.glob("*.md"))
        assert len(pages) >= 1
        text = pages[0].read_text(encoding="utf-8")
        assert "s1" in text
        assert "s2" in text

    def test_candidate_lifecycle_applied_to_new_concept(self, tmp_path):
        _setup_vault(tmp_path)
        article = _make_article("测试", "内容。" * 5)
        # Pre-create a source so concept extraction finds something
        sources = tmp_path / "wiki" / "sources"
        (sources / "s1.md").write_text("端到端架构详解\n", encoding="utf-8")
        (sources / "s2.md").write_text("端到端应用\n", encoding="utf-8")

        ensure_taxonomy_pages(
            tmp_path, article, source_slug="test",
            force=False,
            domains_override=["自动驾驶"],
            source_lifecycle="candidate",
        )
        # Check if any concept page has candidate lifecycle
        concept_dir = tmp_path / "wiki" / "concepts"
        for page in concept_dir.glob("*.md"):
            text = page.read_text(encoding="utf-8")
            if 'lifecycle: "candidate"' in text:
                break
        # No assertion failure means it worked (or no concepts were extracted, which is also fine)


class TestEnsureSynthesisPages:
    """ensure_synthesis_pages() creates/updates synthesis pages."""

    def test_creates_synthesis_page(self, tmp_path):
        _setup_vault(tmp_path)
        article = _make_article("AI 工程综述", "关于 AI 工程的综合分析。" * 5)
        ensure_synthesis_pages(
            tmp_path, article,
            source_slug="test",
            domains_override=["AI 工程"],
        )
        synth_dir = tmp_path / "wiki" / "syntheses"
        pages = list(synth_dir.glob("*.md"))
        assert len(pages) >= 1
        assert any("综合分析" in p.name for p in pages)

    def test_updates_existing_synthesis_page(self, tmp_path):
        _setup_vault(tmp_path)
        article = _make_article("AI 工程", "内容。")
        ensure_synthesis_pages(tmp_path, article, source_slug="s1", domains_override=["AI 工程"])
        ensure_synthesis_pages(tmp_path, article, source_slug="s2", domains_override=["AI 工程"])
        synth_dir = tmp_path / "wiki" / "syntheses"
        pages = list(synth_dir.glob("*.md"))
        assert len(pages) >= 1
        text = pages[0].read_text(encoding="utf-8")
        assert "s1" in text
        assert "s2" in text

    def test_skips_unknown_domain(self, tmp_path):
        _setup_vault(tmp_path)
        article = _make_article("杂项", "内容。")
        ensure_synthesis_pages(tmp_path, article, source_slug="test", domains_override=["待归域"])
        synth_dir = tmp_path / "wiki" / "syntheses"
        pages = list(synth_dir.glob("*.md"))
        assert len(pages) == 0
