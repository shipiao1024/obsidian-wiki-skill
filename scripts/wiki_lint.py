#!/usr/bin/env python
"""Basic health checks for the Obsidian LLM wiki."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


WIKI_FOLDERS = ["sources", "briefs", "concepts", "entities", "domains", "syntheses", "comparisons", "questions", "stances", "outputs"]
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
SECTION_PATTERN = re.compile(r"##\s+(.+?)\s*\n(.*?)(?=\n##\s+|\Z)", re.S)
CLAIM_PATTERN = re.compile(r"^- \[([^\]|]+)\|([^\]]+)\]\s+(.+)$", re.M)
CLAIM_NORMALIZE = re.compile(r"[，。；、\s]+")
CJK_CHUNK = re.compile(r"[\u4e00-\u9fff]{2,}")
CONFLICT_PAIRS = [
    ("会", "不会"),
    ("支持", "反对"),
    ("增强", "削弱"),
    ("加强", "削弱"),
    ("增加", "减少"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run health checks against the Obsidian LLM wiki.")
    parser.add_argument("--vault", type=Path, required=True, help="Obsidian vault root.")
    return parser.parse_args()


def collect_pages(vault: Path) -> dict[str, Path]:
    pages: dict[str, Path] = {}
    for folder in WIKI_FOLDERS:
        for path in (vault / "wiki" / folder).glob("*.md"):
            pages[f"{folder}/{path.stem}"] = path
    for path in (vault / "raw" / "articles").glob("*.md"):
        pages[f"raw/articles/{path.stem}"] = path
    return pages


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, text[match.end():]


def section_body(body: str, heading: str) -> str:
    for match in SECTION_PATTERN.finditer(body):
        if match.group(1).strip() == heading:
            return match.group(2).strip()
    return ""


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
    folders = [vault / "wiki" / "outputs", vault / "wiki" / "sources", vault / "wiki" / "syntheses"]
    for folder in folders:
        if not folder.exists():
            continue
        for path in folder.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            page_type = meta.get("type", "")
            if page_type not in {"delta-compile", "source", "synthesis"}:
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


def normalized_claim_key(claim: str) -> str:
    text = claim
    for left, right in CONFLICT_PAIRS:
        text = text.replace(left, "")
        text = text.replace(right, "")
    text = CLAIM_NORMALIZE.sub("", text)
    return text[:24]


def claim_keywords(claim: str) -> set[str]:
    text = claim
    for left, right in CONFLICT_PAIRS:
        text = text.replace(left, "")
        text = text.replace(right, "")
    keywords: set[str] = set()
    for chunk in CJK_CHUNK.findall(text):
        if len(chunk) < 2:
            continue
        for size in range(2, min(4, len(chunk)) + 1):
            for start in range(0, len(chunk) - size + 1):
                keywords.add(chunk[start : start + size])
    return keywords


def claims_conflict(left: str, right: str) -> bool:
    for positive, negative in CONFLICT_PAIRS:
        if positive in left and negative in right:
            return True
        if negative in left and positive in right:
            return True
    return False


def claim_conflict_records(vault: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    claims = collect_claims(vault)
    for idx in range(len(claims)):
        for jdx in range(idx + 1, len(claims)):
            left = claims[idx]
            right = claims[jdx]
            if not claims_conflict(left["claim"], right["claim"]):
                continue
            overlap = claim_keywords(left["claim"]) & claim_keywords(right["claim"])
            if not overlap:
                continue
            issues.append(
                {
                    "left_path": left["path"],
                    "right_path": right["path"],
                    "left_claim": left["claim"],
                    "right_claim": right["claim"],
                }
            )
    return issues


def claim_conflicts(vault: Path) -> list[str]:
    return [
        f"{item['left_path']} vs {item['right_path']}: {item['left_claim']} <> {item['right_claim']}"
        for item in claim_conflict_records(vault)
    ]


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


def main() -> int:
    args = parse_args()
    vault = args.vault.resolve()
    pages = collect_pages(vault)
    results: dict[str, list[str]] = {
        "missing_briefs": [],
        "missing_sources": [],
        "orphan_pages": [],
        "empty_taxonomy_folders": [],
        "broken_wikilinks": [],
        "low_quality_sources": [],
        "claim_inventory_issues": [],
        "claim_conflicts": [],
        "status_mismatch": [],
        "orphan_comparisons": [],
    }

    raw_articles = sorted((vault / "raw" / "articles").glob("*.md"))
    for raw in raw_articles:
        stem = raw.stem
        if f"wiki/briefs/{stem}".replace("wiki/", "") not in pages and f"briefs/{stem}" not in pages:
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
    results["claim_conflicts"] = claim_conflicts(vault)
    results["orphan_comparisons"] = orphan_comparisons(vault)

    # --- Status mismatch: check if page status aligns with reference count ---
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

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
