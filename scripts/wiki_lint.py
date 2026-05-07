#!/usr/bin/env python
"""Basic health checks for the Obsidian LLM wiki.

Two modes:
  --collect-only  : Collect data → JSON for LLM analysis (Phase 1)
  --apply         : Execute LLM decisions from JSON (Phase 3)
  (default)       : Legacy mode — mechanical checks only, no semantic judgment
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from pipeline.encoding_fix import fix_windows_encoding

from pipeline.text_utils import (
    FRONTMATTER,
    SECTION_PATTERN,
    CLAIM_PATTERN,
    parse_frontmatter,
    section_body,
)
from pipeline.structure_fix import detect_structure_violations

WIKI_FOLDERS = ["sources", "briefs", "concepts", "entities", "domains", "syntheses", "comparisons", "questions", "stances", "outputs"]
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run health checks against the Obsidian LLM wiki.")
    parser.add_argument("--vault", type=Path, required=True, help="Obsidian vault root.")
    parser.add_argument("--collect-only", action="store_true", help="Collect data as JSON for LLM analysis (Phase 1).")
    parser.add_argument("--apply", type=Path, dest="apply_json", help="Execute LLM decisions from result JSON (Phase 3).")
    parser.add_argument("--output", type=Path, help="Output path for --collect-only JSON (default: stdout).")
    return parser.parse_args()


def collect_pages(vault: Path) -> dict[str, Path]:
    pages: dict[str, Path] = {}
    for folder in WIKI_FOLDERS:
        for path in (vault / "wiki" / folder).glob("*.md"):
            pages[f"{folder}/{path.stem}"] = path
    for path in (vault / "raw" / "articles").glob("*.md"):
        pages[f"raw/articles/{path.stem}"] = path
    return pages


def claim_inventory_issues(vault: Path) -> list[str]:
    issues: list[str] = []
    for path in (vault / "wiki" / "outputs").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if meta.get("type") != "delta-compile":
            continue
        claims_body = section_body(body, "关键判断")
        evidence_body = section_body(body, "证据")
        evidence_lines = [line.strip() for line in evidence_body.splitlines() if line.strip().startswith("- ")]
        for match in CLAIM_PATTERN.finditer(claims_body):
            claim_type = match.group(1).strip()
            confidence = match.group(2).strip().lower()
            claim = match.group(3).strip()
            if confidence == "low":
                issues.append(f"{path.stem}: low confidence claim [{claim_type}] {claim}")
            if not evidence_lines:
                issues.append(f"{path.stem}: claim missing evidence [{claim_type}] {claim}")
    return issues


def low_quality_sources(vault: Path) -> list[str]:
    issues: list[str] = []
    for path in (vault / "wiki" / "sources").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if meta.get("type") != "source":
            continue
        if meta.get("quality", "").strip().lower() != "low":
            continue
        summary = section_body(body, "核心摘要").splitlines()
        excerpt = ""
        for line in summary:
            line = line.strip()
            if line.startswith("- "):
                excerpt = line[2:].strip()
                break
        label = path.stem
        if excerpt:
            issues.append(f"{label}: {excerpt}")
        else:
            issues.append(label)
    return issues


def collect_claims(vault: Path) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []
    folders = [vault / "wiki" / "outputs", vault / "wiki" / "sources", vault / "wiki" / "briefs", vault / "wiki" / "syntheses"]
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            page_type = meta.get("type", "")
            if page_type not in {"delta-compile", "source", "brief", "synthesis"}:
                continue
            claims_body = section_body(body, "关键判断")
            for match in CLAIM_PATTERN.finditer(claims_body):
                claims.append(
                    {
                        "path": path.stem,
                        "claim_type": match.group(1).strip(),
                        "confidence": match.group(2).strip().lower(),
                        "claim": match.group(3).strip(),
                        "page_type": page_type,
                    }
                )
    return claims


# NOTE: claim_keywords(), claims_conflict(), claim_conflict_records(), claim_conflicts()
# were removed in the LLM-first refactoring. Semantic judgment (contradiction detection,
# claim relationship classification) is now handled by LLM per references/prompts/claim_evolution.md.
# Use claim_evolution.py --collect-only to gather claims, then let LLM analyze relationships.


def outbound_links(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {match.strip() for match in LINK_PATTERN.findall(text)}


def orphan_comparisons(vault: Path) -> list[str]:
    """Find comparison pages where no source mentions both subjects."""
    issues: list[str] = []
    comp_dir = vault / "wiki" / "comparisons"
    if not comp_dir.exists():
        return issues
    for path in comp_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        subject_a = meta.get("subject_a", "").strip('"')
        subject_b = meta.get("subject_b", "").strip('"')
        if not subject_a or not subject_b:
            issues.append(f"{path.stem}: missing subject_a or subject_b in frontmatter")
            continue
        both_found = False
        sources_dir = vault / "wiki" / "sources"
        if sources_dir.exists():
            for spath in sources_dir.glob("*.md"):
                src_text = spath.read_text(encoding="utf-8")
                if subject_a in src_text and subject_b in src_text:
                    both_found = True
                    break
        if not both_found:
            issues.append(f"{path.stem}: no source mentions both '{subject_a}' and '{subject_b}'")
    return issues


def sample_pages(vault: Path, count: int = 10) -> list[dict[str, str]]:
    """Random sample of wiki pages for LLM semantic analysis."""
    all_pages: list[Path] = []
    for folder in WIKI_FOLDERS:
        folder_path = vault / "wiki" / folder
        if folder_path.exists():
            all_pages.extend(folder_path.glob("*.md"))
    if not all_pages:
        return []
    sampled = random.sample(all_pages, min(count, len(all_pages)))
    result: list[dict[str, str]] = []
    for path in sampled:
        text = path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        folder = path.parent.name
        result.append({
            "path": f"{folder}/{path.stem}",
            "title": meta.get("title", path.stem).strip('"'),
            "type": meta.get("type", ""),
            "lifecycle": meta.get("lifecycle", ""),
            "frontmatter": {k: v for k, v in meta.items() if k in ("title", "type", "lifecycle", "quality", "domains", "status")},
            "body_excerpt": body[:500],
        })
    return result


def collect_lint_data(vault: Path) -> dict:
    """Phase 1: Collect all data for LLM analysis."""
    pages = collect_pages(vault)

    # Mechanical checks
    missing_briefs: list[str] = []
    missing_sources: list[str] = []
    raw_articles = sorted((vault / "raw" / "articles").glob("*.md"))
    for raw in raw_articles:
        stem = raw.stem
        if f"briefs/{stem}" not in pages:
            missing_briefs.append(stem)
        if f"sources/{stem}" not in pages:
            missing_sources.append(stem)

    broken_links: list[str] = []
    inbound_count = {key: 0 for key in pages}
    for key, path in pages.items():
        for link in outbound_links(path):
            if link in inbound_count:
                inbound_count[link] += 1
            elif link.startswith("raw/assets/"):
                continue
            elif not link.startswith("http"):
                broken_links.append(f"{key} -> {link}")

    orphan_pages: list[str] = []
    for key, count in inbound_count.items():
        if count == 0 and not key.startswith("raw/articles/"):
            if key not in {"wiki/index", "wiki/log", "wiki/hot"} and key not in {"index", "log", "hot"} and not key.startswith("outputs/"):
                orphan_pages.append(key)

    empty_folders: list[str] = []
    for folder in ["concepts", "entities", "domains", "syntheses"]:
        if not list((vault / "wiki" / folder).glob("*.md")):
            empty_folders.append(folder)

    # Candidate pages
    candidate_pages: list[dict[str, str]] = []
    for folder in ("sources", "briefs", "concepts", "entities"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            if meta.get("lifecycle") == "candidate":
                candidate_pages.append({"folder": folder, "slug": path.stem, "title": meta.get("title", path.stem).strip('"')})

    # Status mismatch (mechanical — reference count based)
    status_mismatch: list[str] = []
    VALID_PAGE_STATUS = ("seed", "developing", "mature", "evergreen", "draft")
    STATUS_UPGRADE_THRESHOLDS = {"seed": 1, "developing": 3, "mature": 6}
    for folder in ["concepts", "entities", "domains"]:
        for path in (vault / "wiki" / folder).glob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            status = meta.get("status", "seed")
            if status == "draft":
                status = "seed"
            name = meta.get("title", path.stem).strip('"')
            ref_count = 0
            for src_path in (vault / "wiki" / "sources").glob("*.md"):
                src_text = src_path.read_text(encoding="utf-8")
                if name in src_text:
                    ref_count += 1
            ordered = [s for s in VALID_PAGE_STATUS if s != "draft"]
            expected = "seed"
            for s, t in sorted(STATUS_UPGRADE_THRESHOLDS.items(), key=lambda x: ordered.index(x[0]) if x[0] in ordered else 0):
                s_idx = ordered.index(s) if s in ordered else -1
                if ref_count >= t and s_idx >= 0 and s_idx < len(ordered) - 1:
                    expected = ordered[s_idx + 1]
            if status != expected and ref_count > 0:
                status_mismatch.append(f"{folder}/{path.stem}: status={status}, expected={expected} (refs={ref_count})")

    # Claims for LLM analysis
    all_claims = collect_claims(vault)
    low_confidence_claims = [
        {"path": c["path"], "claim_type": c["claim_type"], "claim": c["claim"], "page_type": c["page_type"]}
        for c in all_claims if c["confidence"] == "low"
    ]

    # Structure violations (math/list/table blank line issues)
    structure_violations: list[dict] = []
    for folder in ("briefs", "sources", "concepts", "entities", "domains", "syntheses", "comparisons"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for v in detect_structure_violations(text):
                v["file"] = f"{folder}/{path.stem}"
                structure_violations.append(v)

    return {
        "broken_links": broken_links,
        "orphan_pages": orphan_pages,
        "missing_briefs": missing_briefs,
        "missing_sources": missing_sources,
        "empty_folders": empty_folders,
        "low_quality_sources": low_quality_sources(vault),
        "claim_inventory_issues": claim_inventory_issues(vault),
        "status_mismatch": status_mismatch,
        "orphan_comparisons": orphan_comparisons(vault),
        "low_confidence_claims": low_confidence_claims,
        "candidate_pages": candidate_pages,
        "all_claims": all_claims,
        "page_sample": sample_pages(vault),
        "structure_violations": structure_violations,
    }


def apply_lint_result(vault: Path, result_path: Path) -> None:
    """Phase 3: Execute LLM decisions from lint result JSON."""
    result = json.loads(result_path.read_text(encoding="utf-8"))

    # Apply repair suggestions
    repairs = result.get("repair_suggestions", [])
    for repair in repairs:
        action = repair.get("action", "")
        target = repair.get("target", "")
        if not action or not target:
            continue
        print(f"[repair] {target}: {action}")

    # Apply upgrade candidates
    upgrades = result.get("upgrade_candidates", [])
    for upgrade in upgrades:
        path_str = upgrade.get("path", "")
        new_status = upgrade.get("recommended_status", "")
        if not path_str or not new_status:
            continue
        full_path = vault / "wiki" / f"{path_str}.md"
        if not full_path.exists():
            print(f"[skip] {path_str}: file not found")
            continue
        text = full_path.read_text(encoding="utf-8")
        # Update lifecycle from candidate to the recommended level
        text = text.replace('lifecycle: "candidate"', f'lifecycle: "{new_status}"')
        full_path.write_text(text, encoding="utf-8")
        print(f"[upgrade] {path_str} → {new_status}")

    summary = result.get("summary", {})
    print(f"\nLint applied: {summary.get('critical_issues', 0)} critical, {summary.get('warnings', 0)} warnings, {summary.get('suggestions', 0)} suggestions")


def main_legacy(vault: Path) -> int:
    """Legacy mode: mechanical checks only, no semantic judgment."""
    pages = collect_pages(vault)
    results: dict[str, list[str]] = {
        "missing_briefs": [],
        "missing_sources": [],
        "orphan_pages": [],
        "empty_taxonomy_folders": [],
        "broken_wikilinks": [],
        "low_quality_sources": [],
        "claim_inventory_issues": [],
        "status_mismatch": [],
        "orphan_comparisons": [],
        "structure_violations": [],
    }

    raw_articles = sorted((vault / "raw" / "articles").glob("*.md"))
    for raw in raw_articles:
        stem = raw.stem
        if f"briefs/{stem}" not in pages:
            results["missing_briefs"].append(stem)
        if f"sources/{stem}" not in pages:
            results["missing_sources"].append(stem)

    inbound_count = {key: 0 for key in pages}
    for key, path in pages.items():
        for link in outbound_links(path):
            if link in inbound_count:
                inbound_count[link] += 1
            elif link.startswith("raw/assets/"):
                continue
            elif not link.startswith("http"):
                results["broken_wikilinks"].append(f"{key} -> {link}")

    for key, count in inbound_count.items():
        if count == 0 and not key.startswith("raw/articles/"):
            if key not in {"wiki/index", "wiki/log", "wiki/hot"} and key not in {"index", "log", "hot"} and not key.startswith("outputs/"):
                results["orphan_pages"].append(key)

    for folder in ["concepts", "entities", "domains", "syntheses"]:
        if not list((vault / "wiki" / folder).glob("*.md")):
            results["empty_taxonomy_folders"].append(folder)

    results["low_quality_sources"] = low_quality_sources(vault)
    results["claim_inventory_issues"] = claim_inventory_issues(vault)
    results["orphan_comparisons"] = orphan_comparisons(vault)

    all_claims = collect_claims(vault)
    results["low_confidence_claims"] = [
        {"path": c["path"], "claim_type": c["claim_type"], "claim": c["claim"], "page_type": c["page_type"]}
        for c in all_claims if c["confidence"] == "low"
    ]

    candidate_pages: list[dict[str, str]] = []
    for folder in ("sources", "briefs", "concepts", "entities"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            if meta.get("lifecycle") == "candidate":
                candidate_pages.append({"folder": folder, "slug": path.stem, "title": meta.get("title", path.stem).strip('"')})
    results["candidate_pages"] = candidate_pages

    VALID_PAGE_STATUS = ("seed", "developing", "mature", "evergreen", "draft")
    STATUS_UPGRADE_THRESHOLDS = {"seed": 1, "developing": 3, "mature": 6}
    for folder in ["concepts", "entities", "domains"]:
        for path in (vault / "wiki" / folder).glob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            status = meta.get("status", "seed")
            if status == "draft":
                status = "seed"
            name = meta.get("title", path.stem).strip('"')
            ref_count = 0
            for src_path in (vault / "wiki" / "sources").glob("*.md"):
                src_text = src_path.read_text(encoding="utf-8")
                if name in src_text:
                    ref_count += 1
            ordered = [s for s in VALID_PAGE_STATUS if s != "draft"]
            expected = "seed"
            for s, t in sorted(STATUS_UPGRADE_THRESHOLDS.items(), key=lambda x: ordered.index(x[0]) if x[0] in ordered else 0):
                s_idx = ordered.index(s) if s in ordered else -1
                if ref_count >= t and s_idx >= 0 and s_idx < len(ordered) - 1:
                    expected = ordered[s_idx + 1]
            if status != expected and ref_count > 0:
                results["status_mismatch"].append(f"{folder}/{path.stem}: status={status}, expected={expected} (refs={ref_count})")

    # Structure violations
    structure_violations: list[dict] = []
    for folder in ("briefs", "sources", "concepts", "entities", "domains", "syntheses", "comparisons"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for v in detect_structure_violations(text):
                v["file"] = f"{folder}/{path.stem}"
                structure_violations.append(v)
    results["structure_violations"] = structure_violations

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = args.vault.resolve()

    if args.apply_json:
        apply_lint_result(vault, args.apply_json)
        return 0

    if args.collect_only:
        data = collect_lint_data(vault)
        output = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Lint data written to {args.output}")
        else:
            print(output)
        return 0

    return main_legacy(vault)


if __name__ == "__main__":
    raise SystemExit(main())
