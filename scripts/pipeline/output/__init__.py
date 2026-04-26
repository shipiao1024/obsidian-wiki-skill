"""Multi-mode output generation for wiki_query.py — shared helpers and dispatcher.

The original output.py has been split into per-mode files in pipeline/output/:
  brief.py, briefing.py, draft_context.py, contradict.py, digest.py,
  essay.py, reading_list.py, talk_track.py, deep_research.py

This __init__.py provides the shared helpers (_read_page, _page_title),
the dispatcher (build_mode_output), and re-exports all mode builders
for backward compatibility with `from pipeline.output import ...`.
"""

from __future__ import annotations

from pathlib import Path

from pipeline.text_utils import parse_frontmatter


def _read_page(vault: Path, ref: str) -> tuple[dict[str, str], str]:
    """Read a wiki page by ref (e.g. 'sources/slug') and return (meta, body)."""
    path = vault / "wiki" / f"{ref}.md"
    if not path.exists():
        path = vault / f"{ref}.md"
    if not path.exists():
        return {}, ""
    text = path.read_text(encoding="utf-8")
    return parse_frontmatter(text)


def _page_title(meta: dict[str, str], fallback: str = "") -> str:
    return meta.get("title", "").strip('"') or fallback


VALID_MODES = ("brief", "briefing", "draft-context", "contradict", "digest", "essay", "reading-list", "talk-track", "deep-research")


def build_mode_output(
    mode: str,
    vault: Path,
    question: str,
    candidates: list[object],
    raw_paths: list[Path],
    build_answer_fn=None,
    digest_type: str = "deep",
) -> str:
    """Dispatch to the appropriate output mode builder."""
    if mode == "brief":
        if build_answer_fn is None:
            raise ValueError("brief mode requires build_answer_fn")
        from .brief import build_brief_output
        return build_brief_output(question, candidates, raw_paths, build_answer_fn)
    elif mode == "briefing":
        from .briefing import build_briefing_output
        return build_briefing_output(vault, question, candidates)
    elif mode == "draft-context":
        from .draft_context import build_draft_context_output
        return build_draft_context_output(vault, question, candidates)
    elif mode == "contradict":
        from .contradict import build_contradict_output
        return build_contradict_output(vault, question, candidates)
    elif mode == "digest":
        from .digest import build_digest_output
        return build_digest_output(vault, question, candidates, digest_type=digest_type)
    elif mode == "essay":
        from .essay import build_essay_output
        return build_essay_output(vault, question, candidates)
    elif mode == "reading-list":
        from .reading_list import build_reading_list_output, build_reading_list_seed
        if not candidates and digest_type and digest_type != "deep":
            return build_reading_list_seed(vault, digest_type)
        return build_reading_list_output(vault, question, candidates)
    elif mode == "talk-track":
        from .talk_track import build_talk_track_output
        return build_talk_track_output(vault, question, candidates)
    elif mode == "deep-research":
        from .deep_research import build_deep_research_output
        return build_deep_research_output(vault, question, candidates)
    else:
        raise ValueError(f"Unknown mode: {mode}. Valid modes: {', '.join(VALID_MODES)}")


# Backward-compatible re-exports
from .brief import build_brief_output
from .briefing import build_briefing_output
from .draft_context import build_draft_context_output
from .contradict import build_contradict_output
from .digest import build_digest_output, DIGEST_TYPES
from .essay import build_essay_output
from .reading_list import build_reading_list_output, build_reading_list_seed
from .talk_track import build_talk_track_output
from .deep_research import build_deep_research_output

__all__ = [
    "_read_page",
    "_page_title",
    "VALID_MODES",
    "build_mode_output",
    "build_brief_output",
    "build_briefing_output",
    "build_draft_context_output",
    "build_contradict_output",
    "build_digest_output",
    "DIGEST_TYPES",
    "build_essay_output",
    "build_reading_list_output",
    "build_reading_list_seed",
    "build_talk_track_output",
    "build_deep_research_output",
]