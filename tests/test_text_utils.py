"""Tests for pipeline/text_utils.py — text processing utilities."""

from __future__ import annotations

import pytest

from pipeline.text_utils import (
    slugify_article,
    parse_frontmatter,
    plain_text,
    sanitize_filename,
    SECTION_PATTERN,
    CLAIM_PATTERN,
    section_body,
)


class TestTextUtils:
    """T2: Text utility functions."""

    def test_slugify_article_unicode(self):
        slug = slugify_article("2026-05-01", "自动驾驶技术综述")
        assert slug.startswith("2026-05-01--")
        assert "自动驾驶" in slug

    def test_slugify_article_no_date(self):
        slug = slugify_article("", "Some Title")
        assert slug == "Some Title"
        assert "--" not in slug

    def test_slugify_article_collision(self):
        """Same date + same title produces same slug (deterministic)."""
        s1 = slugify_article("2026-05-01", "Test Title")
        s2 = slugify_article("2026-05-01", "Test Title")
        assert s1 == s2

    def test_parse_frontmatter_valid(self):
        text = "---\ntitle: My Title\nauthor: Test\n---\nBody content here."
        meta, body = parse_frontmatter(text)
        assert meta["title"] == "My Title"
        assert meta["author"] == "Test"
        assert "Body content" in body

    def test_parse_frontmatter_missing_delimiters(self):
        text = "No frontmatter at all."
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_parse_frontmatter_strips_quotes(self):
        text = '---\ntitle: "Quoted Title"\n---\nBody'
        meta, _ = parse_frontmatter(text)
        assert meta["title"] == "Quoted Title"

    def test_plain_text_strips_markdown(self):
        md = "# Heading\n\n**Bold** and *italic* and `code`.\n\n[Link](http://example.com)"
        result = plain_text(md)
        assert "**" not in result
        assert "*" not in result
        assert "`" not in result
        assert "Link" in result
        assert "http" not in result

    def test_sanitize_filename_removes_invalid_chars(self):
        result = sanitize_filename('file:name*with?bad"chars')
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
        assert '"' not in result

    def test_sanitize_filename_max_length(self):
        long_name = "a" * 200
        result = sanitize_filename(long_name, max_length=50)
        assert len(result) <= 50

    def test_section_body_extracts_heading(self):
        body = "## Summary\nThis is the summary.\n\n## Details\nDetails here."
        result = section_body(body, "Summary")
        assert "This is the summary" in result

    def test_section_body_missing_heading(self):
        body = "## Summary\nSummary text."
        result = section_body(body, "Nonexistent")
        assert result == ""

    def test_section_pattern_matches(self):
        text = "## Key Points\n- Point 1\n- Point 2\n\n## Next\nOther"
        matches = list(SECTION_PATTERN.finditer(text))
        assert len(matches) >= 1
        assert matches[0].group(1).strip() == "Key Points"

    def test_claim_pattern_matches(self):
        text = "- [interpretation|high] This is a high confidence claim\n- [fact|low] This is low"
        matches = list(CLAIM_PATTERN.finditer(text))
        assert len(matches) == 2
        assert matches[0].group(1) == "interpretation"
        assert matches[0].group(2) == "high"
        assert "high confidence claim" in matches[0].group(3)
