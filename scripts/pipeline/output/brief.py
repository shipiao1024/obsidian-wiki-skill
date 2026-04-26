"""Mode: brief — current behaviour (top excerpts from candidates)."""

from __future__ import annotations

from pathlib import Path


def build_brief_output(
    question: str,
    candidates: list[object],
    raw_paths: list[Path],
    build_answer_fn,
) -> str:
    """Thin wrapper so all modes share the same call signature."""
    return build_answer_fn(question, candidates, raw_paths)