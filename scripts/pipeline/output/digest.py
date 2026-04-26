"""Mode: digest — deep / compare / timeline multi-source aggregation."""

from __future__ import annotations

from pathlib import Path

DIGEST_TYPES = ("deep", "compare", "timeline")


def build_digest_output(
    vault: Path,
    question: str,
    candidates: list[object],
    *,
    digest_type: str = "deep",
) -> str:
    """Multi-source digest aggregation."""
    from pipeline.digest import collect_digest_sources, build_deep_report, build_comparison_table, build_timeline, write_digest_page

    if digest_type not in DIGEST_TYPES:
        raise ValueError(f"Invalid digest_type: {digest_type}. Valid: {', '.join(DIGEST_TYPES)}")

    sources = collect_digest_sources(vault, question, limit=10)

    if digest_type == "deep":
        content = build_deep_report(vault, question, sources)
    elif digest_type == "compare":
        content = build_comparison_table(vault, question, sources)
    elif digest_type == "timeline":
        content = build_timeline(vault, question, sources)
    else:
        content = build_deep_report(vault, question, sources)

    write_digest_page(vault, question, digest_type, content)
    return content