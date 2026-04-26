"""Ingest impact report: post-ingestion guidance for the user.

Builds a structured report of what changed in the knowledge base
after ingesting a new source, and suggests next steps.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .shared import (
    Article,
    extract_content_questions,
    extract_content_topics,
    parse_frontmatter,
    section_excerpt,
)


def build_ingest_impact_report(
    vault: Path,
    slug: str,
    title: str,
    compiled_payload: dict | None,
    compile_mode: str = "heuristic",
    article: Article | None = None,
    domain_mismatch: dict | None = None,
) -> dict:
    """Build a post-ingestion impact report and next-step suggestions."""

    report: dict = {
        "title": title,
        "slug": slug,
        "compile_mode": compile_mode,
        "content_questions": [],
        "content_topics": [],
        "cross_domain_insights": [],
        "domain_mismatch": domain_mismatch or {},
        "new_questions": [],
        "answered_questions": [],
        "stance_impacts": [],
        "related_sources_count": 0,
        "domain_hint": "",
        "insights": [],
    }

    # Prefer LLM-compiled data over heuristic extraction
    result = (compiled_payload or {}).get("result", {})

    # Questions: prefer open_questions from LLM compile
    if result.get("open_questions"):
        report["content_questions"] = result["open_questions"]
    elif article:
        report["content_questions"] = extract_content_questions(article)

    # Topics: prefer knowledge_proposals concept names from LLM compile
    proposed_concepts = [
        p["name"]
        for p in (result.get("knowledge_proposals", {}).get("concepts") or [])
        if p.get("action") != "no_page"
    ]
    if proposed_concepts:
        report["content_topics"] = proposed_concepts
    elif article:
        report["content_topics"] = extract_content_topics(article)

    # Cross-domain insights: only available from LLM compile
    if result.get("cross_domain_insights"):
        report["cross_domain_insights"] = result["cross_domain_insights"]

    # 1. Scan wiki/questions/ for questions created by this source
    questions_dir = vault / "wiki" / "questions"
    if questions_dir.exists():
        for qpath in sorted(questions_dir.glob("*.md")):
            text = qpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            origin = meta.get("origin_source", "")
            if origin == f"sources/{slug}" or f"sources/{slug}" in origin:
                q_text = section_excerpt(body, "问题") or meta.get("title", "").strip('"') or qpath.stem
                status = meta.get("status", "open")
                report["new_questions"].append(f"{q_text} ({status})")

    # 2. Check wiki/stances/ for impacts from this source
    stances_dir = vault / "wiki" / "stances"
    if stances_dir.exists():
        for spath in sorted(stances_dir.glob("*.md")):
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            impacts_raw = meta.get("impacts", "")
            if f"sources/{slug}" in impacts_raw:
                stance_topic = meta.get("title", "").strip('"') or spath.stem
                impact_type = ""
                for line in impacts_raw.splitlines():
                    if f"sources/{slug}" in line:
                        for itype in ("reinforce", "contradict", "extend"):
                            if itype in line.lower():
                                impact_type = itype
                                break
                report["stance_impacts"].append(
                    f"{stance_topic}: {impact_type or '影响'}"
                )

    # 3. Count related existing sources (by title/keyword overlap)
    sources_dir = vault / "wiki" / "sources"
    if sources_dir.exists():
        title_terms = [t for t in re.findall(r"[一-鿿]{2,8}|[A-Za-z0-9\-+]{2,}", title) if len(t) >= 2]
        related_count = 0
        domain_hint = ""
        for spath in sorted(sources_dir.glob("*.md")):
            if spath.stem == slug:
                continue
            text = spath.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            src_title = meta.get("title", "").strip('"')
            overlap = sum(1 for t in title_terms if t in src_title or t in text[:500])
            if overlap >= 2:
                related_count += 1
                domains_raw = meta.get("domains", "")
                if domains_raw and not domain_hint:
                    for d in domains_raw.split(","):
                        d = d.strip().strip('"')
                        if d:
                            domain_hint = d
                            break
        report["related_sources_count"] = related_count
        report["domain_hint"] = domain_hint or title[:20]

    # 4. Read latest insights from graph-data.json
    graph_data_path = vault / "wiki" / "graph-data.json"
    if graph_data_path.exists():
        try:
            data = json.loads(graph_data_path.read_text(encoding="utf-8"))
            insights = data.get("insights", [])
            if isinstance(insights, list):
                for ins in insights[:3]:
                    desc = ins.get("description", "")
                    if desc:
                        report["insights"].append(desc)
        except (json.JSONDecodeError, OSError):
            pass

    return report


def format_ingest_report(report: dict) -> str:
    """Format the impact report as user-readable guidance text."""

    lines: list[str] = [f"入库完成：{report['title']}", ""]

    # Quick read entry point
    lines.append("快速了解：")
    lines.append(f"  -> [[briefs/{report['slug']}]] -- 一页快读")
    lines.append("")

    # Content highlights
    topics = report.get("content_topics", [])
    if topics:
        lines.append("内容要点：")
        for topic in topics[:5]:
            lines.append(f"  . {topic}")
        lines.append("")

    # Content-derived questions
    questions = report.get("content_questions", [])
    if questions:
        lines.append("深度探索：")
        lines.append("  . 问一个具体问题，如：")
        for q in questions[:5]:
            lines.append(f"    - \"{q}\"")
        lines.append("  -> 基于已有知识库回答；如果库中没有相关内容，会明确告知")
        lines.append("")

    # Cross-domain insights
    cross_insights = report.get("cross_domain_insights", [])
    mismatch = report.get("domain_mismatch", {})
    if cross_insights:
        lines.append("跨域联想：")
        for insight in cross_insights[:3]:
            concept = insight.get("mapped_concept", "")
            domain = insight.get("target_domain", "")
            logic = insight.get("bridge_logic", "")
            question = insight.get("potential_question", "")
            lines.append(f"  . {concept} -> {domain}")
            lines.append(f"    \"{logic}\"")
            if question:
                lines.append(f"    -> 问：\"{question}\"")
        lines.append("")
        if mismatch.get("is_mismatch"):
            lines.append("  . 建议：1. 将此内容作为跨域参考保留 2. 创建新领域独立归档")
            lines.append("")
    elif mismatch.get("is_mismatch"):
        suggested = mismatch.get("suggested_domain_name", "")
        vault_domains = mismatch.get("vault_domains", [])
        vault_names = "、".join(vault_domains[:5]) if vault_domains else "（空）"
        lines.append("* 领域匹配：")
        lines.append(f"  . 此内容与知识库现有领域（{vault_names}）无交叉")
        if suggested:
            lines.append(f"  . 建议：1. 创建「{suggested}」新领域并归入 2. 放入待归域稍后处理")
        else:
            lines.append(f"  . 建议：1. 在当前库中标记为新领域 2. 放入待归域稍后处理")
        # Hint that prepare-only mode can reveal cross-domain insights
        compile_mode = report.get("compile_mode", "heuristic")
        if compile_mode == "heuristic":
            lines.append("  -> 使用 prepare-only 模式可获得跨域联想分析")
        lines.append("")

    # Compile quality
    compile_mode = report.get("compile_mode", "heuristic")
    if compile_mode == "heuristic":
        lines.append("编译质量：")
        lines.append("  . 本次使用启发式提取（非 LLM 编译），brief/source 为原始文本截取")
        lines.append("  -> 建议通过 prepare-only 模式重新编译以获得结构化摘要")
        lines.append("")

    # Auto-detected questions
    if report["new_questions"]:
        lines.append("自动创建的开放问题：")
        for q in report["new_questions"][:3]:
            lines.append(f"  . {q}")
        lines.append("")

    # Stance impacts
    if report["stance_impacts"]:
        lines.append("立场影响：")
        for s in report["stance_impacts"][:3]:
            lines.append(f"  . {s}")
        lines.append("")

    # Related sources
    if report["related_sources_count"] > 0:
        lines.append(f"已有 {report['related_sources_count']} 篇相关来源")
        lines.append("")

    # Knowledge graph
    if report["insights"]:
        lines.append("知识图谱更新：")
        for ins in report["insights"][:2]:
            lines.append(f"  . {ins}")
        lines.append("")

    return "\n".join(lines)