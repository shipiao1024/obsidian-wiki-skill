#!/usr/bin/env python
"""Build and maintain the semantic index for the Obsidian wiki.

Three-stage architecture:
  --rebuild   : Scan wiki/ and build semantic-index.json (mechanical)
  --query     : Query the index for a concept or domain (mechanical)

The semantic index is a structured JSON that enables smart retrieval
without requiring LLM to scan the entire vault.

Usage:
  python scripts/wiki_index_v2.py --vault "D:\Vault" --rebuild
  python scripts/wiki_index_v2.py --vault "D:\Vault" --query "BEV感知"
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from pipeline.shared import resolve_vault
from pipeline.text_utils import parse_frontmatter, section_excerpt, section_body, plain_text, CLAIM_PATTERN
from pipeline.encoding_fix import fix_windows_encoding


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and query the semantic index.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild semantic-index.json from wiki/ pages.")
    parser.add_argument("--query", type=str, help="Query the index for a concept or domain.")
    parser.add_argument("--output", type=Path, help="Output path for --rebuild or --query JSON.")
    return parser.parse_args()


def _extract_claims_from_page(path: Path, meta: dict[str, str], body: str) -> list[dict[str, str]]:
    """Extract claims from a page's ## 关键判断 section."""
    claims = []
    claim_section = section_body(body, "关键判断")
    if not claim_section:
        return claims

    folder = path.parent.name
    slug = path.stem

    for match in CLAIM_PATTERN.finditer(claim_section):
        etype = match.group(1).strip()
        conf = match.group(2).strip()
        text = match.group(3).strip().rstrip("⚠️需验证").strip()
        if text:
            claims.append({
                "text": text,
                "confidence": conf,
                "evidence_type": etype,
                "source": f"{folder}/{slug}",
                "source_title": meta.get("title", slug).strip('"'),
            })

    # Also extract from plain bullet lines in 关键判断 if CLAIM_PATTERN doesn't match
    if not claims:
        for line in claim_section.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ") and len(stripped) > 10:
                claims.append({
                    "text": stripped[2:].strip(),
                    "confidence": "Unknown",
                    "source": f"{folder}/{slug}",
                    "source_title": meta.get("title", slug).strip('"'),
                })

    return claims


def _extract_domains_from_page(meta: dict[str, str], body: str) -> list[str]:
    """Extract domain names from page links or metadata."""
    domains = []
    # From frontmatter tags
    tags = meta.get("tags", "")
    if tags:
        for tag in re.findall(r'"?([^",]+)"?', str(tags)):
            tag = tag.strip()
            if tag and tag not in ("source", "brief", "concept", "entity"):
                domains.append(tag)

    # From ## 主题域 section links
    domain_section = section_body(body, "主题域")
    if domain_section:
        for match in re.finditer(r"\[\[domains/([^\]|]+)", domain_section):
            domains.append(match.group(1))

    return list(set(domains))


def _extract_related_concepts(body: str) -> list[str]:
    """Extract related concept/entity names from links in body."""
    refs = set()
    for match in re.finditer(r"\[\[(concepts|entities)/([^\]|]+)", body):
        refs.add(match.group(2))
    return sorted(refs)


def _extract_relationships_from_stance(path: Path, body: str) -> list[dict[str, str]]:
    """Extract stance relationships (supports/contradicts) from stance pages."""
    rels = []
    slug = path.stem

    support_section = section_body(body, "支持证据")
    contradict_section = section_body(body, "反对证据（steel-man）")

    if support_section:
        for match in re.finditer(r"\[\[sources/([^\]|]+)", support_section):
            rels.append({
                "from": f"stances/{slug}",
                "to": f"sources/{match.group(1)}",
                "type": "supports",
            })

    if contradict_section:
        for match in re.finditer(r"\[\[sources/([^\]|]+)", contradict_section):
            rels.append({
                "from": f"stances/{slug}",
                "to": f"sources/{match.group(1)}",
                "type": "contradicts",
            })

    return rels


def _extract_synthesis_sources(body: str) -> list[str]:
    """Extract source references from synthesis pages."""
    sources = []
    for match in re.finditer(r"\[\[sources/([^\]|]+)", body):
        sources.append(match.group(1))
    return sources


def _page_confidence(meta: dict[str, str], body: str) -> str:
    """Get the confidence level of a page."""
    conf = meta.get("confidence", "")
    if conf:
        return conf.strip('"')
    # Extract from claim distribution
    conf_dist = {}
    for level in ("Seeded", "Preliminary", "Working", "Supported", "Stable"):
        val = meta.get(f"claim_confidence_{level.lower()}", "0")
        try:
            conf_dist[level] = int(val.strip('"'))
        except ValueError:
            conf_dist[level] = 0
    total = sum(conf_dist.values())
    if total == 0:
        return "Unknown"
    # Return the highest confidence level with > 0 count
    for level in ("Stable", "Supported", "Working", "Preliminary", "Seeded"):
        if conf_dist[level] > 0:
            return level
    return "Unknown"


