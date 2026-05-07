"""Taxonomy page management: ensure, upgrade, and maintain wiki taxonomy pages."""

from __future__ import annotations

import re
from pathlib import Path

from .pipeline_types import Article, VALID_PAGE_STATUS, STATUS_UPGRADE_THRESHOLDS
from .text_utils import parse_frontmatter
from .extractors import (
    concept_slug,
    comparison_slug,
    domain_slug,
    entity_slug,
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


def _fill_placeholder_definition(body: str, section_name: str, definition: str) -> str:
    """Replace a placeholder definition with a real one, only if the section is empty."""
    if not definition:
        return body
    pattern = rf'(##\s+{re.escape(section_name)}\s*\n\n)(-?\s*待[^\n]*)'
    m = re.search(pattern, body)
    if not m:
        return body
    return body[:m.start(2)] + definition + body[m.end(2):]


_ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}


def _extract_matching_claims(
    compiled_payload: dict | None,
    concept_name: str,
    source_slug: str,
) -> tuple[str, list[str]]:
    """Extract claims relevant to a concept from compiled_payload.claim_inventory.

    Returns (best_judgment, evidence_chain_entries).
    """
    if not compiled_payload or compiled_payload.get("schema_version") != "2.0":
        return "", []
    result = compiled_payload.get("result", {})
    if not isinstance(result, dict):
        return "", []
    claim_inventory = result.get("claim_inventory", [])
    if not isinstance(claim_inventory, list):
        return "", []

    name_lower = concept_name.lower()
    matching: list[dict] = []
    for claim in claim_inventory:
        if not isinstance(claim, dict):
            continue
        claim_text = str(claim.get("claim", ""))
        if not claim_text:
            continue
        # Match if concept name appears in claim text or suggested_destination
        name_in_claim = name_lower in claim_text.lower()
        dest_match = False
        for dest in (claim.get("suggested_destination") or []):
            if isinstance(dest, str) and (name_lower in dest.lower() or concept_name in dest):
                dest_match = True
                break
        if not name_in_claim and not dest_match:
            continue
        matching.append(claim)

    if not matching:
        return "", []

    # Format evidence chain entries
    entries = []
    for claim in matching:
        etype = str(claim.get("evidence_type", "inference")).strip()
        conf = str(claim.get("confidence", "Working")).strip()
        text = str(claim.get("claim", "")).strip()
        entries.append(f"- [{etype}|{conf}] {text} —— [[sources/{source_slug}]]")

    # Best judgment: highest-confidence Working+ claim
    best = ""
    best_rank = -1
    for claim in matching:
        conf = str(claim.get("confidence", "")).strip()
        rank = _ORDINAL_RANK.get(conf, -1)
        if rank > best_rank and rank >= 2:  # Working or above
            best_rank = rank
            best = str(claim.get("claim", "")).strip()

    return best, entries


def _fill_placeholder_judgment(body: str, judgment: str) -> str:
    """Fill the 当前判断 section only if it's still placeholder."""
    if not judgment:
        return body
    pattern = r'(##\s+当前判断\s*\n\n)(-?\s*待[^\n]*)'
    m = re.search(pattern, body)
    if not m:
        return body
    return body[:m.start(2)] + judgment + body[m.end(2):]


def _append_evidence_chain(body: str, new_entries: list[str]) -> str:
    """Append new evidence chain entries after existing ones. Also fills placeholder."""
    if not new_entries:
        return body
    # Check if 证据链 section exists at all
    section_match = re.search(r'(##\s+证据链\s*\n)', body)
    if not section_match:
        # Old-format page without 证据链 section; insert before 来自来源
        insert_match = re.search(r'(##\s+来自来源\s*\n)', body)
        if insert_match:
            header = "## 证据链\n\n" + "\n".join(new_entries) + "\n\n"
            return body[:insert_match.start()] + header + body[insert_match.start():]
        return body

    # Replace placeholder if present
    placeholder_match = re.search(
        r'(##\s+证据链\s*\n\n)(-?\s*待[^\n]*)',
        body,
    )
    if placeholder_match:
        replacement = "\n".join(new_entries)
        return body[:placeholder_match.start(2)] + replacement + body[placeholder_match.end(2):]

    # Append after last existing evidence entry (before next ## or end)
    section_start = section_match.end()
    # Find the next ## after the 证据链 section
    next_section = re.search(r'\n##\s+', body[section_start:])
    if next_section:
        insert_pos = section_start + next_section.start()
        entry_text = "\n".join(new_entries) + "\n"
        return body[:insert_pos] + entry_text + body[insert_pos:]
    else:
        return body + "\n" + "\n".join(new_entries) + "\n"


