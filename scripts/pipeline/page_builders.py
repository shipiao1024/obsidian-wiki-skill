"""Page content generation and file I/O utilities for the obsidian-wiki pipeline."""

from __future__ import annotations

import re
from pathlib import Path

from .types import Article
from .text_utils import top_lines, brief_lead, section_excerpt, plain_text, parse_frontmatter
from .extractors import (
    concept_slug,
    comparison_slug,
    detect_domains,
    domain_slug,
    entity_slug,
    existing_taxonomy_links,
    extract_concepts,
    extract_entities,
    mature_concepts,
)


def merge_links_section(existing_body: str, heading: str, new_links: list[str], fallback_note: str) -> str:
    pattern = re.compile(rf"(##\s+{re.escape(heading)}\s*\n)(.*?)(?=\n##\s+|\Z)", re.S)
    match = pattern.search(existing_body)
    if not match:
        section = [f"## {heading}", ""]
        section.extend(new_links or [fallback_note])
        section.extend(["", ""])
        return existing_body.rstrip() + "\n\n" + "\n".join(section)

    current_body = match.group(2)
    current_links = set(re.findall(r"\[\[[^\]]+\]\]", current_body))
    merged = list(current_links)
    for link in new_links:
        if link not in current_links:
            merged.append(link)
    replacement = match.group(1) + ("\n".join(merged or [fallback_note])) + "\n"
    return existing_body[:match.start()] + replacement + existing_body[match.end():]


def replace_links_section(existing_body: str, heading: str, new_links: list[str], fallback_note: str) -> str:
    pattern = re.compile(rf"(##\s+{re.escape(heading)}\s*\n)(.*?)(?=\n##\s+|\Z)", re.S)
    replacement_body = "\n".join(new_links or [fallback_note]) + "\n"
    match = pattern.search(existing_body)
    if not match:
        section = [f"## {heading}", "", *(new_links or [fallback_note]), "", ""]
        return existing_body.rstrip() + "\n\n" + "\n".join(section)
    replacement = match.group(1) + replacement_body
    return existing_body[:match.start()] + replacement + existing_body[match.end():]


def render_frontmatter(meta: dict[str, str]) -> str:
    return "---\n" + "\n".join(f'{k}: "{v}"' for k, v in meta.items()) + "\n---\n\n"


def build_brief_page(article: Article, slug: str, compile_mode: str = "heuristic") -> str:
    bullets = top_lines(article, limit=7)
    lead = brief_lead(article, bullets)
    is_raw_extract = compile_mode == "heuristic"
    lines = [
        "---",
        f'title: "{article.title} - 快读"',
        'type: "brief"',
        'fidelity: "lossy-summary"',
        'status: "seed"',
        'graph_role: "document"',
        'graph_include: "false"',
        'lifecycle: "official"',
        f'slug: "{slug}"',
    ]
    if is_raw_extract:
        lines.append('compile_quality: "raw-extract"')
    lines.extend([
        f'raw_source: "[[raw/articles/{slug}]]"',
        f'source_page: "[[sources/{slug}]]"',
    ])
    if article.author:
        lines.append(f'author: "{article.author}"')
    if article.date:
        lines.append(f'date: "{article.date}"')
    if article.source:
        lines.append(f'source: "{article.source}"')
    lines.extend(["---", "", f"# {article.title}", ""])
    if is_raw_extract:
        lines.extend([
            "> [!warning] 启发式提取",
            "> 以下内容为原始文本截取，未经结构化编译。建议使用 prepare-only 模式重新入库。",
            "",
        ])
    lines.extend(["## 一句话结论", "", lead, "", "## 核心要点", ""])
    lines.extend(f"- {item}" for item in bullets[:6])
    lines.extend(
        [
            "",
            "## 适合谁读",
            "",
            "- 需要快速了解这篇文章核心判断的人。",
            "- 需要决定是否值得继续读原文的人。",
            "",
            "## 值得回看",
            "",
            "- 文中最关键的论点、定义、对比和判断。",
            "",
            "## 原文入口",
            "",
            f"- [[raw/articles/{slug}]]",
            f"- [[sources/{slug}]]",
        ]
    )
    if article.source:
        lines.append(f"- 来源：{article.source}")
    lines.append("")
    return "\n".join(lines)


