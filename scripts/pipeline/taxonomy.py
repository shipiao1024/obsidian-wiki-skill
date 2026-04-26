"""Taxonomy page management: ensure, upgrade, and maintain wiki taxonomy pages."""

from __future__ import annotations

from pathlib import Path

from .types import Article, VALID_PAGE_STATUS, STATUS_UPGRADE_THRESHOLDS
from .text_utils import parse_frontmatter
from .extractors import (
    concept_slug,
    comparison_slug,
    detect_domains,
    domain_slug,
    entity_slug,
    extract_concepts,
    extract_entities,
    mature_concepts,
    mature_entities,
    page_mention_count,
)
from .page_builders import (
    build_concept_page,
    build_entity_page,
    build_domain_page,
    build_synthesis_page,
    build_comparison_page,
    merge_links_section,
    replace_links_section,
    render_frontmatter,
)


def ensure_comparison_page(
    vault: Path,
    subject_a: str,
    subject_b: str,
    source_slug: str,
    dimensions: list[str] = [],
) -> None:
    slug = comparison_slug(f"{subject_a}-vs-{subject_b}")
    path = vault / "wiki" / "comparisons" / f"{slug}.md"
    if not path.exists():
        path.write_text(
            build_comparison_page(
                subject_a=subject_a,
                subject_b=subject_b,
                dimensions=dimensions,
                related_sources=[f"sources/{source_slug}"],
            ),
            encoding="utf-8",
        )
    else:
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        updated = merge_links_section(body, "相关来源", [f"[[sources/{source_slug}]]"], "- （待补充来源）")
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")


def check_and_upgrade_status(vault: Path, folder: str, name: str, slug_fn) -> None:
    """Auto-upgrade page status based on reference count thresholds."""
    path = vault / "wiki" / folder / f"{slug_fn(name)}.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    current = meta.get("status", "seed")
    if current in ("draft",):
        current = "seed"
    if current not in VALID_PAGE_STATUS or current == "evergreen":
        return
    ref_count = page_mention_count(vault, "sources", name)
    ordered = [s for s in VALID_PAGE_STATUS if s != "draft"]
    idx = ordered.index(current) if current in ordered else 0
    for status, threshold in STATUS_UPGRADE_THRESHOLDS.items():
        s_idx = ordered.index(status) if status in ordered else -1
        if s_idx == idx and ref_count >= threshold and idx < len(ordered) - 1:
            meta["status"] = ordered[idx + 1]
            path.write_text(render_frontmatter(meta) + body, encoding="utf-8")
            break


def ensure_taxonomy_pages(
    vault: Path,
    article: Article,
    source_slug: str,
    force: bool,
    domains_override: list[str] | None = None,
    compiled_payload: dict[str, object] | None = None,
) -> None:
    from .compile import promoted_taxonomy_names_from_payload

    concept_names = mature_concepts(vault, extract_concepts(article, limit=8))
    entity_names = mature_entities(vault, extract_entities(article, limit=8))
    for name in promoted_taxonomy_names_from_payload(compiled_payload, "concepts"):
        if name not in concept_names:
            concept_names.append(name)
    for name in promoted_taxonomy_names_from_payload(compiled_payload, "entities"):
        if name not in entity_names:
            entity_names.append(name)
    domain_names = [name for name in (domains_override or detect_domains(article)) if isinstance(name, str) and name.strip()]
    domain_links = [f"[[domains/{domain_slug(name)}]]" for name in domain_names]

    for name in concept_names:
        path = vault / "wiki" / "concepts" / f"{concept_slug(name)}.md"
        if not path.exists():
            path.write_text(build_concept_page(name, source_slug, article), encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        updated = merge_links_section(body, "来自来源", [f"[[sources/{source_slug}]]"], "- 待补充。")
        updated = replace_links_section(updated, "相关主题域", domain_links, "- 待补充。")
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")
        check_and_upgrade_status(vault, "concepts", name, concept_slug)

    for name in entity_names:
        path = vault / "wiki" / "entities" / f"{entity_slug(name)}.md"
        if not path.exists():
            path.write_text(build_entity_page(name, source_slug, article), encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        updated = merge_links_section(body, "来自来源", [f"[[sources/{source_slug}]]"], "- 待补充。")
        updated = replace_links_section(updated, "相关主题域", domain_links, "- 待补充。")
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")
        check_and_upgrade_status(vault, "entities", name, entity_slug)

    for name in domain_names:
        path = vault / "wiki" / "domains" / f"{domain_slug(name)}.md"
        if not path.exists():
            path.write_text(build_domain_page(name, source_slug), encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        updated = merge_links_section(body, "来源", [f"[[sources/{source_slug}]]"], "- 待补充。")
        updated = merge_links_section(
            updated,
            "综合分析",
            [f"[[syntheses/{domain_slug(name)}--综合分析]]"],
            "- 待补充。",
        )
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")
        check_and_upgrade_status(vault, "domains", name, domain_slug)


def ensure_synthesis_pages(
    vault: Path,
    article: Article,
    source_slug: str,
    domains_override: list[str] | None = None,
) -> None:
    domain_names = [name for name in (domains_override or detect_domains(article)) if isinstance(name, str) and name.strip()]
    for name in domain_names:
        if name == "待归域":
            continue
        path = vault / "wiki" / "syntheses" / f"{domain_slug(name)}--综合分析.md"
        if not path.exists():
            path.write_text(build_synthesis_page(vault, name, source_slug, article), encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        updated = merge_links_section(body, "近期来源", [f"[[sources/{source_slug}]]"], "- 待补充。")
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")