def _upgrade_judgment_if_higher(body: str, new_judgment: str, new_confidence: str) -> str:
    """Update 当前判断 if new claim has higher confidence than existing one."""
    if not new_judgment:
        return body
    new_rank = _ORDINAL_RANK.get(new_confidence, -1)
    if new_rank < 2:  # Only Working+ upgrades existing
        return body
    # Extract current judgment confidence from body
    m = re.search(r'##\s+当前判断\s*\n\n(.+?)(?=\n##|\Z)', body, re.S)
    if not m:
        return _fill_placeholder_judgment(body, new_judgment)
    current_text = m.group(1).strip()
    if current_text.startswith("- 待") or "待随着更多来源持续演化" in current_text:
        return _fill_placeholder_judgment(body, new_judgment)
    # Don't overwrite existing judgment — only fill placeholder
    return body


def _append_cross_domain_insights(body: str, insights: list[dict], source_slug: str) -> str:
    """Append cross-domain insights to a concept page's 跨域联想 section."""
    if not insights:
        return body
    # Build insight lines
    entries = []
    for insight in insights[:5]:
        concept = insight.get("mapped_concept", "")
        target = insight.get("target_domain", "")
        logic = insight.get("bridge_logic", "")
        mc = insight.get("migration_conclusion", "")
        mc_suffix = f" → **可迁移结论**：{mc}" if mc else ""
        entries.append(f"- **{concept}** → {target}：{logic}{mc_suffix}")

    # Check if 跨域联想 section exists
    section_match = re.search(r'(##\s+跨域联想\s*\n)', body)
    if not section_match:
        # Insert before 来自来源
        insert_match = re.search(r'(##\s+来自来源\s*\n)', body)
        if insert_match:
            header = "## 跨域联想\n\n" + "\n".join(entries) + "\n\n"
            return body[:insert_match.start()] + header + body[insert_match.start():]
        return body

    # Replace placeholder if present
    placeholder_match = re.search(r'(##\s+跨域联想\s*\n\n)(-?\s*待[^\n]*)', body)
    if placeholder_match:
        replacement = "\n".join(entries)
        return body[:placeholder_match.start(2)] + replacement + body[placeholder_match.end(2):]

    # Append after existing entries
    section_start = section_match.end()
    next_section = re.search(r'\n##\s+', body[section_start:])
    if next_section:
        insert_pos = section_start + next_section.start()
        entry_text = "\n".join(entries) + "\n"
        return body[:insert_pos] + entry_text + body[insert_pos:]
    else:
        return body + "\n" + "\n".join(entries) + "\n"


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
    lifecycle = meta.get("lifecycle", "official")
    if current in ("draft",):
        current = "seed"
    if current not in VALID_PAGE_STATUS or current == "evergreen":
        return
    # Candidate lifecycle upgrade: 2+ high-confidence source mentions -> official + seed
    if lifecycle == "candidate" and current == "candidate":
        ref_count = page_mention_count(vault, "sources", name)
        if ref_count >= STATUS_UPGRADE_THRESHOLDS.get("candidate", 2):
            meta["lifecycle"] = "official"
            meta["status"] = "seed"
            path.write_text(render_frontmatter(meta) + body, encoding="utf-8")
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
    source_lifecycle: str = "official",
) -> None:
    from .compile import promoted_taxonomy_items_from_payload, promoted_taxonomy_names_from_payload, taxonomy_items_from_payload

    # Use LLM-provided taxonomy items with full metadata (including definitions)
    # Include both promote_to_official_candidate AND create_candidate items
    concept_items = taxonomy_items_from_payload(compiled_payload, "concepts", include_candidates=True)
    entity_items = taxonomy_items_from_payload(compiled_payload, "entities", include_candidates=True)
    concept_names = [item["name"] for item in concept_items if isinstance(item.get("name"), str)]
    entity_names = [item["name"] for item in entity_items if isinstance(item.get("name"), str)]
    # Build name→definition lookup
    concept_defs = {item["name"]: (item.get("definition", "") or "") for item in concept_items if isinstance(item.get("name"), str)}
    entity_defs = {item["name"]: (item.get("definition", "") or "") for item in entity_items if isinstance(item.get("name"), str)}
    # Build name→is_candidate lookup
    concept_candidates = {item["name"]: item.get("is_candidate", False) for item in concept_items if isinstance(item.get("name"), str)}
    entity_candidates = {item["name"]: item.get("is_candidate", False) for item in entity_items if isinstance(item.get("name"), str)}
    # Build cross-category links
    entity_links_for_concepts = [f"[[entities/{entity_slug(n)}]]" for n in entity_names]
    concept_links_for_entities = [f"[[concepts/{concept_slug(n)}]]" for n in concept_names]
    concept_links_for_domains = [f"[[concepts/{concept_slug(n)}]]" for n in concept_names]
    entity_links_for_domains = [f"[[entities/{entity_slug(n)}]]" for n in entity_names]
    domain_names = [name for name in (domains_override or []) if isinstance(name, str) and name.strip()]
    domain_links = [f"[[domains/{domain_slug(name)}]]" for name in domain_names]
    # Build domain definitions from knowledge_proposals.domains
    domain_defs: dict[str, str] = {}
    if isinstance(compiled_payload, dict) and compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result", {}) if isinstance(compiled_payload.get("result"), dict) else {}
        kp = result.get("knowledge_proposals", {}) if isinstance(result.get("knowledge_proposals"), dict) else {}
        domain_proposals = kp.get("domains", []) if isinstance(kp.get("domains"), list) else []
        for item in domain_proposals:
            if not isinstance(item, dict): continue
            dname = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
            reason = item.get("reason", "").strip() if isinstance(item.get("reason"), str) else ""
            if dname and reason:
                domain_defs[dname] = reason

    # Extract matching claims for each concept/entity from claim_inventory
    concept_judgments: dict[str, str] = {}
    concept_evidence: dict[str, list[str]] = {}
    concept_confidence: dict[str, str] = {}
    entity_judgments: dict[str, str] = {}
    entity_evidence: dict[str, list[str]] = {}
    entity_confidence: dict[str, str] = {}
    for name in concept_names:
        best, entries = _extract_matching_claims(compiled_payload, name, source_slug)
        concept_judgments[name] = best
        concept_evidence[name] = entries
        # Extract confidence of the best judgment
        if best and compiled_payload and compiled_payload.get("schema_version") == "2.0":
            result = compiled_payload.get("result", {})
            claim_inventory = result.get("claim_inventory", [])
            for claim in claim_inventory:
                if isinstance(claim, dict) and str(claim.get("claim", "")).strip() == best:
                    concept_confidence[name] = str(claim.get("confidence", "Working")).strip()
                    break
    for name in entity_names:
        best, entries = _extract_matching_claims(compiled_payload, name, source_slug)
        entity_judgments[name] = best
        entity_evidence[name] = entries
        if best and compiled_payload and compiled_payload.get("schema_version") == "2.0":
            result = compiled_payload.get("result", {})
            claim_inventory = result.get("claim_inventory", [])
            for claim in claim_inventory:
                if isinstance(claim, dict) and str(claim.get("claim", "")).strip() == best:
                    entity_confidence[name] = str(claim.get("confidence", "Working")).strip()
                    break

    # Extract cross-domain insights matching each concept
    concept_cross_domain: dict[str, list[dict]] = {}
    cross_domain_insights = []
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        result = compiled_payload.get("result", {})
        cross_domain_insights = result.get("cross_domain_insights", []) if isinstance(result, dict) else []
    for name in concept_names:
        name_lower = name.lower()
        matching_insights = []
        for insight in cross_domain_insights:
            if not isinstance(insight, dict):
                continue
            mc = insight.get("mapped_concept", "")
            if name_lower in str(mc).lower() or str(mc).lower() in name_lower:
                matching_insights.append(insight)
        concept_cross_domain[name] = matching_insights

    for name in concept_names:
        path = vault / "wiki" / "concepts" / f"{concept_slug(name)}.md"
        is_candidate = concept_candidates.get(name, False)
        item_lifecycle = "candidate" if (is_candidate or source_lifecycle == "candidate") else "official"
        if not path.exists():
            page_text = build_concept_page(
                name, source_slug, domains=domain_names,
                definition=concept_defs.get(name, ""),
                related_entities=entity_names,
                current_judgment=concept_judgments.get(name, ""),
                evidence_chain=concept_evidence.get(name, []),
                cross_domain_insights=concept_cross_domain.get(name, []),
            )
            if item_lifecycle == "candidate":
                page_text = page_text.replace('lifecycle: "official"', 'lifecycle: "candidate"').replace('status: "seed"', 'status: "candidate"')
            path.write_text(page_text, encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if item_lifecycle == "candidate" and meta.get("lifecycle", "official") == "official":
            meta["lifecycle"] = "candidate"
            meta["status"] = "candidate"
        updated = merge_links_section(body, "来自来源", [f"[[sources/{source_slug}]]"], "- 待补充。")
        updated = replace_links_section(updated, "相关主题域", domain_links, "- 待补充。")
        updated = replace_links_section(updated, "相关实体", entity_links_for_concepts, "- 待补充。")
        updated = _fill_placeholder_definition(updated, "定义", concept_defs.get(name, ""))
        updated = _fill_placeholder_judgment(updated, concept_judgments.get(name, ""))
        updated = _upgrade_judgment_if_higher(updated, concept_judgments.get(name, ""), concept_confidence.get(name, ""))
        updated = _append_evidence_chain(updated, concept_evidence.get(name, []))
        # Append cross-domain insights
        insights = concept_cross_domain.get(name, [])
        if insights:
            updated = _append_cross_domain_insights(updated, insights, source_slug)
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")
        check_and_upgrade_status(vault, "concepts", name, concept_slug)

    for name in entity_names:
        path = vault / "wiki" / "entities" / f"{entity_slug(name)}.md"
        is_candidate = entity_candidates.get(name, False)
        item_lifecycle = "candidate" if (is_candidate or source_lifecycle == "candidate") else "official"
        if not path.exists():
            page_text = build_entity_page(
                name, source_slug, domains=domain_names,
                definition=entity_defs.get(name, ""),
                related_concepts=concept_names,
                current_judgment=entity_judgments.get(name, ""),
                evidence_chain=entity_evidence.get(name, []),
            )
            if item_lifecycle == "candidate":
                page_text = page_text.replace('lifecycle: "official"', 'lifecycle: "candidate"').replace('status: "seed"', 'status: "candidate"')
            path.write_text(page_text, encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if item_lifecycle == "candidate" and meta.get("lifecycle", "official") == "official":
            meta["lifecycle"] = "candidate"
            meta["status"] = "candidate"
        updated = merge_links_section(body, "来自来源", [f"[[sources/{source_slug}]]"], "- 待补充。")
        updated = replace_links_section(updated, "相关主题域", domain_links, "- 待补充。")
        updated = replace_links_section(updated, "相关概念", concept_links_for_entities, "- 待补充。")
        updated = _fill_placeholder_definition(updated, "类型", entity_defs.get(name, ""))
        updated = _fill_placeholder_judgment(updated, entity_judgments.get(name, ""))
        updated = _upgrade_judgment_if_higher(updated, entity_judgments.get(name, ""), entity_confidence.get(name, ""))
        updated = _append_evidence_chain(updated, entity_evidence.get(name, []))
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")
        check_and_upgrade_status(vault, "entities", name, entity_slug)

    for name in domain_names:
        path = vault / "wiki" / "domains" / f"{domain_slug(name)}.md"
        if not path.exists():
            path.write_text(
                build_domain_page(
                    name, source_slug,
                    definition=domain_defs.get(name, ""),
                    concept_names=concept_names,
                    entity_names=entity_names,
                ),
                encoding="utf-8",
            )
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
        updated = replace_links_section(updated, "关键概念", concept_links_for_domains, "- 待补充。")
        updated = replace_links_section(updated, "相关实体", entity_links_for_domains, "- 待补充。")
        # Fill overview if still placeholder
        overview_section = re.search(r'(## 概览\s*\n\n)(.+?)(?=\n## |\Z)', updated, re.S)
        if overview_section and '待随着更多来源持续演化' in overview_section.group(2) and domain_defs.get(name):
            before = updated[:overview_section.start()]
            after = updated[overview_section.end():]
            updated = before + f"## 概览\n\n{domain_defs[name]}\n" + after
        path.write_text(render_frontmatter(meta) + updated.strip() + "\n", encoding="utf-8")
        check_and_upgrade_status(vault, "domains", name, domain_slug)


def ensure_synthesis_pages(
    vault: Path,
    article: Article,
    source_slug: str,
    domains_override: list[str] | None = None,
) -> None:
    domain_names = [name for name in (domains_override or []) if isinstance(name, str) and name.strip()]
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
