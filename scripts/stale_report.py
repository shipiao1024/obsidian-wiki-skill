#!/usr/bin/env python
"""Report pages that are likely stale or need maintenance in the local Obsidian LLM wiki."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.encoding_fix import fix_windows_encoding
from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)")
INGEST_LOG_PATTERN = re.compile(r"^## \[[^\]]+\] ingest \| (.+)$", re.M)
QUERY_LOG_PATTERN = re.compile(r"^## \[[^\]]+\] query(?:\(\w+\))? \| (.+)$", re.M)
PLACEHOLDER_PATTERNS = ("待补充", "待随着更多来源持续演化", "待后续", "待人工")
TAXONOMY_FOLDERS = ["concepts", "entities", "domains", "syntheses"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report stale or weak pages in the Obsidian LLM wiki.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--min-linked-sources", type=int, default=2, help="Minimum linked sources before a page is considered mature enough to require cleanup.")
    parser.add_argument("--stale-hours", type=int, default=1, help="Flag page if linked source is newer than page by this many hours.")
    parser.add_argument("--blind-spots", action="store_true", help="Also generate wiki/blind-spots.md report.")
    parser.add_argument("--auto-suggest", action="store_true", help="Output structured maintenance suggestions JSON.")
    return parser.parse_args()



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


def outbound_links(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {match.strip() for match in LINK_PATTERN.findall(text)}


def page_title(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    meta, _ = parse_frontmatter(text)
    return meta.get("title") or path.stem


def collect_source_pages(vault: Path) -> dict[str, Path]:
    return {f"sources/{path.stem}": path for path in (vault / "wiki" / "sources").glob("*.md")}


def linked_source_refs(path: Path) -> list[str]:
    return sorted(link for link in outbound_links(path) if link.startswith("sources/"))


def has_placeholder(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    return any(pattern in text for pattern in PLACEHOLDER_PATTERNS)


def linked_source_gap_hours(path: Path, source_pages: dict[str, Path]) -> float:
    page_mtime = path.stat().st_mtime
    max_gap_seconds = 0.0
    for ref in linked_source_refs(path):
        source_path = source_pages.get(ref)
        if not source_path:
            continue
        gap = source_path.stat().st_mtime - page_mtime
        if gap > max_gap_seconds:
            max_gap_seconds = gap
    return max_gap_seconds / 3600.0


def repeated_log_entries(log_text: str, pattern: re.Pattern[str]) -> dict[str, int]:
    counts = Counter(match.group(1).strip() for match in pattern.finditer(log_text))
    return {item: count for item, count in counts.items() if count > 1}


def repeated_outputs(vault: Path) -> dict[str, list[str]]:
    outputs: dict[str, list[str]] = defaultdict(list)
    for path in (vault / "wiki" / "outputs").glob("*.md"):
        outputs[page_title(path)].append(path.name)
    return {title: sorted(paths) for title, paths in outputs.items() if len(paths) > 1}


def _compute_health_score(report: dict[str, object]) -> int:
    """Compute health score from report data. Starts at 100, deducts for issues."""
    score = 100
    score -= len(report.get("stale_taxonomy_pages", [])) * 3
    score -= len(report.get("placeholder_pages_with_multiple_sources", [])) * 2
    score -= len(report.get("duplicate_outputs", {})) * 1
    return max(0, min(100, score))


def _count_pending_outputs(vault: Path) -> int:
    """Count outputs with lifecycle temporary or review-needed."""
    count = 0
    outputs_dir = vault / "wiki" / "outputs"
    if not outputs_dir.exists():
        return 0
    for path in outputs_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        lifecycle = meta.get("lifecycle", "")
        if lifecycle in {"temporary", "review-needed"}:
            count += 1
    return count


def _last_maintenance_date(vault: Path) -> str | None:
    """Read last maintenance date from log.md."""
    log_path = vault / "wiki" / "log.md"
    if not log_path.exists():
        return None
    log_text = log_path.read_text(encoding="utf-8")
    # Look for maintenance/lint entries
    maint_pattern = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\].*(?:lint|maintenance|维护)", re.M)
    matches = maint_pattern.findall(log_text)
    return max(matches) if matches else None


def _count_ingest_records(vault: Path) -> int:
    """Count ingest records in log.md."""
    log_path = vault / "wiki" / "log.md"
    if not log_path.exists():
        return 0
    log_text = log_path.read_text(encoding="utf-8")
    return len(INGEST_LOG_PATTERN.findall(log_text))


def build_auto_suggestions(vault: Path, report: dict[str, object]) -> dict[str, object]:
    """Build structured maintenance suggestions from report data."""
    suggestions: list[dict[str, str]] = []

    # Low health score
    health_score = _compute_health_score(report)
    if health_score < 80:
        suggestions.append({
            "type": "low_health_score",
            "score": str(health_score),
            "severity": "high",
            "reason": f"健康评分 {health_score}/100，低于 80 分阈值",
            "suggested_action": "健康检查",
            "suggested_command": "wiki_lint.py --collect-only",
        })

    # Stale pages
    stale_count = len(report.get("stale_taxonomy_pages", []))
    if stale_count >= 3:
        suggestions.append({
            "type": "stale_pages",
            "count": str(stale_count),
            "severity": "medium",
            "reason": f"{stale_count} 个页面时间戳早于引用来源，可能需要重新综合",
            "suggested_action": "主张分析",
            "suggested_command": "claim_evolution.py --collect-only",
        })

    # Pending outputs
    pending_count = _count_pending_outputs(vault)
    if pending_count >= 10:
        severity = "high" if pending_count >= 20 else "medium"
        suggestions.append({
            "type": "pending_outputs",
            "count": str(pending_count),
            "severity": severity,
            "reason": f"outputs/ 中有 {pending_count} 个待处理项目",
            "suggested_action": "审核队列",
            "suggested_command": "review_queue.py --collect-only",
        })

    # Duplicate outputs
    dup_count = len(report.get("duplicate_outputs", {}))
    if dup_count >= 2:
        suggestions.append({
            "type": "duplicate_outputs",
            "count": str(dup_count),
            "severity": "low",
            "reason": f"{dup_count} 组重复 output",
            "suggested_action": "审核队列",
            "suggested_command": "review_queue.py --sweep",
        })

    # Ingest count milestone (every 10)
    ingest_count = _count_ingest_records(vault)
    if ingest_count > 0 and ingest_count % 10 == 0:
        suggestions.append({
            "type": "ingest_milestone",
            "count": str(ingest_count),
            "severity": "low",
            "reason": f"已有 {ingest_count} 篇素材入库，建议定期检查",
            "suggested_action": "健康检查",
            "suggested_command": "wiki_lint.py --collect-only",
        })

    # Last maintenance date
    last_maint = _last_maintenance_date(vault)
    days_since = None
    if last_maint:
        from datetime import datetime
        try:
            last_date = datetime.strptime(last_maint, "%Y-%m-%d")
            days_since = (datetime.now() - last_date).days
            if days_since >= 14:
                suggestions.append({
                    "type": "maintenance_overdue",
                    "days": str(days_since),
                    "severity": "medium",
                    "reason": f"距上次维护已 {days_since} 天",
                    "suggested_action": "日常维护",
                    "suggested_command": "wiki_lint.py --collect-only",
                })
        except ValueError:
            pass

    return {
        "suggestions": suggestions,
        "last_maintenance": last_maint,
        "days_since_maintenance": days_since,
        "health_score": health_score,
        "pending_outputs": pending_count,
        "ingest_count": ingest_count,
    }


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    source_pages = collect_source_pages(vault)

    report: dict[str, object] = {
        "vault": str(vault),
        "stale_taxonomy_pages": [],
        "placeholder_pages_with_multiple_sources": [],
        "high_churn_queries": {},
        "high_churn_ingests": {},
        "duplicate_outputs": {},
    }

    for folder in TAXONOMY_FOLDERS:
        for path in (vault / "wiki" / folder).glob("*.md"):
            sources = linked_source_refs(path)
            if len(sources) >= args.min_linked_sources and has_placeholder(path):
                report["placeholder_pages_with_multiple_sources"].append(
                    {
                        "page": f"{folder}/{path.stem}",
                        "title": page_title(path),
                        "linked_sources": sources,
                        "reason": "已有多个来源，但页面仍含占位文案。",
                    }
                )
            gap_hours = linked_source_gap_hours(path, source_pages)
            if gap_hours >= args.stale_hours:
                report["stale_taxonomy_pages"].append(
                    {
                        "page": f"{folder}/{path.stem}",
                        "title": page_title(path),
                        "linked_sources": sources,
                        "source_newer_by_hours": round(gap_hours, 2),
                        "reason": "页面时间戳早于其引用的 source，可能需要重新综合。",
                    }
                )

    log_path = vault / "wiki" / "log.md"
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8")
        report["high_churn_ingests"] = repeated_log_entries(log_text, INGEST_LOG_PATTERN)
        report["high_churn_queries"] = repeated_log_entries(log_text, QUERY_LOG_PATTERN)

    report["duplicate_outputs"] = repeated_outputs(vault)

    if args.blind_spots:
        from pipeline.blindspots import write_blind_spots_page
        blind_spots_path = write_blind_spots_page(vault)
        report["blind_spots_page"] = str(blind_spots_path)

    if args.auto_suggest:
        suggestions = build_auto_suggestions(vault, report)
        print(json.dumps(suggestions, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
