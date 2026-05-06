"""Tests for pipeline/vault_config.py — vault resolution and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.vault_config import (
    video_id_from_url,
    normalize_collection_url,
    transcript_fidelity,
    parse_purpose_md,
    load_domain_keywords,
    DEFAULT_DOMAINS as VC_DEFAULT_DOMAINS,
)
from pipeline.pipeline_types import Article, DEFAULT_DOMAINS as TYPES_DEFAULT_DOMAINS


class TestVaultConfig:
    """T9: Vault configuration and URL helpers."""

    def test_video_id_from_url_youtube(self):
        vid = video_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_video_id_from_url_youtube_short(self):
        vid = video_id_from_url("https://youtu.be/dQw4w9WgXcQ")
        assert vid == "dQw4w9WgXcQ"

    def test_video_id_from_url_bilibili(self):
        vid = video_id_from_url("https://www.bilibili.com/video/BV1xx411c7mD?p=2")
        assert vid == "BV1xx411c7mD:p2"

    def test_video_id_from_url_douyin(self):
        vid = video_id_from_url("https://www.douyin.com/video/1234567890")
        assert vid == "1234567890"

    def test_video_id_from_url_unknown(self):
        vid = video_id_from_url("https://example.com/some/page")
        assert vid  # should return sanitized URL, not empty

    def test_transcript_fidelity_asr_capped_at_acceptable(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        md_path = src_dir / "a.md"
        md_path.write_text("x", encoding="utf-8")
        article = Article(
            title="T", author="A", date="2026-01-01",
            source="http://x.com", body="b",
            src_dir=src_dir, md_path=md_path,
            transcript_source="asr",
        )
        fidelity = transcript_fidelity(article)
        assert fidelity == "machine-transcribed"

    def test_transcript_fidelity_platform_subtitle(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        md_path = src_dir / "a.md"
        md_path.write_text("x", encoding="utf-8")
        article = Article(
            title="T", author="A", date="2026-01-01",
            source="http://x.com", body="b",
            src_dir=src_dir, md_path=md_path,
            transcript_source="platform_subtitle",
        )
        fidelity = transcript_fidelity(article)
        assert fidelity == "source-provided"

    def test_parse_purpose_md_no_file(self, tmp_path):
        result = parse_purpose_md(tmp_path)
        assert result == {"focus": [], "exclude": []}

    def test_parse_purpose_md_with_domains(self, tmp_path):
        purpose = tmp_path / "purpose.md"
        purpose.write_text(
            "## 关注领域\n- AI 工程\n- 认知科学\n## 排除范围\n- 娱乐八卦\n",
            encoding="utf-8",
        )
        result = parse_purpose_md(tmp_path)
        assert "AI 工程" in result["focus"]
        assert "认知科学" in result["focus"]
        assert "娱乐八卦" in result["exclude"]

    def test_load_domain_keywords_no_vault(self):
        keywords = load_domain_keywords(None)
        assert len(keywords) > 0
        assert "AI 工程" in keywords

    def test_load_domain_keywords_with_purpose(self, tmp_path):
        purpose = tmp_path / "purpose.md"
        purpose.write_text("## 关注领域\n- AI 工程\n- 机器人\n", encoding="utf-8")
        keywords = load_domain_keywords(tmp_path)
        assert "AI 工程" in keywords
        assert "机器人" in keywords
        # Domains not in purpose.md should not be included
        assert "社会批判" not in keywords

    def test_load_domain_keywords_empty_purpose(self, tmp_path):
        purpose = tmp_path / "purpose.md"
        purpose.write_text("# Purpose\nNo domains here.\n", encoding="utf-8")
        keywords = load_domain_keywords(tmp_path)
        # Should fall back to DEFAULT_DOMAINS
        assert len(keywords) > 0

    def test_default_domains_consistent_across_modules(self):
        """vault_config.DEFAULT_DOMAINS and types.DEFAULT_DOMAINS must be the same object."""
        assert VC_DEFAULT_DOMAINS is TYPES_DEFAULT_DOMAINS

    def test_default_domains_reexported_by_shared(self):
        """shared.py must re-export DEFAULT_DOMAINS from vault_config."""
        from pipeline.shared import DEFAULT_DOMAINS as SHARED_DEFAULT_DOMAINS
        assert SHARED_DEFAULT_DOMAINS is VC_DEFAULT_DOMAINS

    def test_load_domain_keywords_reexported_by_shared(self):
        """shared.py must re-export load_domain_keywords from vault_config."""
        from pipeline.shared import load_domain_keywords as shared_lck
        assert shared_lck is load_domain_keywords
