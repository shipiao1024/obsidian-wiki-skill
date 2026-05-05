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


VALID_MODES = ("auto", "brief", "briefing", "draft-context", "contradict", "digest", "essay", "reading-list", "talk-track", "deep-research")


def build_mode_output(
    mode: str,
    vault: Path,
    question: str,
    candidates: list[object],
    raw_paths: list[Path],
    build_answer_fn=None,
    digest_type: str = "deep",
) -> tuple[str, dict[str, str]]:
    """Dispatch to the appropriate output mode builder.

    Returns (answer_text, routing_info) where routing_info contains:
      - resolved_mode: the actual mode used (after auto-routing)
      - resolved_digest_type: the actual digest sub-type
      - entry_layer: "ask" / "digest" / "context"
      - auto_routed: "true" if mode was auto-detected
    """
    routing_info: dict[str, str] = {}

    # --- Auto-routing: resolve intent from natural language ---
    if mode == "auto":
        from .intent_router import resolve_intent
        resolved_mode, resolved_digest, entry = resolve_intent(question)
        routing_info = {
            "resolved_mode": resolved_mode,
            "resolved_digest_type": resolved_digest,
            "entry_layer": entry,
            "auto_routed": "true",
        }
        # Recurse with resolved mode
        answer, _inner_info = build_mode_output(
            mode=resolved_mode,
            vault=vault,
            question=question,
            candidates=candidates,
            raw_paths=raw_paths,
            build_answer_fn=build_answer_fn,
            digest_type=resolved_digest,
        )
        return answer, routing_info

    # --- Direct mode dispatch ---
    routing_info = {
        "resolved_mode": mode,
        "resolved_digest_type": digest_type,
        "entry_layer": _mode_to_entry(mode),
        "auto_routed": "false",
    }

    if mode == "brief":
        if build_answer_fn is None:
            raise ValueError("brief mode requires build_answer_fn")
        from .brief import build_brief_output
        return build_brief_output(question, candidates, raw_paths, build_answer_fn), routing_info
    elif mode == "briefing":
        from .briefing import build_briefing_output
        return build_briefing_output(vault, question, candidates), routing_info
    elif mode == "draft-context":
        from .draft_context import build_draft_context_output
        return build_draft_context_output(vault, question, candidates), routing_info
    elif mode == "contradict":
        from .contradict import build_contradict_output
        return build_contradict_output(vault, question, candidates), routing_info
    elif mode == "digest":
        from .digest import build_digest_output
        return build_digest_output(vault, question, candidates, digest_type=digest_type), routing_info
    elif mode == "essay":
        from .essay import build_essay_output
        return build_essay_output(vault, question, candidates), routing_info
    elif mode == "reading-list":
        from .reading_list import build_reading_list_output, build_reading_list_seed
        if not candidates and digest_type and digest_type != "deep":
            return build_reading_list_seed(vault, digest_type), routing_info
        return build_reading_list_output(vault, question, candidates), routing_info
    elif mode == "talk-track":
        from .talk_track import build_talk_track_output
        return build_talk_track_output(vault, question, candidates), routing_info
    elif mode == "deep-research":
        from .deep_research import build_deep_research_output
        return build_deep_research_output(vault, question, candidates), routing_info
    else:
        raise ValueError(f"Unknown mode: {mode}. Valid modes: {', '.join(VALID_MODES)}")


def _mode_to_entry(mode: str) -> str:
    """Map a resolved mode back to its entry layer for reporting."""
    if mode in ("brief", "briefing", "contradict", "talk-track", "deep-research"):
        return "ask"
    if mode in ("digest", "essay", "reading-list"):
        return "digest"
    if mode == "draft-context":
        return "context"
    return "ask"


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