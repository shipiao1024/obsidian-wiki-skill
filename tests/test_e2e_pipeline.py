"""End-to-end pipeline tests — article → ingest → vault output.

These tests exercise the full ingest pipeline with a real temporary vault,
verifying that all expected files are created with correct structure.
No external API calls or network access required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from unittest.mock import patch

from pipeline.pipeline_types import Article, WIKI_DIRS
from pipeline.ingest import ensure_bootstrap
from pipeline.ingest_orchestrator import ingest_article


def _make_article(tmp_path: Path, title: str = "Transformer 架构详解", body: str | None = None) -> Article:
    """Create a realistic article for E2E testing."""
    src_dir = tmp_path / "source"
    src_dir.mkdir(parents=True, exist_ok=True)
    md_path = src_dir / "article.md"
    md_path.write_text(
        f'---\ntitle: "{title}"\nauthor: "测试作者"\ndate: "2026-05-01"\nsource: "https://example.com/test"\n---\n\n'
        f'# {title}\n\n正文内容。\n',
        encoding="utf-8",
    )
    if body is None:
        body = (
            "## 系统架构\n\n"
            "Transformer 是一种基于自注意力机制的神经网络架构。"
            "它在自然语言处理领域取得了突破性进展。\n\n"
            "## 核心组件\n\n"
            "多头注意力机制是 Transformer 的核心组件。"
            "通过查询、键、值三个矩阵的运算实现注意力计算。\n\n"
            "## 应用场景\n\n"
            "Transformer 已广泛应用于文本分类、机器翻译、文本生成等任务。"
            "GPT 和 BERT 都是基于 Transformer 的代表性模型。\n"
        )
    return Article(
        title=title,
        author="测试作者",
        date="2026-05-01",
        source="https://example.com/test",
        body=body,
        src_dir=src_dir,
        md_path=md_path,
        quality="high",
    )


class TestE2ENoCompilePipeline:
    """E2E tests for the no-LLM compile path (compile returns None → status=failed)."""

    @patch("pipeline.compile.try_llm_compile")
    def test_no_compile_ingest_returns_failed_status(self, mock_compile, tmp_path):
        """When compile returns None, status should be 'failed' with only raw page created."""
        mock_compile.return_value = (None, "LLM compile disabled by --no-llm-compile.")
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result = ingest_article(tmp_path, article, force=True, no_llm_compile=True)

        assert result["status"] == "failed"
        assert result["compile_mode"] == "failed"
        slug = result["slug"]

        # Raw article should exist
        raw_path = tmp_path / "raw" / "articles" / f"{slug}.md"
        assert raw_path.exists(), "raw article page missing"
        raw_text = raw_path.read_text(encoding="utf-8")
        assert "title:" in raw_text
        assert "author:" in raw_text

        # Brief and source should NOT exist (no heuristic fallback)
        assert not (tmp_path / "wiki" / "briefs" / f"{slug}.md").exists()
        assert not (tmp_path / "wiki" / "sources" / f"{slug}.md").exists()

    @patch("pipeline.compile.try_llm_compile")
    def test_no_compile_ingest_skip_on_duplicate(self, mock_compile, tmp_path):
        """Second ingest without force should skip (raw page already exists)."""
        mock_compile.return_value = (None, "disabled")
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result1 = ingest_article(tmp_path, article, force=True, no_llm_compile=True)
        assert result1["status"] == "failed"

        result2 = ingest_article(tmp_path, article, force=False, no_llm_compile=True)
        assert result2["status"] == "skipped"
        assert result2["skip_reason"] != ""

    @patch("pipeline.compile.try_llm_compile")
    def test_no_compile_ingest_force_overwrites_raw(self, mock_compile, tmp_path):
        """Second ingest with force should overwrite raw page."""
        mock_compile.return_value = (None, "disabled")
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result1 = ingest_article(tmp_path, article, force=True, no_llm_compile=True)
        result2 = ingest_article(tmp_path, article, force=True, no_llm_compile=True)
        assert result2["status"] == "failed"


class TestE2EV2CompilePipeline:
    """E2E tests for the LLM v2 compile ingest path."""

    @patch("pipeline.compile.try_llm_compile")
    def test_v2_ingest_creates_brief_and_source_from_compile(self, mock_compile, tmp_path, v2_payload):
        """V2 compile should produce brief/source pages from compile payload."""
        mock_compile.return_value = (v2_payload, None)
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result = ingest_article(tmp_path, article, force=True, no_llm_compile=False)

        assert result["status"] == "ingested"
        assert result["compile_mode"] == "llm-v2"
        slug = result["slug"]

        # Brief should contain compile-derived content
        brief_path = tmp_path / "wiki" / "briefs" / f"{slug}.md"
        assert brief_path.exists()
        brief_text = brief_path.read_text(encoding="utf-8")
        assert "test one-sentence summary" in brief_text or "one_sentence" in brief_text

        # Source should contain compile-derived content
        source_path = tmp_path / "wiki" / "sources" / f"{slug}.md"
        assert source_path.exists()

    @patch("pipeline.compile.try_llm_compile")
    def test_v2_ingest_extracts_claims(self, mock_compile, tmp_path, v2_payload):
        """V2 compile should extract claim inventory into article metadata."""
        mock_compile.return_value = (v2_payload, None)
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result = ingest_article(tmp_path, article, force=True, no_llm_compile=False)
        assert result["status"] == "ingested"
        assert result["compile_mode"] == "llm-v2"

    @patch("pipeline.compile.try_llm_compile")
    def test_v2_ingest_with_seeded_confidence_sets_candidate(self, mock_compile, tmp_path, v2_payload):
        """Seeded confidence claims should produce candidate lifecycle pages."""
        for claim in v2_payload["result"]["claim_inventory"]:
            claim["confidence"] = "Seeded"
        mock_compile.return_value = (v2_payload, None)
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result = ingest_article(tmp_path, article, force=True, no_llm_compile=False)
        slug = result["slug"]

        brief_text = (tmp_path / "wiki" / "briefs" / f"{slug}.md").read_text(encoding="utf-8")
        assert "candidate" in brief_text

    @patch("pipeline.compile.try_llm_compile")
    def test_v2_ingest_creates_question_pages(self, mock_compile, tmp_path, v2_payload):
        """V2 compile with open_questions should create question pages."""
        mock_compile.return_value = (v2_payload, None)
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result = ingest_article(tmp_path, article, force=True, no_llm_compile=False)
        assert result["status"] == "ingested"

        question_dir = tmp_path / "wiki" / "questions"
        question_pages = list(question_dir.glob("*.md"))
        assert len(question_pages) >= 1, "no question pages created from open_questions"

    @patch("pipeline.compile.try_llm_compile")
    def test_v2_ingest_creates_delta_pages(self, mock_compile, tmp_path, v2_payload):
        """V2 compile with update_proposals should create delta pages."""
        v2_payload["result"]["update_proposals"] = [
            {
                "target_page": "concepts/transformer",
                "action": "append_section",
                "content": "新增内容",
                "rationale": "测试",
            }
        ]
        mock_compile.return_value = (v2_payload, None)
        ensure_bootstrap(tmp_path)
        article = _make_article(tmp_path)

        result = ingest_article(tmp_path, article, force=True, no_llm_compile=False)
        assert result["status"] == "ingested"
        assert result.get("delta_outputs", "") != ""


class TestE2EVaultStructure:
    """E2E tests verifying vault directory structure integrity."""

    def test_bootstrap_creates_all_wiki_dirs(self, tmp_path):
        """ensure_bootstrap should create all directories defined in WIKI_DIRS."""
        ensure_bootstrap(tmp_path)
        for d in WIKI_DIRS:
            assert (tmp_path / d).exists(), f"Missing directory: {d}"

    def test_bootstrap_idempotent(self, tmp_path):
        """ensure_bootstrap should be safe to call multiple times."""
        ensure_bootstrap(tmp_path)
        ensure_bootstrap(tmp_path)  # should not raise
        for d in WIKI_DIRS:
            assert (tmp_path / d).exists()

    @patch("pipeline.compile.try_llm_compile")
    def test_ingest_preserves_existing_files(self, mock_compile, tmp_path):
        """Ingesting one article should not corrupt another article's files."""
        mock_compile.return_value = (None, "disabled")
        ensure_bootstrap(tmp_path)

        article1 = _make_article(tmp_path, title="第一篇文章")
        article2 = _make_article(tmp_path, title="第二篇文章")

        result1 = ingest_article(tmp_path, article1, force=True, no_llm_compile=True)
        result2 = ingest_article(tmp_path, article2, force=True, no_llm_compile=True)

        slug1 = result1["slug"]
        slug2 = result2["slug"]
        assert slug1 != slug2

        # Both raw pages should exist
        assert (tmp_path / "raw" / "articles" / f"{slug1}.md").exists()
        assert (tmp_path / "raw" / "articles" / f"{slug2}.md").exists()

    @patch("pipeline.compile.try_llm_compile")
    def test_ingest_with_transcript(self, mock_compile, tmp_path):
        """Article with transcript body should create transcript page."""
        mock_compile.return_value = (None, "disabled")
        ensure_bootstrap(tmp_path)

        article = _make_article(tmp_path)
        article.transcript_body = "这是视频的文字稿内容。"
        article.transcript_source = "platform_subtitle"
        article.transcript_stage = "transcript"

        result = ingest_article(tmp_path, article, force=True, no_llm_compile=True)
        slug = result["slug"]

        transcript_path = tmp_path / "raw" / "transcripts" / f"{slug}--transcript.md"
        assert transcript_path.exists(), "transcript page missing"
        transcript_text = transcript_path.read_text(encoding="utf-8")
        assert "文字稿" in transcript_text or "transcript" in transcript_text.lower()
