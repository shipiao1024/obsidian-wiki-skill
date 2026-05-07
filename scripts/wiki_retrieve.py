#!/usr/bin/env python
"""Smart retrieval using the semantic index.

Replaces LLM-driven grep search with structured, ranked retrieval.
Reads semantic-index.json, scores pages by relevance, extracts key
sections, and outputs a structured context package for the LLM.

Usage:
  python scripts/wiki_retrieve.py --vault "D:\Vault" --query "BEV感知的局限性"
  python scripts/wiki_retrieve.py --vault "D:\Vault" --query "端到端" --top-k 8
  python scripts/wiki_retrieve.py --vault "D:\Vault" --query "对比" --types source,concept

Design:
  1. Parse query → extract core terms
  2. Search semantic index → match domains, concepts, entities, claims
  3. Score + rank → combine title match, claim match, domain match, status, recency
  4. Read top-k pages → extract key sections (claims, summary, evidence)
  5. Output structured context package (JSON)
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from pipeline.shared import resolve_vault
from pipeline.encoding_fix import fix_windows_encoding
from pipeline.text_utils import (
    parse_frontmatter,
    plain_text,
    section_body,
    section_excerpt,
    get_one_sentence,
    CLAIM_PATTERN,
)


# ---------------------------------------------------------------------------
# Term extraction
# ---------------------------------------------------------------------------

STOPWORDS = {
    "什么", "怎么", "如何", "这个", "这篇", "文章", "一下", "一个",
    "是否", "以及", "关于", "的", "了", "和", "与", "或", "在",
    "是", "有", "对", "从", "到", "等", "也", "就", "都", "而",
    "但", "如果", "因为", "所以", "可以", "需要", "比较", "分析",
    "总结", "梳理", "介绍", "说明", "解释", "哪些", "哪个",
}


def extract_terms(query: str) -> list[str]:
    """Extract meaningful search terms from a natural-language query."""
    # Split on Chinese and English boundaries
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-_.+]{1,}|[一-鿿]{2,8}", query)
    terms: list[str] = []
    for t in raw:
        t = t.strip()
        if t.lower() in STOPWORDS or t in STOPWORDS:
            continue
        if len(t) < 2:
            continue
        if t not in terms:
            terms.append(t)
    return terms or [query.strip()]


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

FOLDER_BASE_WEIGHT = {
    "briefs": 8,
    "sources": 6,
    "concepts": 5,
    "stances": 4,
    "syntheses": 4,
    "domains": 3,
    "comparisons": 3,
    "entities": 3,
    "questions": 2,
    "outputs": -10,
}

STATUS_BOOST = {
    "evergreen": 4,
    "mature": 3,
    "developing": 1,
    "seed": 0,
}

CONFIDENCE_BOOST = {
    "Stable": 4,
    "Supported": 3,
    "Working": 2,
    "Preliminary": 1,
    "Seeded": 0,
}


def _term_overlap(text: str, terms: list[str]) -> int:
    """Count how many distinct terms appear in text."""
    text_lower = text.lower()
    return sum(1 for t in terms if t.lower() in text_lower)


def _term_frequency(text: str, terms: list[str]) -> int:
    """Sum of occurrence counts for each term in text."""
    text_lower = text.lower()
    return sum(text_lower.count(t.lower()) for t in terms)


def score_page(
    page_data: dict,
    folder: str,
    terms: list[str],
    matched_domain_slugs: set[str],
    matched_concept_slugs: set[str],
    matched_entity_slugs: set[str],
) -> float:
    """Compute relevance score for a page from the semantic index."""
    score = 0.0

    title = page_data.get("title", "")
    slug = page_data.get("ref", "").split("/", 1)[-1] if "/" in page_data.get("ref", "") else ""

    # Title/slug match (highest signal)
    score += _term_overlap(title, terms) * 8
    score += _term_overlap(slug, terms) * 6

    # Claim text match
    for claim in page_data.get("claims", []):
        claim_text = claim.get("text", "")
        score += _term_overlap(claim_text, terms) * 3
        score += _term_frequency(claim_text, terms) * 1

    # Domain match boost
    page_domains = set(page_data.get("domains", []))
    domain_overlap = page_domains & matched_domain_slugs
    score += len(domain_overlap) * 4

    # Related concept match boost
    related = set(page_data.get("related_concepts", []))
    concept_overlap = related & (matched_concept_slugs | matched_entity_slugs)
    score += len(concept_overlap) * 3

    # Folder base weight
    score += FOLDER_BASE_WEIGHT.get(folder, 0)

    # Status boost
    status = page_data.get("status", page_data.get("confidence", ""))
    score += STATUS_BOOST.get(status, 0)
    score += CONFIDENCE_BOOST.get(status, 0)

    # Recency boost (sources with dates)
    date_str = page_data.get("date", "")
    if date_str:
        try:
            days_ago = (datetime.now() - datetime.fromisoformat(date_str)).days
            if days_ago < 30:
                score += 3
            elif days_ago < 90:
                score += 2
            elif days_ago < 180:
                score += 1
        except (ValueError, TypeError):
            pass

    return score


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve(
    index: dict,
    query: str,
    top_k: int = 5,
    type_filter: list[str] | None = None,
) -> dict:
    """Main retrieval: search index, score, rank, return structured results."""
    terms = extract_terms(query)

    # --- Phase 1: Find matching domains, concepts, entities in index ---
    matched_domain_slugs: set[str] = set()
    matched_domains: list[dict] = []
    for domain_name, domain_data in index.get("domains", {}).items():
        if _term_overlap(domain_name, terms) > 0:
            matched_domain_slugs.add(domain_name)
            matched_domains.append({"name": domain_name, **domain_data})

    matched_concept_slugs: set[str] = set()
    matched_entity_slugs: set[str] = set()

    # --- Phase 2: Score all pages ---
    scored_pages: list[dict] = []

    for folder_key in ("briefs", "sources", "concepts", "entities", "domains", "syntheses", "comparisons", "stances", "questions"):
        if type_filter and folder_key not in type_filter:
            continue
        pages = index.get(folder_key, {})
        for slug, page_data in pages.items():
            # Track matched concepts/entities
            if folder_key == "concepts":
                title = page_data.get("title", slug)
                if _term_overlap(title, terms) > 0 or _term_overlap(slug, terms) > 0:
                    matched_concept_slugs.add(slug)
            elif folder_key == "entities":
                title = page_data.get("title", slug)
                if _term_overlap(title, terms) > 0 or _term_overlap(slug, terms) > 0:
                    matched_entity_slugs.add(slug)

    # Re-score with updated matched sets
    for folder_key in ("briefs", "sources", "concepts", "entities", "domains", "syntheses", "comparisons", "stances", "questions"):
        if type_filter and folder_key not in type_filter:
            continue
        pages = index.get(folder_key, {})
        for slug, page_data in pages.items():
            s = score_page(
                page_data, folder_key, terms,
                matched_domain_slugs, matched_concept_slugs, matched_entity_slugs,
            )
            if s > 0:
                scored_pages.append({
                    "ref": page_data.get("ref", f"{folder_key}/{slug}"),
                    "title": page_data.get("title", slug),
                    "folder": folder_key,
                    "score": s,
                    "domains": page_data.get("domains", []),
                    "status": page_data.get("status", ""),
                    "confidence": page_data.get("confidence", ""),
                    "date": page_data.get("date", ""),
                    "related_concepts": page_data.get("related_concepts", []),
                })

    scored_pages.sort(key=lambda x: x["score"], reverse=True)
    top_pages = scored_pages[:top_k]

    # --- Phase 3: Collect claims from matched pages ---
    top_claims: list[dict] = []
    all_claims = index.get("claims", [])
    top_refs = {p["ref"] for p in top_pages}
    for claim in all_claims:
        if claim.get("source") in top_refs:
            top_claims.append(claim)
        elif _term_overlap(claim.get("text", ""), terms) > 0:
            top_claims.append(claim)
    # Deduplicate and limit
    seen_claims: set[str] = set()
    unique_claims: list[dict] = []
    for c in top_claims:
        key = c["text"][:80]
        if key not in seen_claims:
            seen_claims.add(key)
            unique_claims.append(c)
    top_claims = unique_claims[:20]

    # --- Phase 4: Collect related relationships ---
    top_rels: list[dict] = []
    all_rels = index.get("relationships", [])
    for rel in all_rels:
        if rel.get("from") in top_refs or rel.get("to") in top_refs:
            top_rels.append(rel)

    # --- Phase 5: Build navigation hints (cognitive context for LLM reference) ---
    # These are prior judgments saved at ingest time, NOT system conclusions.
    # LLM should read, evaluate, and decide whether to adopt, revise, or override.
    cognitive_context: dict[str, list[dict]] = {
        "concept_judgments": [],    # Prior ingest-time judgments — for LLM reference, not automatic citation
        "stance_positions": [],     # Accumulated stance positions — for LLM awareness, not binding conclusions
        "cross_domain_insights": [], # Cross-domain connections — for LLM exploration, not proven facts
    }
    for slug in matched_concept_slugs:
        concept_data = index.get("concepts", {}).get(slug, {})
        judgment = concept_data.get("current_judgment", "")
        if judgment and not judgment.startswith("- 待"):
            cognitive_context["concept_judgments"].append({
                "concept": slug,
                "title": concept_data.get("title", slug),
                "prior_judgment": judgment[:300],  # "prior" signals this is a previous LLM judgment, not a script conclusion
                "confidence": concept_data.get("confidence", ""),
                "sources": concept_data.get("sources", []),
                "note": "prior ingest-time judgment — LLM should evaluate before adopting",
            })
    for slug, stance_data in index.get("stances", {}).items():
        if _term_overlap(stance_data.get("title", slug), terms) > 0 or _term_overlap(slug, terms) > 0:
            cognitive_context["stance_positions"].append({
                "topic": stance_data.get("title", slug),
                "confidence": stance_data.get("confidence", ""),
                "status": stance_data.get("status", ""),
                "prior_judgment": stance_data.get("core_judgment_excerpt", ""),  # "prior" signals accumulated position
                "source_count": stance_data.get("source_count", 0),
                "support_count": stance_data.get("support_count", 0),
                "contradict_count": stance_data.get("contradict_count", 0),
                "note": "accumulated stance — LLM should verify against current evidence",
            })
    for insight in index.get("cross_domain_insights", []):
        if _term_overlap(insight.get("mapped_concept", ""), terms) > 0 or _term_overlap(insight.get("target_domain", ""), terms) > 0:
            cognitive_context["cross_domain_insights"].append(insight)

    return {
        "query": query,
        "terms": terms,
        "top_pages": top_pages,
        "claims": top_claims,
        "relationships": top_rels,
        "matched_domains": matched_domains,
        "cognitive_context": cognitive_context,
        "total_scored": len(scored_pages),
    }


# ---------------------------------------------------------------------------
# Page reading (optional: read actual files for deep context)
# ---------------------------------------------------------------------------

def _extract_key_sections(path: Path) -> dict[str, str]:
    """Read a wiki page and extract key sections as structured text."""
    if not path.exists():
        return {"error": f"File not found: {path}"}

    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    page_type = meta.get("type", "")

    result: dict[str, str] = {
        "title": meta.get("title", path.stem),
        "type": page_type,
    }

    # One-sentence summary
    one_sentence = get_one_sentence(meta, body)
    if one_sentence:
        result["one_sentence"] = one_sentence

    # Type-specific sections
    if page_type == "source":
        for heading in ("核心摘要", "关键判断", "与现有知识库的关系", "主题域"):
            excerpt = section_excerpt(body, heading)
            if excerpt:
                result[heading] = excerpt
    elif page_type == "brief":
        for heading in ("骨架", "数据", "关键判断", "跨域联想"):
            excerpt = section_excerpt(body, heading)
            if excerpt:
                result[heading] = excerpt
    elif page_type == "concept":
        for heading in ("定义", "当前判断", "证据链", "跨域联想", "来自来源"):
            excerpt = section_excerpt(body, heading)
            if excerpt:
                result[heading] = excerpt
    elif page_type == "synthesis":
        for heading in ("当前结论", "证据链", "立场追踪", "跨域联想", "知识缺口", "近期来源", "关键判断"):
            excerpt = section_excerpt(body, heading)
            if excerpt:
                result[heading] = excerpt
    elif page_type == "stance":
        for heading in ("核心判断", "支持证据", "反对证据（steel-man）", "未解决子问题"):
            excerpt = section_excerpt(body, heading)
            if excerpt:
                result[heading] = excerpt
    else:
        # Generic: first ~500 chars of body
        result["body_excerpt"] = plain_text(body)[:500]

    return result


def _cross_vault_supplementary_retrieve(
    primary_vault: Path,
    primary_result: dict,
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """Check cross_domain_insights and supplement from other vaults.

    Steps:
    1. Collect target_domains from primary vault's cross_domain_insights
    2. Match against other vaults' purpose.md focus domains
    3. Load matching vaults' semantic-index.json, run supplementary retrieve
    4. Mark results as cross-vault supplementary

    Returns list of supplementary page dicts.
    """
    from pipeline.vault_config import load_vault_registry, parse_purpose_md

    registry = load_vault_registry()
    if len(registry) < 2:
        return []

    # Collect target domains from cross_domain_insights
    insights = primary_result.get("cognitive_context", {}).get("cross_domain_insights", [])
    target_domains: set[str] = set()
    for insight in insights:
        td = insight.get("target_domain", "")
        if td:
            target_domains.add(td)

    if not target_domains:
        return []

    # Find secondary vaults whose focus domains overlap with target domains
    supplementary_results: list[dict] = []
    for entry in registry:
        vault_path = Path(entry["path"])
        if not vault_path.exists() or vault_path.resolve() == primary_vault.resolve():
            continue

        purpose = parse_purpose_md(vault_path)
        focus_domains = set(purpose.get("focus", []))
        overlap = target_domains & focus_domains
        if not overlap:
            continue

        # Load secondary vault's semantic index
        secondary_index_path = vault_path / "wiki" / "semantic-index.json"
        if not secondary_index_path.exists():
            continue

        try:
            secondary_index = json.loads(secondary_index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        # Run supplementary retrieve
        secondary_result = retrieve(
            secondary_index, query, top_k=top_k,
            type_filter=["briefs", "sources", "concepts"],
        )

        # Mark results as cross-vault supplementary
        for page in secondary_result.get("top_pages", []):
            page["vault"] = entry.get("name", vault_path.name)
            page["is_cross_vault"] = True
            # Attach bridge logic from matching insights
            for insight in insights:
                if insight.get("target_domain", "") in page.get("domains", []):
                    page["bridge_logic"] = insight.get("bridge_logic", "")
                    page["mapped_concept"] = insight.get("mapped_concept", "")
                    break
            supplementary_results.append(page)

    return supplementary_results[:top_k * 2]


def retrieve_with_reading(
    index: dict,
    query: str,
    vault: Path,
    top_k: int = 5,
    type_filter: list[str] | None = None,
    read_pages: int = 3,
    cross_vault: bool = True,
) -> dict:
    """Retrieve + read top pages for deep context."""
    result = retrieve(index, query, top_k, type_filter)

    # Read actual files for top pages
    page_contents: list[dict] = []
    for page in result["top_pages"][:read_pages]:
        ref = page["ref"]
        folder = ref.split("/", 1)[0] if "/" in ref else ""
        slug = ref.split("/", 1)[1] if "/" in ref else ref
        path = vault / "wiki" / folder / f"{slug}.md"
        sections = _extract_key_sections(path)
        sections["ref"] = ref
        sections["score"] = page["score"]
        page_contents.append(sections)

    result["page_contents"] = page_contents

    # --- Cross-vault supplementary search ---
    if cross_vault:
        supplementary = _cross_vault_supplementary_retrieve(
            primary_vault=vault,
            primary_result=result,
            query=query,
            top_k=3,
        )
        if supplementary:
            result["cross_vault_supplementary"] = supplementary
            result["cognitive_context"]["cross_vault_supplementary"] = [
                {
                    "title": p.get("title", ""),
                    "ref": p.get("ref", ""),
                    "score": p.get("score", 0),
                    "folder": p.get("folder", ""),
                    "domains": p.get("domains", []),
                    "vault": p.get("vault", ""),
                    "bridge_logic": p.get("bridge_logic", ""),
                    "mapped_concept": p.get("mapped_concept", ""),
                    "note": "cross-vault supplementary result — LLM should evaluate relevance",
                }
                for p in supplementary
            ]

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart retrieval from the semantic index.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--query", required=True, help="Natural-language query.")
    parser.add_argument("--top-k", type=int, default=5, help="Max pages to return (default: 5).")
    parser.add_argument("--types", type=str, default=None,
                        help="Comma-separated page types to search (e.g. source,concept,synthesis).")
    parser.add_argument("--read", type=int, default=3,
                        help="Number of top pages to read for deep context (default: 3). 0 = skip reading.")
    parser.add_argument("--output", type=Path, help="Write result JSON to this path.")
    parser.add_argument("--json", action="store_true", help="Print result as JSON to stdout.")
    return parser.parse_args()


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()

    index_path = vault / "wiki" / "semantic-index.json"
    if not index_path.exists():
        print("semantic-index.json not found — auto-rebuilding...")
        import subprocess
        rebuild_cmd = [sys.executable, str(Path(__file__).parent / "wiki_index_v2.py"), "--vault", str(vault), "--rebuild"]
        proc = subprocess.run(rebuild_cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"Auto-rebuild failed: {proc.stderr.strip()}")
            print("Please run manually: python scripts/wiki_index_v2.py --vault <vault> --rebuild")
            return 1
        if not index_path.exists():
            print("Auto-rebuild completed but semantic-index.json still not found.")
            print("Please run manually: python scripts/wiki_index_v2.py --vault <vault> --rebuild")
            return 1
        print("Auto-rebuild complete.")

    index = json.loads(index_path.read_text(encoding="utf-8"))

    type_filter = args.types.split(",") if args.types else None

    if args.read > 0:
        result = retrieve_with_reading(
            index, args.query, vault,
            top_k=args.top_k, type_filter=type_filter, read_pages=args.read,
        )
    else:
        result = retrieve(index, args.query, top_k=args.top_k, type_filter=type_filter)

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        args.output.write_text(output_json, encoding="utf-8")
        print(f"Results written to {args.output}")
    elif args.json:
        print(output_json)
    else:
        # Human-readable summary
        print(f"Query: {result['query']}")
        print(f"Terms: {', '.join(result['terms'])}")
        print(f"Matched {result['total_scored']} pages, showing top {len(result['top_pages'])}")
        print()
        for i, page in enumerate(result["top_pages"], 1):
            print(f"  {i}. [{page['folder']}] {page['title']} (score: {page['score']:.1f})")
            if page.get("domains"):
                print(f"     domains: {', '.join(page['domains'])}")
            if page.get("confidence"):
                print(f"     confidence: {page['confidence']}")
        if result.get("claims"):
            print(f"\nTop claims ({len(result['claims'])}):")
            for claim in result["claims"][:5]:
                print(f"  - [{claim.get('confidence', '?')}] {claim['text'][:80]}")
        if result.get("page_contents"):
            print(f"\nRead {len(result['page_contents'])} pages for deep context.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
