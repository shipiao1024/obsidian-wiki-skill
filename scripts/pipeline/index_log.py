"""Index, log, and hot-cache management for the obsidian-wiki pipeline."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .text_utils import get_one_sentence, parse_frontmatter, section_excerpt, plain_text
from .page_builders import render_frontmatter, replace_links_section


def rebuild_index(vault: Path) -> None:
    sections = [
        ("Sources", "sources"),
        ("Briefs", "briefs"),
        ("Concepts", "concepts"),
        ("Entities", "entities"),
        ("Domains", "domains"),
        ("Syntheses", "syntheses"),
        ("Questions", "questions"),
        ("Stances", "stances"),
        ("Comparisons", "comparisons"),
        ("Outputs", "outputs"),
    ]
    lines = [
        "---",
        'title: "Wiki Index"',
        'type: "system-index"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        "---",
        "",
        "# Wiki Index",
        "",
        "> 先扫描本页，再按需打开相关页面。",
        "",
    ]
    for title, folder in sections:
        lines.extend([f"## {title}", ""])
        files = sorted((vault / "wiki" / folder).glob("*.md"))
        if not files:
            lines.append("- （空）")
            lines.append("")
            continue
        for file in files:
            text = file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            if folder == "outputs" and meta.get("lifecycle") == "absorbed":
                continue
            page_type = meta.get("type", "")
            if page_type == "source":
                summary = section_excerpt(body, "核心摘要")
            elif page_type == "brief":
                summary = get_one_sentence(meta, body)
            else:
                summary = plain_text(body)[:240].strip()
            if not summary:
                summary = plain_text(body)[:240].strip() or "待补充摘要"
            lines.append(f"- [[{folder}/{file.stem}]]: {summary}")
        lines.append("")
    (vault / "wiki" / "index.md").write_text("\n".join(lines), encoding="utf-8")


def append_log(vault: Path, entries: list[tuple[str, str, str]]) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    for title, slug, quality in entries:
        lines.extend(
            [
                f"## [{timestamp}] ingest | {title}",
                "",
                f"- raw: [[raw/articles/{slug}]]",
                f"- source: [[sources/{slug}]]",
                f"- brief: [[briefs/{slug}]]",
                *( [f"- quality: {quality}"] if quality else [] ),
                "",
            ]
        )
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def update_hot_cache(vault: Path, title: str, slug: str, compile_mode: str) -> None:
    """Append ingest summary to wiki/hot.md, keep last 5 entries per section."""
    hot_path = vault / "wiki" / "hot.md"
    if not hot_path.exists():
        return
    text = hot_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_line = f"- [{timestamp}] {title} ({compile_mode}) [[sources/{slug}]]"
    updated = replace_links_section(body, "Recent Ingests", [new_line], "- （空）")
    hot_path.write_text(render_frontmatter(meta) + updated, encoding="utf-8")