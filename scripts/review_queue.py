#!/usr/bin/env python
"""Supporting script for the review stage in the WeChat Obsidian LLM wiki.

Build a focused review queue page from wiki/outputs lifecycle state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from wiki_lint import claim_conflict_records
from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
SECTION_PATTERN = re.compile(r"##\s+(.+?)\s*\n(.*?)(?=\n##\s+|\Z)", re.S)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supporting script for the review stage: generate a review queue page from pending outputs.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--write", action="store_true", help="Write wiki/review_queue.md")
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


def section_body(body: str, heading: str) -> str:
    for match in SECTION_PATTERN.finditer(body):
        if match.group(1).strip() == heading:
            return match.group(2).strip()
    return ""


def summary_line(meta: dict[str, str], body: str) -> str:
    page_type = meta.get("type", "")
    if page_type == "delta-compile":
        summary = (
            section_body(body, "关键判断")
            or section_body(body, "建议替换的一句话结论")
            or section_body(body, "背景")
            or "待复核草稿"
        )
        return re.sub(r"\s+", " ", summary).strip()
    answer = section_body(body, "回答") or "待复核问答"
    first = [line.strip() for line in answer.splitlines() if line.strip() and not line.strip().endswith("：")]
    return re.sub(r"\s+", " ", (first[0] if first else answer)).strip()


def lifecycle_rank(meta: dict[str, str]) -> tuple[int, str]:
    lifecycle = meta.get("lifecycle", "")
    order = {
        "review-needed": 0,
        "temporary": 1,
        "accepted": 2,
        "absorbed": 3,
        "archived": 4,
    }
    return order.get(lifecycle, 9), lifecycle


def conflicted_output_stems(vault: Path) -> set[str]:
    stems: set[str] = set()
    for item in claim_conflict_records(vault):
        for key in ("left_path", "right_path"):
            stem = item.get(key, "")
            if stem.startswith("delta-"):
                stems.add(stem)
    return stems


def low_quality_source_items(vault: Path) -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    for path in sorted((vault / "wiki" / "sources").glob("*.md")):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if meta.get("quality", "").strip().lower() != "low":
            continue
        title = meta.get("title") or path.stem
        summary = summary_line(meta, body)
        items.append((path.stem, title, summary))
    return items


def build_review_queue(vault: Path) -> tuple[dict[str, object], str]:
    outputs = sorted((vault / "wiki" / "outputs").glob("*.md"))
    conflicted_stems = conflicted_output_stems(vault)
    low_quality_sources = low_quality_source_items(vault)
    pending: list[tuple[str, str, str, str]] = []
    absorbed: list[tuple[str, str, str, str]] = []
    active_groups: defaultdict[str, list[str]] = defaultdict(list)
    archived: list[tuple[str, str, str, str]] = []

    for path in outputs:
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = meta.get("title") or path.stem
        lifecycle = meta.get("lifecycle", "")
        item = (path.stem, title, lifecycle, summary_line(meta, body))
        if lifecycle == "absorbed":
            absorbed.append(item)
        elif lifecycle == "archived":
            archived.append(item)
        elif lifecycle in {"temporary", "review-needed"}:
            pending.append(item)
            active_groups[title].append(path.stem)

    pending.sort(key=lambda item: (0 if item[0] in conflicted_stems else 1, lifecycle_rank({"lifecycle": item[2]}), item[0]))
    duplicates = {title: stems for title, stems in active_groups.items() if len(stems) > 1}

    lines = [
        "---",
        'title: "Review Queue"',
        'type: "system-review-queue"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        "---",
        "",
        "# Review Queue",
        "",
        "> 只看待处理 output，不把已吸收历史草稿混进日常导航。",
        "",
        "## 冲突候选",
        "",
    ]
    if conflicted_stems:
        for stem, title, lifecycle, summary in pending:
            if stem not in conflicted_stems:
                continue
            lines.append(f"- [[outputs/{stem}]] | `{lifecycle}` | {title}")
            lines.append(f"  - {summary}")
    else:
        lines.append("- 当前没有冲突候选。")

    lines.extend([
        "",
        "## 低质量来源候选",
        "",
    ])
    if low_quality_sources:
        for stem, title, summary in low_quality_sources:
            lines.append(f"- [[sources/{stem}]] | {title}")
            lines.append(f"  - {summary}")
    else:
        lines.append("- 当前没有低质量来源候选。")

    lines.extend([
        "",
        "## 待处理",
        "",
    ])
    if pending:
        for stem, title, lifecycle, summary in pending:
            lines.append(f"- [[outputs/{stem}]] | `{lifecycle}` | {title}")
            lines.append(f"  - {summary}")
    else:
        lines.append("- 当前没有待处理 output。")

    lines.extend(["", "## 重复候选", ""])
    if duplicates:
        for title, stems in sorted(duplicates.items()):
            lines.append(f"- {title}")
            for stem in sorted(stems):
                lines.append(f"  - [[outputs/{stem}]]")
    else:
        lines.append("- 当前没有标题重复的 output。")

    lines.extend(["", "## 已吸收统计", ""])
    lines.append(f"- 已吸收条目：{len(absorbed)}")
    lines.append(f"- 已归档条目：{len(archived)}")
    lines.append(f"- 待处理条目：{len(pending)}")
    lines.append("")

    report = {
        "pending_count": len(pending),
        "absorbed_count": len(absorbed),
        "archived_count": len(archived),
        "duplicate_titles": duplicates,
        "pending": [
            {"slug": stem, "title": title, "lifecycle": lifecycle, "summary": summary}
            for stem, title, lifecycle, summary in pending
        ],
        "conflicted_outputs": sorted(conflicted_stems),
        "low_quality_sources": [stem for stem, _title, _summary in low_quality_sources],
    }
    return report, "\n".join(lines)


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    report, page = build_review_queue(vault)
    page_path = vault / "wiki" / "review_queue.md"
    if args.write:
        page_path.write_text(page, encoding="utf-8")
        report["page"] = str(page_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
