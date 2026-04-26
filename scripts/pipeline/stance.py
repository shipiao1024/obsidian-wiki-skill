from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .shared import (
    sanitize_filename,
    parse_frontmatter,
)


STANCE_DIR = "wiki/stances"

VALID_STANCES = ("active", "challenged", "abandoned")
VALID_CONFIDENCES = ("high", "medium", "low")
VALID_IMPACTS = ("reinforce", "contradict", "extend", "neutral")


def stance_slug(topic: str) -> str:
    slug = sanitize_filename(topic.strip())
    slug = re.sub(r"[^\w\-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-") or "untitled-stance"


def build_stance_page(
    *,
    topic: str,
    core_judgement: str = "",
    confidence: str = "medium",
    status: str = "active",
    supporting_evidence: list[str] = [],
    contradicting_evidence: list[str] = [],
    open_sub_questions: list[str] = [],
    rethinking_conditions: str = "",
    created: str | None = None,
    last_updated: str | None = None,
    source_count: int = 0,
) -> str:
    today = date.today().isoformat()
    created = created or today
    last_updated = last_updated or today

    support_lines = "\n".join(f"- {s}" for s in supporting_evidence) if supporting_evidence else "- （暂无）"
    contradict_lines = "\n".join(f"- {s}" for s in contradicting_evidence) if contradicting_evidence else "- （暂无）"
    question_links = "\n".join(f"- [[{q}]]" for q in open_sub_questions) if open_sub_questions else "- （暂无）"

    lines = [
        "---",
        f"title: \"我对 {topic} 的当前立场\"",
        "type: \"stance\"",
        f"status: \"{status}\"",
        "graph_role: \"knowledge\"",
        "graph_include: \"true\"",
        "lifecycle: \"official\"",
        f"confidence: \"{confidence}\"",
        f"last_updated: \"{last_updated}\"",
        f"created: \"{created}\"",
        f"source_count: \"{source_count}\"",
        "---",
        "",
        f"# 我对 {topic} 的当前立场",
        "",
        "## 核心判断",
        core_judgement or "- （待形成判断）",
        f"（置信度：{confidence}）",
        "",
        "## 支持证据",
        support_lines,
        "",
        "## 反对证据（steel-man）",
        contradict_lines,
        "",
        "## 未解决子问题",
        question_links,
        "",
        "## 触发重新思考的条件",
        rethinking_conditions or "- （待补充）",
        "",
        "## 更新记录",
        f"- {today}: 创建",
        "",
    ]
    return "\n".join(lines)


def write_stance_page(
    vault: Path,
    *,
    topic: str,
    core_judgement: str = "",
    confidence: str = "medium",
    status: str = "active",
    supporting_evidence: list[str] = [],
    contradicting_evidence: list[str] = [],
    open_sub_questions: list[str] = [],
    rethinking_conditions: str = "",
    source_count: int = 0,
) -> Path:
    slug = stance_slug(topic)
    dir_path = vault / STANCE_DIR
    dir_path.mkdir(parents=True, exist_ok=True)
    page_path = dir_path / f"{slug}.md"

    content = build_stance_page(
        topic=topic,
        core_judgement=core_judgement,
        confidence=confidence,
        status=status,
        supporting_evidence=supporting_evidence,
        contradicting_evidence=contradicting_evidence,
        open_sub_questions=open_sub_questions,
        rethinking_conditions=rethinking_conditions,
        source_count=source_count,
    )
    page_path.write_text(content, encoding="utf-8")
    return page_path


def apply_stance_impact(
    vault: Path,
    slug: str,
    *,
    impact: str,
    source_link: str,
    note: str = "",
) -> Path:
    """Apply a stance impact from a new source ingestion.

    impact: reinforce / contradict / extend / neutral
    """
    page_path = vault / STANCE_DIR / f"{slug}.md"
    if not page_path.exists():
        raise FileNotFoundError(f"Stance page not found: {page_path}")

    if impact not in VALID_IMPACTS:
        raise ValueError(f"Invalid impact: {impact}")

    if impact == "neutral":
        return page_path

    text = page_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    today = date.today().isoformat()

    # Update source_count
    current_count = int(meta.get("source_count", "0"))
    meta["source_count"] = str(current_count + 1)
    meta["last_updated"] = today

    # Adjust confidence on contradict
    current_confidence = meta.get("confidence", "medium")
    if impact == "contradict":
        if current_confidence == "high":
            meta["confidence"] = "medium"
            meta["status"] = "active"
        elif current_confidence == "medium":
            meta["confidence"] = "low"
            meta["status"] = "challenged"

    # Rebuild frontmatter
    fm_lines = ["---"]
    for k, v in meta.items():
        fm_lines.append(f"{k}: \"{v}\"")
    fm_lines.append("---")

    # Find the evidence section and append
    body_lines = body.splitlines()
    new_lines: list[str] = []

    for line in body_lines:
        if line.startswith("## 支持证据") and impact == "reinforce":
            new_lines.append(line)
            new_lines.append(f"- {source_link}: {note}")
            continue
        elif line.startswith("## 反对证据（steel-man）") and impact == "contradict":
            new_lines.append(line)
            new_lines.append(f"- {source_link}: {note}")
            continue
        elif line.startswith("## 更新记录"):
            new_lines.append(line)
            new_lines.append(f"- {today}: {source_link} {impact}")
            continue
        else:
            new_lines.append(line)

    content = "\n".join(fm_lines) + "\n\n" + "\n".join(new_lines)
    page_path.write_text(content, encoding="utf-8")
    return page_path


def scan_active_stances(vault: Path) -> list[dict[str, str]]:
    """Return all active/challenged stances."""
    dir_path = vault / STANCE_DIR
    if not dir_path.exists():
        return []
    stances: list[dict[str, str]] = []
    for page in sorted(dir_path.glob("*.md")):
        text = page.read_text(encoding="utf-8")
        meta, _body = parse_frontmatter(text)
        status = meta.get("status", "active")
        if status in ("active", "challenged"):
            stances.append({
                "slug": page.stem,
                "title": meta.get("title", page.stem),
                "confidence": meta.get("confidence", "medium"),
                "status": status,
                "source_count": int(meta.get("source_count", "0")),
            })
    return stances