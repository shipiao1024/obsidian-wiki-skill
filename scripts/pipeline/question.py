from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .shared import (
    sanitize_filename,
    slugify_article,
    parse_frontmatter,
    FRONTMATTER,
)


QUESTION_DIR = "wiki/questions"

VALID_STATUSES = ("open", "partial", "resolved", "dropped")


def question_slug(question_text: str) -> str:
    slug = sanitize_filename(question_text[:60].strip())
    slug = re.sub(r"[^\w\-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-") or "untitled-question"


def build_question_page(
    *,
    question: str,
    status: str = "open",
    origin_source: str = "",
    origin_query: str = "",
    partial_answer: str = "",
    known_clues: str = "",
    needed_materials: str = "",
    related_sources: list[str] = [],
    related_concepts: list[str] = [],
    created: str | None = None,
    last_updated: str | None = None,
) -> str:
    today = date.today().isoformat()
    created = created or today
    last_updated = last_updated or today

    source_links = "\n".join(f"- [[{s}]]" for s in related_sources) if related_sources else "- ..."
    concept_links = "\n".join(f"- [[concepts/{c}]]" for c in related_concepts) if related_concepts else "- ..."

    lines = [
        "---",
        f"title: \"{question}\"",
        "type: \"question\"",
        f"status: \"{status}\"",
        "graph_role: \"knowledge\"",
        "graph_include: \"true\"",
        "lifecycle: \"official\"",
        f"origin_source: \"{origin_source}\"",
        f"origin_query: \"{origin_query}\"",
        f"created: \"{created}\"",
        f"last_updated: \"{last_updated}\"",
        "---",
        "",
        f"# {question}",
        "",
        "## 当前部分答案",
        partial_answer or "- （暂无）",
        "",
        "## 已知线索",
        known_clues or "- （暂无）",
        "",
        "## 回答需要什么类型的新材料",
        needed_materials or "- （待补充）",
        "",
        "## 相关概念",
        concept_links,
        "",
        "## 相关来源",
        source_links,
        "",
        "## 更新记录",
        f"- {today}: 创建",
        "",
    ]
    return "\n".join(lines)


def write_question_page(
    vault: Path,
    *,
    question: str,
    status: str = "open",
    origin_source: str = "",
    origin_query: str = "",
    partial_answer: str = "",
    known_clues: str = "",
    needed_materials: str = "",
    related_sources: list[str] = [],
    related_concepts: list[str] = [],
) -> Path:
    slug = question_slug(question)
    dir_path = vault / QUESTION_DIR
    dir_path.mkdir(parents=True, exist_ok=True)
    page_path = dir_path / f"{slug}.md"

    content = build_question_page(
        question=question,
        status=status,
        origin_source=origin_source,
        origin_query=origin_query,
        partial_answer=partial_answer,
        known_clues=known_clues,
        needed_materials=needed_materials,
        related_sources=related_sources,
        related_concepts=related_concepts,
    )
    page_path.write_text(content, encoding="utf-8")
    return page_path


def update_question_status(
    vault: Path,
    slug: str,
    *,
    new_status: str,
    update_note: str = "",
    partial_answer: str | None = None,
    known_clues: str | None = None,
    related_sources: list[str] | None = None,
) -> Path:
    page_path = vault / QUESTION_DIR / f"{slug}.md"
    if not page_path.exists():
        raise FileNotFoundError(f"Question page not found: {page_path}")

    text = page_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    today = date.today().isoformat()

    meta["status"] = new_status
    meta["last_updated"] = today

    # Rebuild frontmatter
    fm_lines = ["---"]
    for k, v in meta.items():
        fm_lines.append(f"{k}: \"{v}\"")
    fm_lines.append("---")

    # Update body sections
    body_lines = body.splitlines()
    new_lines: list[str] = []

    in_section = ""
    for line in body_lines:
        if line.startswith("## 当前部分答案"):
            in_section = "partial_answer"
            new_lines.append(line)
            if partial_answer is not None:
                new_lines.append(partial_answer)
                in_section = "skip_rest"
            continue
        if line.startswith("## 已知线索"):
            in_section = "known_clues"
            new_lines.append(line)
            if known_clues is not None:
                new_lines.append(known_clues)
                in_section = "skip_rest"
            continue
        if line.startswith("## 相关来源"):
            in_section = "related_sources"
            new_lines.append(line)
            if related_sources is not None:
                for s in related_sources:
                    new_lines.append(f"- [[{s}]]")
                in_section = "skip_rest"
            continue
        if line.startswith("## 更新记录"):
            in_section = "update_log"
            new_lines.append(line)
            continue
        if line.startswith("## ") and in_section:
            in_section = ""
            new_lines.append(line)
            continue
        if in_section != "skip_rest":
            new_lines.append(line)

    # Append update note
    if update_note:
        update_idx = -1
        for i, line in enumerate(new_lines):
            if line.strip() == "":
                update_idx = i
                break
        update_entry = f"- {today}: {update_note}"
        # Find the update log section and append
        for i, line in enumerate(new_lines):
            if line.startswith("## 更新记录"):
                # Insert after the section header and existing entries
                j = i + 1
                while j < len(new_lines) and not new_lines[j].startswith("## ") and not new_lines[j].startswith("- "):
                    j += 1
                if j < len(new_lines) and new_lines[j].startswith("- "):
                    new_lines.insert(j, update_entry)
                else:
                    new_lines.insert(i + 1, update_entry)
                break

    content = "\n".join(fm_lines) + "\n\n" + "\n".join(new_lines)
    page_path.write_text(content, encoding="utf-8")
    return page_path


def scan_open_questions(vault: Path) -> list[dict[str, str]]:
    """Return all open/partial questions with their metadata."""
    dir_path = vault / QUESTION_DIR
    if not dir_path.exists():
        return []
    questions: list[dict[str, str]] = []
    for page in sorted(dir_path.glob("*.md")):
        text = page.read_text(encoding="utf-8")
        meta, _body = parse_frontmatter(text)
        status = meta.get("status", "open")
        if status in ("open", "partial"):
            questions.append({
                "slug": page.stem,
                "title": meta.get("title", page.stem),
                "status": status,
                "origin_source": meta.get("origin_source", ""),
                "path": str(page),
            })
    return questions


def check_source_answers_questions(
    vault: Path,
    source_title: str,
    source_slug: str,
    source_keywords: list[str],
) -> list[str]:
    """Check if a new source might answer any open/partial questions.

    Returns list of question slugs that appear to be addressed.
    Uses keyword matching: if >= 3 source keywords overlap with question title/keywords.
    """
    open_questions = scan_open_questions(vault)
    matched: list[str] = []
    source_kw_set = set(kw.lower() for kw in source_keywords)

    for q in open_questions:
        q_title = q["title"].lower()
        q_keywords = set(re.findall(r"\w+", q_title))
        overlap = source_kw_set & q_keywords
        if len(overlap) >= 3:
            matched.append(q["slug"])
    return matched