def build_brief_page_from_compile(article: Article, slug: str, compiled: dict[str, object]) -> str:
    brief = compiled.get("brief", {}) if isinstance(compiled.get("brief"), dict) else {}
    lead = brief.get("one_sentence", "").strip() if isinstance(brief.get("one_sentence"), str) else ""
    bullets = brief.get("key_points", []) if isinstance(brief.get("key_points"), list) else []
    who_should_read = brief.get("who_should_read", []) if isinstance(brief.get("who_should_read"), list) else []
    why_revisit = brief.get("why_revisit", []) if isinstance(brief.get("why_revisit"), list) else []
    lines = [
        "---",
        f'title: "{article.title} - 快读"',
        'type: "brief"',
        'fidelity: "lossy-summary"',
        'status: "seed"',
        'graph_role: "document"',
        'graph_include: "false"',
        'lifecycle: "official"',
        f'slug: "{slug}"',
        f'confidence: "{article.confidence or "medium"}"',
        f'raw_source: "[[raw/articles/{slug}]]"',
        f'source_page: "[[sources/{slug}]]"',
    ]
    if article.author:
        lines.append(f'author: "{article.author}"')
    if article.date:
        lines.append(f'date: "{article.date}"')
    if article.source:
        lines.append(f'source: "{article.source}"')
    lines.extend(["---", "", f"# {article.title}", "", "## 一句话结论", "", lead or "待人工补充的一句话结论。", "", "## 核心要点", ""])
    lines.extend(f"- {item}" for item in bullets[:7])
    if not bullets:
        lines.append("- 待人工补充。")
    lines.extend(["", "## 适合谁读", ""])
    lines.extend(f"- {item}" for item in who_should_read[:4])
    if not who_should_read:
        lines.append("- 需要快速了解这篇文章核心判断的人。")
    lines.extend(["", "## 值得回看", ""])
    lines.extend(f"- {item}" for item in why_revisit[:4])
    if not why_revisit:
        lines.append("- 文中最关键的论点、定义、对比和判断。")
    lines.extend(["", "## 原文入口", "", f"- [[raw/articles/{slug}]]", f"- [[sources/{slug}]]"])
    if article.source:
        lines.append(f"- 来源：{article.source}")
    lines.append("")
    return "\n".join(lines)


