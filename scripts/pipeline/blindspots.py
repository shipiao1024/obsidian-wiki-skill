"""Knowledge blind-spot detection for the Obsidian wiki.

Scans the vault for:
  - Orphan taxonomy pages (no inbound links from sources)
  - Missing cross-links between concept/entity pages in the same domain
  - Domains with no questions or stances
  - Topics mentioned in sources but missing from taxonomy
  - Open questions with no progress clues
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .shared import (
    parse_frontmatter,
    plain_text,
    sanitize_filename,
)


def _all_refs_in_vault(vault: Path) -> set[str]:
    """Collect all [[ref]] targets that appear across wiki pages."""
    link_pattern = re.compile(r"\[\[([^|\]]+)")
    refs: set[str] = set()
    for folder in ("sources", "briefs", "concepts", "entities", "domains", "syntheses", "questions", "stances"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            refs.update(link_pattern.findall(text))
    return refs


def _taxonomy_backlinks(vault: Path) -> dict[str, int]:
    """Count how many source pages link to each taxonomy page."""
    link_pattern = re.compile(r"\[\[([^|\]]+)")
    counts: dict[str, int] = {}
    sources_dir = vault / "wiki" / "sources"
    if not sources_dir.exists():
        return counts
    for path in sources_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for ref in link_pattern.findall(text):
            if ref.startswith("concepts/") or ref.startswith("entities/") or ref.startswith("domains/"):
                counts[ref] = counts.get(ref, 0) + 1
    return counts


def detect_orphan_taxonomy(vault: Path) -> list[dict[str, str]]:
    """Taxonomy pages with zero inbound source links."""
    backlinks = _taxonomy_backlinks(vault)
    orphans: list[dict[str, str]] = []
    for folder in ("concepts", "entities", "domains"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.glob("*.md")):
            ref = f"{folder}/{path.stem}"
            if backlinks.get(ref, 0) == 0:
                meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
                orphans.append({
                    "ref": ref,
                    "title": meta.get("title", "").strip('"') or path.stem,
                    "reason": "无来源页链接至此概念/实体/域",
                })
    return orphans


def detect_missing_crosslinks(vault: Path) -> list[dict[str, str]]:
    """Concept/entity pages in the same domain that don't link each other."""
    link_pattern = re.compile(r"\[\[([^|\]]+)")
    gaps: list[dict[str, str]] = []

    # Map each taxonomy page to its domains
    page_domains: dict[str, set[str]] = {}
    for folder in ("concepts", "entities"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.md"):
            ref = f"{folder}/{path.stem}"
            text = path.read_text(encoding="utf-8")
            domains = set()
            for link in link_pattern.findall(text):
                if link.startswith("domains/"):
                    domains.add(link)
            page_domains[ref] = domains

    # For each domain, check if same-domain pages link each other
    domain_members: dict[str, list[str]] = {}
    for ref, domains in page_domains.items():
        for domain in domains:
            domain_members.setdefault(domain, []).append(ref)

    for domain, members in domain_members.items():
        if len(members) < 2:
            continue
        for i, ref_a in enumerate(members):
            text_a = (vault / "wiki" / f"{ref_a}.md").read_text(encoding="utf-8")
            links_a = set(link_pattern.findall(text_a))
            for ref_b in members[i + 1:]:
                if ref_b not in links_a:
                    gaps.append({
                        "page_a": ref_a,
                        "page_b": ref_b,
                        "shared_domain": domain,
                        "reason": f"同属 {domain} 但互无链接",
                    })
    return gaps[:20]


def detect_domain_gaps(vault: Path) -> list[dict[str, str]]:
    """Domains with no questions or stances."""
    gaps: list[dict[str, str]] = []
    domains_dir = vault / "wiki" / "domains"
    if not domains_dir.exists():
        return gaps

    question_refs = set()
    questions_dir = vault / "wiki" / "questions"
    if questions_dir.exists():
        for qpath in questions_dir.glob("*.md"):
            text = qpath.read_text(encoding="utf-8")
            link_pattern = re.compile(r"\[\[([^|\]]+)")
            for link in link_pattern.findall(text):
                if link.startswith("domains/"):
                    question_refs.add(link)

    stance_refs = set()
    stances_dir = vault / "wiki" / "stances"
    if stances_dir.exists():
        for spath in stances_dir.glob("*.md"):
            text = spath.read_text(encoding="utf-8")
            link_pattern = re.compile(r"\[\[([^|\]]+)")
            for link in link_pattern.findall(text):
                if link.startswith("domains/"):
                    stance_refs.add(link)

    for dpath in sorted(domains_dir.glob("*.md")):
        ref = f"domains/{dpath.stem}"
        has_questions = ref in question_refs
        has_stances = ref in stance_refs
        if not has_questions and not has_stances:
            meta, _ = parse_frontmatter(dpath.read_text(encoding="utf-8"))
            gaps.append({
                "domain": ref,
                "title": meta.get("title", "").strip('"') or dpath.stem,
                "reason": "该域既无开放问题也无立场",
            })
    return gaps


def detect_unrepresented_topics(vault: Path) -> list[dict[str, str]]:
    """Keywords frequently mentioned in sources but missing from taxonomy.

    Uses simple frequency analysis (script-based intelligent extraction removed;
    the LLM is now responsible for concept/entity extraction during compile).
    """
    import re
    from .shared import body_text

    # Collect all existing taxonomy names
    existing: set[str] = set()
    for folder in ("concepts", "entities"):
        dir_path = vault / "wiki" / folder
        if not dir_path.exists():
            continue
        for path in dir_path.glob("*.md"):
            existing.add(path.stem)

    # Scan recent sources for CJK terms and capitalized English terms
    freq: dict[str, int] = {}
    sources_dir = vault / "wiki" / "sources"
    if not sources_dir.exists():
        return []
    for path in sorted(sources_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        plain = body_text(text)
        # Extract CJK bigrams (2-4 chars)
        cjk_terms = re.findall(r"[一-鿿]{2,4}", plain)
        # Extract capitalized English terms (2+ chars)
        en_terms = re.findall(r"\b[A-Z][A-Za-z]{1,}\b", plain)
        seen_in_doc: set[str] = set()
        for name in cjk_terms + en_terms:
            if name not in existing and name not in seen_in_doc:
                freq[name] = freq.get(name, 0) + 1
                seen_in_doc.add(name)

    return [
        {"term": term, "mention_count": str(count), "reason": f"在 {count} 篇来源中出现但无对应概念/实体页"}
        for term, count in sorted(freq.items(), key=lambda x: -x[1])
        if count >= 2
    ][:15]


def detect_stale_questions(vault: Path) -> list[dict[str, str]]:
    """Open questions with no clues or partial answers."""
    gaps: list[dict[str, str]] = []
    questions_dir = vault / "wiki" / "questions"
    if not questions_dir.exists():
        return gaps
    for qpath in sorted(questions_dir.glob("*.md")):
        text = qpath.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        if meta.get("status") not in ("open", "partial"):
            continue
        # Check if clues section has real content
        has_clues = False
        in_clues = False
        for line in body.splitlines():
            if line.startswith("## 已知线索"):
                in_clues = True
                continue
            if line.startswith("## "):
                in_clues = False
                continue
            if in_clues and line.strip() and "暂无" not in line and line.strip() != "- ...":
                has_clues = True
                break
        if not has_clues:
            gaps.append({
                "question": f"questions/{qpath.stem}",
                "title": meta.get("title", "").strip('"') or qpath.stem,
                "reason": "开放问题无任何已知线索",
            })
    return gaps


def detect_research_blindspots(vault: Path) -> list[dict[str, str]]:
    """Active research projects with evidence-thin hypotheses or stale updates."""
    from .dependency_ledger import scan_active_research, read_ledger
    gaps: list[dict[str, str]] = []
    projects = scan_active_research(vault)

    for project in projects:
        if project["status"] != "active":
            continue
        topic = project["topic"]
        ledger = read_ledger(vault, topic)

        # Check for hypotheses with no F nodes
        for nid, node in ledger["nodes"].items():
            if node.get("type") == "H":
                conf = int(node.get("confidence", "0"))
                if conf < 20:
                    gaps.append({
                        "research": topic,
                        "node": nid,
                        "reason": f"{nid} 置信度 Preliminary ({conf}%)，缺乏事实支撑",
                    })

        # Check for stale research (no updates in 7+ days)
        last_updated = project.get("last_updated", "")
        if last_updated:
            try:
                from datetime import datetime, timedelta
                updated_date = datetime.strptime(last_updated, "%Y-%m-%d").date()
                if (date.today() - updated_date) > timedelta(days=7):
                    gaps.append({
                        "research": topic,
                        "node": "-",
                        "reason": f"研究项目已 {last_updated} 起未更新（>7 天）",
                    })
            except ValueError:
                pass

    return gaps


def build_blind_spots_page(vault: Path) -> str:
    """Build the wiki/blind-spots.md page."""
    today = date.today().isoformat()

    orphans = detect_orphan_taxonomy(vault)
    crosslink_gaps = detect_missing_crosslinks(vault)
    domain_gaps = detect_domain_gaps(vault)
    unrepresented = detect_unrepresented_topics(vault)
    stale_q = detect_stale_questions(vault)
    research_gaps = detect_research_blindspots(vault)

    lines = [
        "---",
        f'title: "知识盲点报告"',
        'type: "system-report"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        f'generated: "{today}"',
        "---",
        "",
        "# 知识盲点报告",
        "",
        f"> 生成日期：{today}",
        "",
    ]

    # Orphan taxonomy
    lines.append("## 孤立概念/实体/域")
    lines.append("")
    if orphans:
        for item in orphans:
            lines.append(f"- [[{item['ref']}]]: {item['reason']}")
    else:
        lines.append("- （无孤立页面）")
    lines.append("")

    # Missing crosslinks
    lines.append("## 缺失交叉链接")
    lines.append("")
    if crosslink_gaps:
        for item in crosslink_gaps:
            lines.append(f"- [[{item['page_a']}]] ↔ [[{item['page_b']}]]: {item['reason']}")
    else:
        lines.append("- （无缺失交叉链接）")
    lines.append("")

    # Domain gaps
    lines.append("## 缺少问题和立场的域")
    lines.append("")
    if domain_gaps:
        for item in domain_gaps:
            lines.append(f"- [[{item['domain']}]]: {item['reason']}")
    else:
        lines.append("- （所有域均有问题或立场）")
    lines.append("")

    # Unrepresented topics
    lines.append("## 来源高频提及但无对应页面")
    lines.append("")
    if unrepresented:
        for item in unrepresented:
            lines.append(f"- {item['term']}（出现 {item['mention_count']} 次）: {item['reason']}")
    else:
        lines.append("- （所有高频概念/实体已有对应页面）")
    lines.append("")

    # Stale questions
    lines.append("## 无线索的开放问题")
    lines.append("")
    if stale_q:
        for item in stale_q:
            lines.append(f"- [[{item['question']}]]: {item['reason']}")
    else:
        lines.append("- （所有开放问题均有线索）")
    lines.append("")

    # Research blindspots
    lines.append("## 研究项目盲点")
    lines.append("")
    if research_gaps:
        for item in research_gaps:
            lines.append(f"- {item['research']}: {item['reason']}")
    else:
        lines.append("- （无活跃研究项目或所有假说已有证据支撑）")
    lines.append("")

    return "\n".join(lines)


def write_blind_spots_page(vault: Path) -> Path:
    """Write wiki/blind-spots.md and return the path."""
    page_path = vault / "wiki" / "blind-spots.md"
    page_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_blind_spots_page(vault)
    page_path.write_text(content, encoding="utf-8")
    return page_path
