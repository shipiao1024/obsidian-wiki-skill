"""Tests for pipeline/page_builders.py — wiki page generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.page_builders import (
    render_frontmatter,
    build_brief_page_from_compile,
    build_source_page_from_compile,
    article_output_exists,
    write_page,
)
from pipeline.pipeline_types import Article


class TestPageBuilders:
    """T6: Page generation and lifecycle rendering."""

    @pytest.fixture
    def article(self):
        return Article(
            title="Test Title",
            author="Author",
            date="2026-05-01",
            source="http://example.com",
            body="## Summary\nThis is the summary section with enough text.\n\n## Details\nMore details here for testing.",
            src_dir=Path("/tmp/src"),
            md_path=Path("/tmp/src/article.md"),
            quality="high",
        )

    def test_render_frontmatter_all_fields(self):
        frontmatter = render_frontmatter({
            "title": "Test",
            "type": "source",
            "slug": "2026-05-01--test",
            "status": "seed",
            "lifecycle": "official",
            "quality": "high",
        })
        assert 'title: "Test"' in frontmatter
        assert 'type: "source"' in frontmatter
        assert 'status: "seed"' in frontmatter
        assert 'lifecycle: "official"' in frontmatter

    def test_build_brief_from_compile_with_claims(self, article):
        compiled = {
            "brief": {
                "one_sentence": "Compiled summary.",
                "key_points": ["Point 1", "Point 2"],
            },
            "source": {
                "core_summary": ["Summary 1"],
                "domains": [],
                "knowledge_base_relation": [],
                "contradictions": [],
                "reinforcements": [],
            },
            "claim_inventory": [
                {"claim": "Test claim", "claim_type": "interpretation", "confidence": "Supported",
                 "evidence_type": "fact", "grounding_quote": "Compiled summary."},
            ],
        }
        page = build_brief_page_from_compile(article, "2026-05-01--test", compiled, lifecycle="official")
        assert "Compiled summary" in page
        assert "Point 1" in page
        assert "Test claim" in page

    def test_build_brief_from_compile_candidate_lifecycle(self, article):
        compiled = {
            "brief": {
                "one_sentence": "Low confidence summary.",
                "key_points": ["Point 1"],
            },
            "source": {
                "core_summary": ["Summary 1"],
                "domains": [],
                "knowledge_base_relation": [],
                "contradictions": [],
                "reinforcements": [],
            },
            "claim_inventory": [
                {"claim": "Weak claim", "claim_type": "assumption", "confidence": "Seeded",
                 "evidence_type": "assumption", "grounding_quote": ""},
            ],
        }
        page = build_brief_page_from_compile(article, "2026-05-01--test", compiled, lifecycle="candidate")
        assert "candidate" in page
        assert "候选页待审" in page

    def test_build_source_page_from_compile(self, article):
        compiled = {
            "brief": {"one_sentence": "S", "key_points": ["KP"]},
            "source": {
                "core_summary": ["Core summary point"],
                "domains": ["AI 工程"],
                "knowledge_base_relation": [],
                "contradictions": [],
                "reinforcements": [],
            },
            "claim_inventory": [
                {"claim": "Source claim", "claim_type": "fact", "confidence": "Working",
                 "evidence_type": "fact", "grounding_quote": "Core summary point"},
            ],
        }
        page = build_source_page_from_compile(
            Path("/tmp/vault"), article, "2026-05-01--test", compiled, lifecycle="official"
        )
        assert "核心摘要" in page
        assert "Core summary point" in page

    def test_article_output_exists_false(self, vault):
        assert article_output_exists(vault, "nonexistent-slug") is False

    def test_article_output_exists_true(self, vault):
        slug = "2026-05-01--test"
        (vault / "raw" / "articles" / f"{slug}.md").write_text("---\ntitle: T\n---\n", encoding="utf-8")
        (vault / "wiki" / "sources" / f"{slug}.md").write_text("---\ntitle: T\n---\n", encoding="utf-8")
        (vault / "wiki" / "briefs" / f"{slug}.md").write_text("---\ntitle: T\n---\n", encoding="utf-8")
        assert article_output_exists(vault, slug) is True

    def test_write_page_creates_file(self, vault):
        path = vault / "wiki" / "briefs" / "test.md"
        write_page(path, "---\ntitle: T\n---\nContent", force=False)
        assert path.exists()
        assert "Content" in path.read_text(encoding="utf-8")

    def test_write_page_no_overwrite_without_force(self, vault):
        path = vault / "wiki" / "briefs" / "test.md"
        path.write_text("original", encoding="utf-8")
        write_page(path, "new content", force=False)
        assert path.read_text(encoding="utf-8") == "original"

    def test_write_page_overwrites_with_force(self, vault):
        path = vault / "wiki" / "briefs" / "test.md"
        path.write_text("original", encoding="utf-8")
        write_page(path, "new content", force=True)
        assert path.read_text(encoding="utf-8") == "new content"