def build_source_page(vault: Path, article: Article, slug: str, compile_mode: str = "heuristic") -> str:
    bullets = top_lines(article, limit=8)
    concepts = extract_concepts(article, limit=8)
    entities = extract_entities(article, limit=8)
    linked_concepts = existing_taxonomy_links(vault, "concepts", concepts, concept_slug)
    linked_entities = existing_taxonomy_links(vault, "entities", entities, entity_slug)
    candidate_concepts = [name for name in concepts if name not in linked_concepts]
    candidate_entities = [name for name in entities if name not in linked_entities]
    domains = detect_domains(article)
    is_raw_extract = compile_mode == "heuristic"
    lines = [
        "---",
        f'title: "{article.title}"',
        'type: "source"',
        'fidelity: "distilled-with-provenance"',
        'status: "seed"',
        'graph_role: "document"',
        'graph_include: "false"',
        'lifecycle: "official"',
        f'slug: "{slug}"',
        f'confidence: "{article.confidence or "medium"}"',
    ]
    if is_raw_extract:
        lines.append('compile_quality: "raw-extract"')
    lines.extend([
        f'raw_source: "[[raw/articles/{slug}]]"',
        f'brief_page: "[[briefs/{slug}]]"',
    ])
    if article.author:
        lines.append(f'author: "{article.author}"')
    if article.date:
        lines.append(f'date: "{article.date}"')
    if article.source:
        lines.append(f'source: "{article.source}"')
    if article.quality:
        lines.append(f'quality: "{article.quality}"')
    lines.extend(
        [
            "---",
            "",
            f"# {article.title}",
            "",
            "## 来源信息",
            "",
            f"- 作者：{article.author or '未知'}",
            f"- 日期：{article.date or '未知'}",
            f"- 原始链接：{article.source or '未知'}",
            f"- 原文页：[[raw/articles/{slug}]]",
            f"- 快读页：[[briefs/{slug}]]",
            "",
        ]
    )
    if is_raw_extract:
        lines.extend([
            "> [!warning] 启发式提取",
            "> 以下内容为原始文本截取，未经结构化编译。建议使用 prepare-only 模式重新入库。",
            "",
        ])
    lines.extend([
            "## 核心摘要",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in bullets[:6])
    lines.extend(
        [
            "",
            "## 相关概念",
            "",
        ]
    )
    lines.extend(f"- [[concepts/{concept_slug(name)}]]" for name in linked_concepts)
    if not linked_concepts:
        lines.append("- 暂无已成熟概念节点。")
    lines.extend(
        [
            "",
            "## 候选概念",
            "",
        ]
    )
    lines.extend(f"- {name}" for name in candidate_concepts)
    if not candidate_concepts:
        lines.append("- 暂无新的候选概念。")
    lines.extend(
        [
            "",
            "## 相关实体",
            "",
        ]
    )
    lines.extend(f"- [[entities/{entity_slug(name)}]]" for name in linked_entities)
    if not linked_entities:
        lines.append("- 暂无已成熟实体节点。")
    lines.extend(
        [
            "",
            "## 候选实体",
            "",
        ]
    )
    lines.extend(f"- {name}" for name in candidate_entities)
    if not candidate_entities:
        lines.append("- 暂无新的候选实体。")
    lines.extend(
        [
            "",
            "## 主题域",
            "",
        ]
    )
    lines.extend(
        f"- [[domains/{domain_slug(name)}]]"
        for name in domains
    )
    lines.extend(
        [
            "",
            "## 与现有知识库的关系",
            "",
            "- 待后续 ingest/query/lint 流程补充交叉链接、冲突和综合结论。",
            "",
            "## 使用建议",
            "",
            "- 快速了解先看本页和 `brief`。",
            "- 需要精确核对时回看 `raw` 原文。",
        ]
    )
    if is_raw_extract:
        lines.extend([
            "- 本页为启发式提取，建议通过 prepare-only 模式重新编译以获得结构化摘要。",
        ])
    lines.extend(["", ""])
    return "\n".join(lines)


def build_source_page_from_compile(vault: Path, article: Article, slug: str, compiled: dict[str, object]) -> str:
    source = compiled.get("source", {}) if isinstance(compiled.get("source"), dict) else {}
    core_summary = source.get("core_summary", []) if isinstance(source.get("core_summary"), list) else []
    concepts = source.get("candidate_concepts", []) if isinstance(source.get("candidate_concepts"), list) else []
    entities = source.get("candidate_entities", []) if isinstance(source.get("candidate_entities"), list) else []
    relation = source.get("knowledge_base_relation", []) if isinstance(source.get("knowledge_base_relation"), list) else []
    contradictions = source.get("contradictions", []) if isinstance(source.get("contradictions"), list) else []
    reinforcements = source.get("reinforcements", []) if isinstance(source.get("reinforcements"), list) else []
    domains = source.get("domains", []) if isinstance(source.get("domains"), list) else []
    domains = [item for item in domains if isinstance(item, str) and item.strip()] or detect_domains(article)
    linked_concepts = existing_taxonomy_links(vault, "concepts", concepts, concept_slug)
    linked_entities = existing_taxonomy_links(vault, "entities", entities, entity_slug)
    candidate_concepts = [name for name in concepts if name not in linked_concepts]
    candidate_entities = [name for name in entities if name not in linked_entities]
    relationship_lines = [f"- {item}" for item in relation[:6]]
    relationship_lines.extend(f"- 强化：{item}" for item in reinforcements[:4])
    relationship_lines.extend(f"- 待验证冲突：{item}" for item in contradictions[:4])
    if not relationship_lines:
        relationship_lines = ["- 待后续 ingest/query/lint 流程补充交叉链接、冲突和综合结论。"]
    lines = [
        "---",
        f'title: "{article.title}"',
        'type: "source"',
        'fidelity: "distilled-with-provenance"',
        'status: "seed"',
        'graph_role: "document"',
        'graph_include: "false"',
        'lifecycle: "official"',
        f'slug: "{slug}"',
        f'confidence: "{article.confidence or "medium"}"',
        f'raw_source: "[[raw/articles/{slug}]]"',
        f'brief_page: "[[briefs/{slug}]]"',
    ]
    if article.author:
        lines.append(f'author: "{article.author}"')
    if article.date:
        lines.append(f'date: "{article.date}"')
    if article.source:
        lines.append(f'source: "{article.source}"')
    if article.quality:
        lines.append(f'quality: "{article.quality}"')
    lines.extend(
        [
            "---",
            "",
            f"# {article.title}",
            "",
            "## 来源信息",
            "",
            f"- 作者：{article.author or '未知'}",
            f"- 日期：{article.date or '未知'}",
            f"- 原始链接：{article.source or '未知'}",
            f"- 原文页：[[raw/articles/{slug}]]",
            f"- 快读页：[[briefs/{slug}]]",
            "",
            "## 核心摘要",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in core_summary[:8])
    if not core_summary:
        lines.append("- 待人工补充。")
    lines.extend(["", "## 相关概念", ""])
    lines.extend(f"- [[concepts/{concept_slug(name)}]]" for name in linked_concepts)
    if not linked_concepts:
        lines.append("- 暂无已成熟概念节点。")
    lines.extend(["", "## 候选概念", ""])
    lines.extend(f"- {name}" for name in candidate_concepts[:10])
    if not candidate_concepts:
        lines.append("- 暂无新的候选概念。")
    lines.extend(["", "## 相关实体", ""])
    lines.extend(f"- [[entities/{entity_slug(name)}]]" for name in linked_entities)
    if not linked_entities:
        lines.append("- 暂无已成熟实体节点。")
    lines.extend(["", "## 候选实体", ""])
    lines.extend(f"- {name}" for name in candidate_entities[:10])
    if not candidate_entities:
        lines.append("- 暂无新的候选实体。")
    lines.extend(["", "## 主题域", ""])
    lines.extend(f"- [[domains/{domain_slug(name)}]]" for name in domains[:3])
    lines.extend(["", "## 与现有知识库的关系", ""])
    lines.extend(relationship_lines)
    lines.extend(["", "## 使用建议", "", "- 快速了解先看本页和 `brief`。", "- 需要精确核对时回看 `raw` 原文。", ""])
    return "\n".join(lines)


def build_concept_page(name: str, source_slug: str, article: Article) -> str:
    return "\n".join(
        [
            "---",
            f'title: "{name}"',
            'type: "concept"',
            'status: "seed"',
            'graph_role: "knowledge"',
            'graph_include: "true"',
            'lifecycle: "official"',
            "---",
            "",
            f"# {name}",
            "",
            "## 定义",
            "",
            "- 待后续 query / lint / 人工复核补充定义。",
            "",
            "## 来自来源",
            "",
            f"- [[sources/{source_slug}]]",
            "",
            "## 相关实体",
            "",
            "- 待补充。",
            "",
            "## 相关主题域",
            "",
            *(f"- [[domains/{domain_slug(domain)}]]" for domain in detect_domains(article)),
            "",
        ]
    )


def build_entity_page(name: str, source_slug: str, article: Article) -> str:
    return "\n".join(
        [
            "---",
            f'title: "{name}"',
            'type: "entity"',
            'status: "seed"',
            'graph_role: "knowledge"',
            'graph_include: "true"',
            'lifecycle: "official"',
            "---",
            "",
            f"# {name}",
            "",
            "## 类型",
            "",
            "- 待补充（人物 / 公司 / 产品 / 方法 / 协议 / 模型）。",
            "",
            "## 来自来源",
            "",
            f"- [[sources/{source_slug}]]",
            "",
            "## 相关概念",
            "",
            "- 待补充。",
            "",
            "## 相关主题域",
            "",
            *(f"- [[domains/{domain_slug(domain)}]]" for domain in detect_domains(article)),
            "",
        ]
    )


def build_domain_page(name: str, source_slug: str) -> str:
    return "\n".join(
        [
            "---",
            f'title: "{name}"',
            'type: "domain"',
            'status: "seed"',
            'graph_role: "knowledge"',
            'graph_include: "true"',
            'lifecycle: "official"',
            "---",
            "",
            f"# {name}",
            "",
            "## 概览",
            "",
            "- 待随着更多来源持续演化。",
            "",
            "## 来源",
            "",
            f"- [[sources/{source_slug}]]",
            "",
            "## 综合分析",
            "",
            f"- [[syntheses/{domain_slug(name)}--综合分析]]",
            "",
            "## 关键概念",
            "",
            "- 待补充。",
            "",
        ]
    )


def build_synthesis_page(vault: Path, name: str, source_slug: str, article: Article) -> str:
    bullets = top_lines(article, limit=4)
    concept_links = [
        f"[[concepts/{concept_slug(concept)}]]"
        for concept in mature_concepts(vault, extract_concepts(article, limit=5))
    ]
    return "\n".join(
        [
            "---",
            f'title: "{name} 综合分析"',
            'type: "synthesis"',
            'status: "seed"',
            'graph_role: "knowledge"',
            'graph_include: "true"',
            'lifecycle: "official"',
            f'domain: "{name}"',
            "---",
            "",
            f"# {name} 综合分析",
            "",
            "## 当前结论",
            "",
            *(f"- {item}" for item in bullets[:3]),
            "",
            "## 近期来源",
            "",
            f"- [[sources/{source_slug}]]",
            "",
            "## 相关概念",
            "",
            *([f"- {link}" for link in concept_links] if concept_links else ["- 待补充。"]),
            "",
            "## 后续维护",
            "",
            "- 新来源进入该主题域时，补充对比、冲突和演化判断。",
            "",
        ]
    )


def build_comparison_page(
    *,
    subject_a: str,
    subject_b: str,
    dimensions: list[str] = [],
    verdict: str = "",
    related_sources: list[str] = [],
    status: str = "seed",
) -> str:
    slug = comparison_slug(f"{subject_a}-vs-{subject_b}")
    dimension_lines = "\n".join(f"- {d}" for d in dimensions) if dimensions else "- （待补充维度）"
    source_lines = "\n".join(f"- [[{s}]]" for s in related_sources) if related_sources else "- （待补充来源）"
    lines = [
        "---",
        f'title: "{subject_a} vs {subject_b}"',
        'type: "comparison"',
        f'status: "{status}"',
        'graph_role: "knowledge"',
        'graph_include: "true"',
        'lifecycle: "official"',
        f'subject_a: "{subject_a}"',
        f'subject_b: "{subject_b}"',
        "---",
        "",
        f"# {subject_a} vs {subject_b}",
        "",
        "## 对比维度",
        dimension_lines,
        "",
        f"## {subject_a} 优势",
        "- （待补充）",
        "",
        f"## {subject_b} 优势",
        "- （待补充）",
        "",
        "## 综合判断",
        verdict or "- （待形成判断）",
        "",
        "## 相关来源",
        source_lines,
        "",
    ]
    return "\n".join(lines)


def write_page(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        return
    path.write_text(content, encoding="utf-8")


def upsert_page(path: Path, new_content: str) -> None:
    if not path.exists():
        path.write_text(new_content, encoding="utf-8")
        return
    path.write_text(new_content, encoding="utf-8")


def article_output_exists(vault: Path, slug: str) -> bool:
    required_paths = [
        vault / "raw" / "articles" / f"{slug}.md",
        vault / "wiki" / "sources" / f"{slug}.md",
        vault / "wiki" / "briefs" / f"{slug}.md",
    ]
    return all(path.exists() for path in required_paths)