def build_semantic_index(vault: Path) -> dict:
    """Scan wiki/ and build the complete semantic index."""
    wiki_root = vault / "wiki"
    if not wiki_root.exists():
        return {"error": "wiki/ directory not found", "domains": {}, "concepts": {}, "entities": {}, "claims": [], "relationships": [], "stats": {}}

    # --- Collect all pages ---
    domains_index: dict[str, dict] = {}
    concepts_index: dict[str, dict] = {}
    entities_index: dict[str, dict] = {}
    all_claims: list[dict[str, str]] = []
    all_relationships: list[dict[str, str]] = []
    source_pages: dict[str, dict] = {}

    # Scan sources
    sources_dir = wiki_root / "sources"
    if sources_dir.exists():
        for path in sorted(sources_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            slug = path.stem
            title = meta.get("title", slug).strip('"')
            domains = _extract_domains_from_page(meta, body)
            confidence = _page_confidence(meta, body)
            date = meta.get("date", "").strip('"')
            quality = meta.get("quality", "").strip('"')

            source_pages[slug] = {
                "ref": f"sources/{slug}",
                "title": title,
                "domains": domains,
                "confidence": confidence,
                "date": date,
                "quality": quality,
                "related_concepts": _extract_related_concepts(body),
            }

            # Extract claims
            claims = _extract_claims_from_page(path, meta, body)
            for claim in claims:
                claim["domain"] = domains[0] if domains else "未分类"
            all_claims.extend(claims)

            # Build domain index entries
            for domain in domains:
                if domain not in domains_index:
                    domains_index[domain] = {"sources": [], "concepts": [], "entities": [], "cross_domain_insights_count": 0, "last_updated": date}
                domains_index[domain]["sources"].append(f"sources/{slug}")
                if date and date > domains_index[domain].get("last_updated", ""):
                    domains_index[domain]["last_updated"] = date

    # Scan briefs
    briefs_index: dict[str, dict] = {}
    all_cross_domain_insights: list[dict[str, str]] = []
    briefs_dir = wiki_root / "briefs"
    if briefs_dir.exists():
        for path in sorted(briefs_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            slug = path.stem
            title = meta.get("title", slug).strip('"')
            domains = _extract_domains_from_page(meta, body)
            confidence = _page_confidence(meta, body)
            one_sentence = meta.get("one_sentence", "").strip('"')

            # Extract skeleton excerpt (first 200 chars of 骨架 section)
            skeleton_excerpt = ""
            skeleton_section = section_body(body, "骨架")
            if skeleton_section:
                skeleton_excerpt = plain_text(skeleton_section)[:200]

            # Extract claims from brief
            brief_claims = _extract_claims_from_page(path, meta, body)

            # Extract cross-domain insights from ## 跨域联想
            cross_domain_section = section_body(body, "跨域联想")
            if cross_domain_section:
                for line in cross_domain_section.splitlines():
                    stripped = line.strip()
                    if not stripped.startswith("- "):
                        continue
                    entry_text = stripped[2:].strip()
                    # Parse: **concept** → domain: bridge_logic → **可迁移结论**：conclusion
                    concept_match = re.match(r'\*\*(.+?)\*\*\s*[→->]+\s*(.+?)(?:\s*[→->]+\s*(.+))?$', entry_text)
                    if concept_match:
                        mapped_concept = concept_match.group(1).strip()
                        rest = concept_match.group(2).strip()
                        # Split domain and bridge_logic
                        if ':' in rest:
                            target_domain, bridge_logic = rest.split(':', 1)
                            target_domain = target_domain.strip()
                            bridge_logic = bridge_logic.strip()
                        else:
                            target_domain = rest
                            bridge_logic = ""
                        migration_conclusion = ""
                        if concept_match.group(3):
                            mc = concept_match.group(3).strip()
                            mc = re.sub(r'^\*\*可迁移结论\*\*[：:]\s*', '', mc)
                            migration_conclusion = mc.strip()
                        all_cross_domain_insights.append({
                            "mapped_concept": mapped_concept,
                            "target_domain": target_domain,
                            "bridge_logic": bridge_logic,
                            "migration_conclusion": migration_conclusion,
                            "source": f"briefs/{slug}",
                        })

            briefs_index[slug] = {
                "ref": f"briefs/{slug}",
                "title": title,
                "domains": domains,
                "confidence": confidence,
                "one_sentence": one_sentence,
                "skeleton_excerpt": skeleton_excerpt,
                "claims": brief_claims,
                "related_concepts": _extract_related_concepts(body),
            }

            # Briefs also contribute to domain index
            for domain in domains:
                if domain not in domains_index:
                    domains_index[domain] = {"sources": [], "concepts": [], "entities": [], "cross_domain_insights_count": 0, "last_updated": ""}
                if f"briefs/{slug}" not in domains_index[domain]["sources"]:
                    domains_index[domain]["sources"].append(f"briefs/{slug}")

    # Scan concepts
    concepts_dir = wiki_root / "concepts"
    if concepts_dir.exists():
        for path in sorted(concepts_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            slug = path.stem
            title = meta.get("title", slug).strip('"')
            status = meta.get("status", "seed").strip('"')
            confidence = _page_confidence(meta, body)
            domains = _extract_domains_from_page(meta, body)
            related = _extract_related_concepts(body)

            # Extract source references
            source_refs = []
            source_section = section_body(body, "来自来源")
            if source_section:
                for match in re.finditer(r"\[\[sources/([^\]|]+)", source_section):
                    source_refs.append(match.group(1))

            concepts_index[slug] = {
                "ref": f"concepts/{slug}",
                "title": title,
                "status": status,
                "confidence": confidence,
                "domains": domains,
                "sources": [f"sources/{s}" for s in source_refs],
                "related_concepts": related,
                "current_judgment": section_body(body, "当前判断") or "",
                "evidence_chain": section_body(body, "证据链") or "",
            }

            for domain in domains:
                if domain not in domains_index:
                    domains_index[domain] = {"sources": [], "concepts": [], "entities": [], "cross_domain_insights_count": 0, "last_updated": ""}
                domains_index[domain]["concepts"].append(f"concepts/{slug}")

    # Scan entities
    entities_dir = wiki_root / "entities"
    if entities_dir.exists():
        for path in sorted(entities_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            slug = path.stem
            title = meta.get("title", slug).strip('"')
            status = meta.get("status", "seed").strip('"')
            confidence = _page_confidence(meta, body)
            domains = _extract_domains_from_page(meta, body)
            related = _extract_related_concepts(body)

            source_refs = []
            source_section = section_body(body, "来自来源")
            if source_section:
                for match in re.finditer(r"\[\[sources/([^\]|]+)", source_section):
                    source_refs.append(match.group(1))

            entities_index[slug] = {
                "ref": f"entities/{slug}",
                "title": title,
                "status": status,
                "confidence": confidence,
                "domains": domains,
                "sources": [f"sources/{s}" for s in source_refs],
                "related_concepts": related,
            }

            for domain in domains:
                if domain not in domains_index:
                    domains_index[domain] = {"sources": [], "concepts": [], "entities": [], "cross_domain_insights_count": 0, "last_updated": ""}
                domains_index[domain]["entities"].append(f"entities/{slug}")

    # Scan stances
    stances_index: dict[str, dict] = {}
    stances_dir = wiki_root / "stances"
    if stances_dir.exists():
        for path in sorted(stances_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            slug = path.stem
            title = meta.get("title", slug).strip('"')
            status = meta.get("status", "active").strip('"')
            confidence = meta.get("confidence", "Working").strip('"')
            source_count = meta.get("source_count", "0").strip('"')
            # Extract core judgment excerpt
            core_judgment = section_body(body, "核心判断") or ""
            core_judgment_excerpt = plain_text(core_judgment)[:300] if core_judgment else ""

            # Count supporting and contradicting evidence
            support_section = section_body(body, "支持证据")
            contradict_section = section_body(body, "反对证据（steel-man）")
            support_count = len(re.findall(r'\[\[sources/', support_section)) if support_section else 0
            contradict_count = len(re.findall(r'\[\[sources/', contradict_section)) if contradict_section else 0

            stances_index[slug] = {
                "ref": f"stances/{slug}",
                "title": title,
                "status": status,
                "confidence": confidence,
                "core_judgment_excerpt": core_judgment_excerpt,
                "source_count": int(source_count) if source_count.isdigit() else 0,
                "support_count": support_count,
                "contradict_count": contradict_count,
            }

            rels = _extract_relationships_from_stance(path, body)
            all_relationships.extend(rels)

    # Scan syntheses for source relationships
    syntheses_dir = wiki_root / "syntheses"
    if syntheses_dir.exists():
        for path in sorted(syntheses_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            _, body = parse_frontmatter(text)
            slug = path.stem
            source_slugs = _extract_synthesis_sources(body)
            for s in source_slugs:
                all_relationships.append({
                    "from": f"syntheses/{slug}",
                    "to": f"sources/{s}",
                    "type": "synthesizes",
                })

    # Scan questions for answer relationships
    questions_dir = wiki_root / "questions"
    if questions_dir.exists():
        for path in sorted(questions_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            _, body = parse_frontmatter(text)
            slug = path.stem
            for match in re.finditer(r"\[\[sources/([^\]|]+)", body):
                all_relationships.append({
                    "from": f"sources/{match.group(1)}",
                    "to": f"questions/{slug}",
                    "type": "answers",
                })

    # Build stats
    stats = {
        "total_sources": len(source_pages),
        "total_concepts": len(concepts_index),
        "total_entities": len(entities_index),
        "total_domains": len(domains_index),
        "total_claims": len(all_claims),
        "total_relationships": len(all_relationships),
        "total_briefs": len(briefs_index),
        "total_stances": len(stances_index),
        "total_cross_domain_insights": len(all_cross_domain_insights),
        "built_at": datetime.now().isoformat(),
    }

    # Populate cross_domain_insights_count per domain
    for insight in all_cross_domain_insights:
        target = insight.get("target_domain", "")
        if target and target in domains_index:
            domains_index[target]["cross_domain_insights_count"] = domains_index[target].get("cross_domain_insights_count", 0) + 1

    return {
        "domains": domains_index,
        "concepts": concepts_index,
        "entities": entities_index,
        "claims": all_claims,
        "relationships": all_relationships,
        "sources": source_pages,
        "briefs": briefs_index,
        "stances": stances_index,
        "cross_domain_insights": all_cross_domain_insights,
        "stats": stats,
    }


def query_index(index: dict, query: str) -> dict:
    """Query the semantic index for a concept or domain name."""
    query_lower = query.lower().strip()
    results = {
        "query": query,
        "matched_domains": [],
        "matched_concepts": [],
        "matched_entities": [],
        "matched_claims": [],
        "related_sources": [],
    }

    # Match domains
    for domain_name, domain_data in index.get("domains", {}).items():
        if query_lower in domain_name.lower():
            results["matched_domains"].append({
                "name": domain_name,
                **domain_data,
            })

    # Match concepts
    for concept_name, concept_data in index.get("concepts", {}).items():
        title = concept_data.get("title", concept_name).lower()
        if query_lower in concept_name.lower() or query_lower in title:
            results["matched_concepts"].append({
                "name": concept_name,
                **concept_data,
            })

    # Match entities
    for entity_name, entity_data in index.get("entities", {}).items():
        title = entity_data.get("title", entity_name).lower()
        if query_lower in entity_name.lower() or query_lower in title:
            results["matched_entities"].append({
                "name": entity_name,
                **entity_data,
            })

    # Match claims
    for claim in index.get("claims", []):
        if query_lower in claim.get("text", "").lower():
            results["matched_claims"].append(claim)

    # Collect related sources from matched concepts/entities
    source_refs = set()
    for c in results["matched_concepts"]:
        for s in c.get("sources", []):
            source_refs.add(s)
    for e in results["matched_entities"]:
        for s in e.get("sources", []):
            source_refs.add(s)
    for d in results["matched_domains"]:
        for s in d.get("sources", []):
            source_refs.add(s)

    # Add source metadata
    sources_data = index.get("sources", {})
    for ref in sorted(source_refs):
        slug = ref.split("/", 1)[1] if "/" in ref else ref
        if slug in sources_data:
            results["related_sources"].append(sources_data[slug])
        else:
            results["related_sources"].append({"ref": ref, "title": slug})

    return results


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    if args.rebuild:
        index = build_semantic_index(vault)
        output = json.dumps(index, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Semantic index written to {args.output}")
        else:
            default_path = vault / "wiki" / "semantic-index.json"
            default_path.write_text(output, encoding="utf-8")
            print(f"Semantic index written to {default_path}")
            print(json.dumps(index["stats"], ensure_ascii=False, indent=2))
        return 0

    if args.query:
        index_path = vault / "wiki" / "semantic-index.json"
        if not index_path.exists():
            print("Error: semantic-index.json not found. Run --rebuild first.")
            return 1
        index = json.loads(index_path.read_text(encoding="utf-8"))
        results = query_index(index, args.query)
        output = json.dumps(results, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output)
        return 0

    # Default: show stats
    index_path = vault / "wiki" / "semantic-index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        print(json.dumps(index.get("stats", {}), ensure_ascii=False, indent=2))
    else:
        print("No semantic-index.json found. Run --rebuild to create one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
