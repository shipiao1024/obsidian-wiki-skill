"""Mode: reading-list — recommended reading path sorted by dependency."""

from __future__ import annotations

import re
from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import parse_frontmatter, section_excerpt


def build_reading_list_seed(
    vault: Path,
    seed_topic: str,
) -> str:
    """Cold-start reading list based on a seed topic, no candidate matching needed.

    Scans all sources/briefs/syntheses, filters by domain/topic overlap,
    groups by domain, and sorts by date.
    """
    lines: list[str] = [f"# 推荐阅读路径：{seed_topic}", ""]
    seed_terms = [t for t in re.findall(r"[一-鿿]{2,8}|[A-Za-z0-9\-\+]{2,}", seed_topic) if len(t) >= 2]

    all_pages: list[dict[str, object]] = []
    for folder in ("sources", "briefs", "syntheses"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for fpath in sorted(dir_path.glob("*.md")):
            text = fpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if not meta:
                continue
            # Score by seed topic overlap
            overlap = sum(1 for t in seed_terms if t in text)
            if overlap == 0 and seed_terms:
                continue
            domain = meta.get("type", folder)
            title = _page_title(meta, fpath.stem)
            date_str = meta.get("date", "").strip('"')
            all_pages.append({
                "ref": f"{folder}/{fpath.stem}",
                "title": title,
                "date": date_str,
                "type": domain,
                "overlap": overlap,
                "body": body,
            })

    if not all_pages:
        lines.append("- （知识库中暂无相关内容，请先入库相关来源）")
        lines.append("")
        return "\n".join(lines)

    # Sort by overlap score (highest first), then by date (most recent first)
    all_pages.sort(key=lambda p: (-p.get("overlap", 0), p.get("date", "")))

    lines.append("## 阅读顺序（按相关性排序）")
    lines.append("")
    for i, page in enumerate(all_pages[:10], 1):
        ref = page["ref"]
        title = page["title"]
        date_str = page.get("date", "")
        page_type = page.get("type", "")
        overlap = page.get("overlap", 0)

        if page_type == "source":
            core = section_excerpt(page.get("body", ""), "核心摘要")[:150]
        elif page_type == "synthesis":
            core = section_excerpt(page.get("body", ""), "当前结论")[:150]
        elif page_type == "brief":
            core = section_excerpt(page.get("body", ""), "一句话结论")[:150]
        else:
            core = ""

        lines.append(f"### {i}. [[{ref}]] {title}")
        if date_str:
            lines.append(f"日期：{date_str}")
        if core:
            lines.append(f"要点：{core}")
        if overlap and seed_terms:
            matched = [t for t in seed_terms if t in (page.get("body", "") or "")]
            if matched:
                lines.append(f"关键词匹配：{', '.join(matched[:4])}")
        lines.append("")

    if len(all_pages) > 10:
        lines.append("## 补充来源")
        lines.append("")
        for page in all_pages[10:15]:
            lines.append(f"- [[{page['ref']}]] {page['title']}")
        lines.append("")

    return "\n".join(lines)


def build_reading_list_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """Recommended reading path sorted by dependency (foundational first)."""
    lines: list[str] = [f"# 推荐阅读路径：{question}", ""]

    # Collect source pages with metadata
    source_pages: list[dict[str, object]] = []
    for cand in candidates[:10]:
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        if not meta:
            continue
        # Count outgoing wikilinks to other sources (dependency measure)
        deps = re.findall(r"\[\[sources/([^\]|]+)", body)
        source_pages.append({
            "ref": ref,
            "title": _page_title(meta, cand.path.stem),  # type: ignore[attr-defined]
            "date": meta.get("date", "").strip('"'),
            "type": meta.get("type", ""),
            "deps": deps,
            "body": body,
        })

    # Topological sort by dependencies (foundational = fewest deps first)
    dep_count = {}
    for page in source_pages:
        dep_count[page["ref"]] = len(page.get("deps", []))
    sorted_pages = sorted(source_pages, key=lambda p: dep_count.get(p["ref"], 0))

    lines.append("## 阅读顺序（由基础到进阶）")
    lines.append("")
    for i, page in enumerate(sorted_pages, 1):
        ref = page["ref"]
        title = page["title"]
        date_str = page.get("date", "")
        page_type = page.get("type", "")
        deps = page.get("deps", [])

        if page_type == "source":
            body = page.get("body", "")
            core = section_excerpt(body, "核心摘要")[:150] if isinstance(body, str) else ""
            annotation = core
        elif page_type == "synthesis":
            body = page.get("body", "")
            annotation = section_excerpt(body, "当前结论")[:150] if isinstance(body, str) else ""
        else:
            annotation = ""

        lines.append(f"### {i}. [[{ref}]] {title}")
        if date_str:
            lines.append(f"日期：{date_str}")
        if annotation:
            lines.append(f"要点：{annotation}")
        if deps:
            dep_refs = [f"[[sources/{d}]]" for d in deps[:3]]
            lines.append(f"前置阅读：{', '.join(dep_refs)}")
        lines.append("")

    lines.append("## 补充来源")
    lines.append("")
    extra = [p for p in source_pages if p not in sorted_pages[:5]]
    for page in extra[:5]:
        lines.append(f"- [[{page['ref']}]] {page['title']}")
    if not extra:
        lines.append("- （无额外来源）")
    lines.append("")

    return "\n".join(lines)