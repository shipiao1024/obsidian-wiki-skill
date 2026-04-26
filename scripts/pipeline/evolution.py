"""Knowledge evolution tracking for the Obsidian wiki.

Tracks how concepts, domains, and stances change over time by analyzing
the append-only wiki/log.md and page update records.

Produces wiki/evolution.md with:
  - Timeline of significant events (new domains, stance changes, question resolutions)
  - Concept growth curve (how many concepts over time)
  - Domain knowledge accumulation rate
  - Stance confidence drift
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from .shared import parse_frontmatter


INGEST_LOG = re.compile(r"^## \[([^\]]+)\] ingest \| (.+)$", re.M)
QUERY_LOG = re.compile(r"^## \[([^\]]+)\] query(?:\((\w+)\))? \| (.+)$", re.M)


def _parse_log_timestamp(ts_str: str) -> date | None:
    """Parse 'YYYY-MM-DD HH:MM:SS' into a date."""
    try:
        return datetime.strptime(ts_str.strip(), "%Y-%m-%d %H:%M:%S").date()
    except ValueError:
        return None


def extract_timeline(vault: Path) -> list[dict[str, str]]:
    """Extract major events from log.md."""
    log_path = vault / "wiki" / "log.md"
    if not log_path.exists():
        return []

    text = log_path.read_text(encoding="utf-8")
    events: list[dict[str, str]] = []

    for match in INGEST_LOG.finditer(text):
        ts = match.group(1)
        title = match.group(2).strip()
        d = _parse_log_timestamp(ts)
        if d:
            events.append({"date": d.isoformat(), "type": "ingest", "title": title})

    for match in QUERY_LOG.finditer(text):
        ts = match.group(1)
        mode = match.group(2) or "brief"
        question = match.group(3).strip()
        d = _parse_log_timestamp(ts)
        if d:
            events.append({"date": d.isoformat(), "type": f"query({mode})", "title": question})

    return sorted(events, key=lambda e: e["date"])


def extract_stance_drift(vault: Path) -> list[dict[str, str]]:
    """Track stance confidence changes over time."""
    stances_dir = vault / "wiki" / "stances"
    if not stances_dir.exists():
        return []

    drift: list[dict[str, str]] = []
    for spath in sorted(stances_dir.glob("*.md")):
        text = spath.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        title = meta.get("title", "").strip('"') or spath.stem
        confidence = meta.get("confidence", "medium")
        status = meta.get("status", "active")
        created = meta.get("created", "")
        last_updated = meta.get("last_updated", "")
        source_count = meta.get("source_count", "0")

        # Extract update log entries
        updates: list[str] = []
        for line in body.splitlines():
            if line.startswith("- 20") and ":" in line[:22]:
                updates.append(line.strip("- ").strip())

        drift.append({
            "stance": f"stances/{spath.stem}",
            "title": title,
            "confidence": confidence,
            "status": status,
            "created": created,
            "last_updated": last_updated,
            "source_count": source_count,
            "updates": "; ".join(updates[:5]),
        })

    return drift


def extract_domain_growth(vault: Path) -> list[dict[str, str]]:
    """Count sources per domain to show knowledge accumulation."""
    domains_dir = vault / "wiki" / "domains"
    if not domains_dir.exists():
        return []

    growth: list[dict[str, str]] = []
    for dpath in sorted(domains_dir.glob("*.md")):
        text = dpath.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        title = meta.get("title", "").strip('"') or dpath.stem

        # Count linked sources
        source_links = re.findall(r"\[\[sources/([^\]]+)\]\]", body)
        source_count = len(set(source_links))

        growth.append({
            "domain": f"domains/{dpath.stem}",
            "title": title,
            "source_count": str(source_count),
        })

    return sorted(growth, key=lambda d: -int(d["source_count"]))


def extract_question_progress(vault: Path) -> dict[str, list[dict[str, str]]]:
    """Group questions by status to show knowledge gap closure."""
    questions_dir = vault / "wiki" / "questions"
    if not questions_dir.exists():
        return {"open": [], "partial": [], "resolved": [], "dropped": []}

    by_status: dict[str, list[dict[str, str]]] = {
        "open": [], "partial": [], "resolved": [], "dropped": [],
    }
    for qpath in sorted(questions_dir.glob("*.md")):
        text = qpath.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        status = meta.get("status", "open")
        title = meta.get("title", "").strip('"') or qpath.stem
        entry = {"ref": f"questions/{qpath.stem}", "title": title}
        if status in by_status:
            by_status[status].append(entry)
    return by_status


def build_evolution_page(vault: Path) -> str:
    """Build wiki/evolution.md page."""
    today = date.today().isoformat()

    timeline = extract_timeline(vault)
    stance_drift = extract_stance_drift(vault)
    domain_growth = extract_domain_growth(vault)
    question_progress = extract_question_progress(vault)

    lines = [
        "---",
        f'title: "知识演化追踪"',
        'type: "system-report"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        f'generated: "{today}"',
        "---",
        "",
        "# 知识演化追踪",
        "",
        f"> 生成日期：{today}",
        "",
    ]

    # Summary stats
    total_ingests = sum(1 for e in timeline if e["type"] == "ingest")
    total_queries = sum(1 for e in timeline if e["type"].startswith("query"))
    lines.append("## 概览")
    lines.append("")
    lines.append(f"- 总 ingest 事件：{total_ingests}")
    lines.append(f"- 总 query 事件：{total_queries}")
    lines.append(f"- 活跃立场：{sum(1 for s in stance_drift if s['status'] in ('active', 'challenged'))}")
    lines.append(f"- 开放问题：{len(question_progress.get('open', []))}")
    lines.append(f"- 已解决问题：{len(question_progress.get('resolved', []))}")
    lines.append("")

    # Domain growth
    lines.append("## 域知识积累")
    lines.append("")
    if domain_growth:
        for item in domain_growth:
            lines.append(f"- [[{item['domain']}]]: {item['source_count']} 篇来源")
    else:
        lines.append("- （暂无域页面）")
    lines.append("")

    # Stance drift
    lines.append("## 立场演化")
    lines.append("")
    if stance_drift:
        for item in stance_drift:
            lines.append(f"- [[{item['stance']}]] （{item['confidence']}/{item['status']}）: {item['updates'] or '无更新记录'}")
    else:
        lines.append("- （暂无立场页面）")
    lines.append("")

    # Question progress
    lines.append("## 问题进展")
    lines.append("")
    for status in ("open", "partial", "resolved", "dropped"):
        items = question_progress.get(status, [])
        if not items:
            continue
        label = {"open": "开放", "partial": "部分回答", "resolved": "已解决", "dropped": "已放弃"}[status]
        lines.append(f"### {label}（{len(items)}）")
        lines.append("")
        for item in items:
            lines.append(f"- [[{item['ref']}]]: {item['title']}")
        lines.append("")

    # Recent timeline (last 20 events)
    lines.append("## 近期事件")
    lines.append("")
    for event in timeline[-20:]:
        lines.append(f"- {event['date']} [{event['type']}] {event['title']}")
    if not timeline:
        lines.append("- （暂无事件）")
    lines.append("")

    return "\n".join(lines)


def write_evolution_page(vault: Path) -> Path:
    """Write wiki/evolution.md and return the path."""
    page_path = vault / "wiki" / "evolution.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_evolution_page(vault)
    page_path.write_text(content, encoding="utf-8")
    return page_path