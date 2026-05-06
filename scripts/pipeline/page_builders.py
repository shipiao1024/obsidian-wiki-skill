"""Page content generation and file I/O utilities for the obsidian-wiki pipeline.

Heuristic page generation (build_brief_page, build_source_page) removed in V2.0.
All intelligent extraction is handled by LLM compile v2.
"""

from __future__ import annotations

import re
from pathlib import Path

from .pipeline_types import Article
from .text_utils import top_lines, brief_lead, section_excerpt, plain_text, parse_frontmatter
from .extractors import (
    concept_slug,
    comparison_slug,
    domain_slug,
    entity_slug,
    existing_taxonomy_links,
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


# ---------------------------------------------------------------------------
# Confidence distribution helpers (ordinal model)
# ---------------------------------------------------------------------------

_ORDINAL_LEVELS = ("Seeded", "Preliminary", "Working", "Supported", "Stable")


def _conf_dist_from_claims(claim_inventory: list) -> dict[str, int]:
    """Count claims by ordinal confidence level."""
    dist = {level: 0 for level in _ORDINAL_LEVELS}
    for ci in claim_inventory:
        if isinstance(ci, dict):
            c = ci.get("confidence", "").strip() if isinstance(ci.get("confidence"), str) else ""
            if c in dist:
                dist[c] += 1
    return dist


def _is_actionable_confidence(conf: str) -> bool:
    """Check if a confidence level is actionable (Working or above)."""
    return conf in ("Working", "Supported", "Stable")


_ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}


def auto_graph_include(
    page_type: str,
    lifecycle: str = "",
    confidence: str = "",
    graph_role: str = "",
) -> str:
    """Automatically determine graph_include based on page properties.

    Rules:
    - Always include: concepts, entities, domains (knowledge nodes)
    - Include if lifecycle >= official: syntheses, comparisons
    - Include if confidence >= Working: briefs, sources
    - Exclude: deltas, outputs, questions (working artifacts)
    - Exclude: candidate lifecycle with Seeded/Preliminary confidence

    Returns "true" or "false" for Obsidian frontmatter.
    """
    # Knowledge taxonomy pages are always included
    if page_type in ("concept", "entity", "domain"):
        return "true"

    # Syntheses and comparisons need official+ lifecycle
    if page_type in ("synthesis", "comparison"):
        if lifecycle in ("official", "stable"):
            return "true"
        return "false"

    # Briefs and sources: include if confidence is Working+
    if page_type in ("brief", "source"):
        rank = _ORDINAL_RANK.get(confidence, 0)
        if rank >= 2:  # Working or above
            return "true"
        return "false"

    # Working artifacts: exclude from main graph
    if page_type in ("delta", "output", "question", "stance"):
        return "false"

    # Graph role hint
    if graph_role == "knowledge":
        return "true"
    if graph_role in ("document", "working"):
        # Only include documents with sufficient confidence
        rank = _ORDINAL_RANK.get(confidence, 0)
        return "true" if rank >= 2 else "false"

    # Default: include
    return "true"


# ---------------------------------------------------------------------------
# Brief page from compile (LLM-generated, the only brief path)
# ---------------------------------------------------------------------------

def build_brief_page_from_compile(
    article: Article,
    slug: str,
    compiled: dict[str, object],
    lifecycle: str = "official",
    cross_domain_insights: list | None = None,
    article_type: str = "",
) -> str:
    brief = compiled.get("brief", {}) if isinstance(compiled.get("brief"), dict) else {}
    lead = brief.get("one_sentence", "").strip() if isinstance(brief.get("one_sentence"), str) else ""
    # --- 4-dimension fields ---
    # Skeleton: support both structured dict ({generators, diagram}) and plain markdown string
    skeleton_raw = brief.get("skeleton", {})
    skeleton_narrative = ""
    if isinstance(skeleton_raw, str) and skeleton_raw.strip():
        skeleton_narrative = skeleton_raw.strip()
        skeleton_data = {}
    elif isinstance(skeleton_raw, dict):
        skeleton_data = skeleton_raw
    else:
        skeleton_data = {}
    generators = skeleton_data.get("generators", []) if isinstance(skeleton_data.get("generators"), list) else []
    diagram = skeleton_data.get("diagram", "") if isinstance(skeleton_data.get("diagram"), str) else ""
    # Data: support both data_points (canonical) and data (alternate LLM field name)
    data_points = brief.get("data_points", []) if isinstance(brief.get("data_points"), list) else []
    if not data_points:
        alt_data = brief.get("data", [])
        if isinstance(alt_data, list) and alt_data and all(isinstance(dp, dict) for dp in alt_data):
            data_points = alt_data
    # Predict: support both predict (canonical) and inference (alternate)
    predict = brief.get("predict", {}) if isinstance(brief.get("predict"), dict) else {}
    if not predict:
        alt_inference = brief.get("inference", {})
        if isinstance(alt_inference, dict):
            predict = alt_inference
    positive_loops = predict.get("positive_loops", []) if isinstance(predict.get("positive_loops"), list) else []
    negative_loops = predict.get("negative_loops", []) if isinstance(predict.get("negative_loops"), list) else []
    # Inference alternate format: {positive_feedback: str, negative_feedback: str}
    positive_feedback_str = predict.get("positive_feedback", "") if isinstance(predict.get("positive_feedback"), str) else ""
    negative_feedback_str = predict.get("negative_feedback", "") if isinstance(predict.get("negative_feedback"), str) else ""
    falsification = brief.get("falsification", []) if isinstance(brief.get("falsification"), list) else []
    if not falsification:
        alt_failure = brief.get("failure_signals", [])
        if isinstance(alt_failure, list):
            falsification = [{"condition": fs, "consequence": ""} for fs in alt_failure if isinstance(fs, str)]
    # --- enhanced fields ---
    methodology_eval = brief.get("methodology_evaluation", {}) if isinstance(brief.get("methodology_evaluation"), dict) else {}
    if not methodology_eval:
        alt_method = brief.get("methodology_assessment", {})
        if isinstance(alt_method, dict):
            methodology_eval = alt_method
    hidden_assumptions = brief.get("hidden_assumptions", []) if isinstance(brief.get("hidden_assumptions"), list) else []
    who_should_read = brief.get("who_should_read", []) if isinstance(brief.get("who_should_read"), list) else []
    why_revisit = brief.get("why_revisit", []) if isinstance(brief.get("why_revisit"), list) else []
    # --- legacy key_points fallback (for old compile output) ---
    key_points = brief.get("key_points", []) if isinstance(brief.get("key_points"), list) else []
    claim_inventory = compiled.get("claim_inventory", []) if isinstance(compiled.get("claim_inventory"), list) else []
    conf_dist = _conf_dist_from_claims(claim_inventory)

    lines = [
        "---",
        f'title: "{article.title} - 简报"',
        'type: "brief"',
        'fidelity: "cognitive-compression"',
        f'status: "{"candidate" if lifecycle == "candidate" else "seed"}"',
        'graph_role: "document"',
        'graph_include: "false"',
        f'lifecycle: "{lifecycle}"',
        f'slug: "{slug}"',
        f'confidence: "{article.confidence or "Working"}"',
    ]
    # Add ordinal confidence distribution
    for level in _ORDINAL_LEVELS:
        if conf_dist[level] > 0:
            lines.append(f'claim_confidence_{level.lower()}: "{conf_dist[level]}"')
    lines.extend([
        f'one_sentence: "{lead}"',
        f'raw_source: "[[raw/articles/{slug}]]"',
        f'source_page: "[[sources/{slug}]]"',
    ])
    if article.author:
        lines.append(f'author: "{article.author}"')
    if article.date:
        lines.append(f'date: "{article.date}"')
    if article.source:
        lines.append(f'source: "{article.source}"')
    if article_type:
        lines.append(f'article_type: "{article_type}"')
    lines.extend(["---", "", f"# {article.title}", ""])
    if lifecycle == "candidate":
        lines.extend([
            "> [!warning] 候选页待审",
            "> 本页包含低置信判断，尚未通过人工审核。引用时请标注置信度。",
            "",
        ])
    # --- 骨架 ---
    lines.extend(["## 骨架", ""])
    if skeleton_narrative:
        lines.append(skeleton_narrative)
    elif generators:
        for gen in generators:
            if isinstance(gen, dict):
                name = gen.get("name", "")
                narrative = gen.get("narrative", "")
                if name and narrative:
                    lines.append(f"**{name}**：{narrative}")
                elif narrative:
                    lines.append(f"- {narrative}")
                elif name:
                    lines.append(f"- {name}")
        if diagram:
            lines.extend(["", "```", diagram.strip(), "```"])
    elif key_points:
        for kp in key_points[:4]:
            lines.append(f"- {kp}")
    else:
        lines.append("- 待补充因果骨架。")
    lines.append("")
    # --- 数据 ---
    lines.extend(["## 数据", ""])
    if data_points:
        lines.extend([
            "| 指标 | 数值 | 基准 |",
            "|---|---|---|",
        ])
        for dp in data_points:
            if isinstance(dp, dict):
                label = dp.get("label", "")
                value = dp.get("value", "")
                baseline = dp.get("baseline", "")
                lines.append(f"| {label} | {value} | {baseline} |")
    elif key_points:
        for kp in key_points[:5]:
            lines.append(f"- {kp}")
    else:
        lines.append("- 待补充锚定数据。")
    lines.append("")
    # --- 推演 ---
    lines.extend(["## 推演", ""])
    has_predict = False
    for pl in positive_loops:
        if isinstance(pl, dict):
            loop = pl.get("loop", "")
            implication = pl.get("implication", "")
            lines.append(f"> **正反馈（加速）**：{loop}——{implication}")
            has_predict = True
    for nl in negative_loops:
        if isinstance(nl, dict):
            bottleneck = nl.get("bottleneck", "")
            signal = nl.get("observation_signal", "")
            lines.append(f"> **负反馈（拐点）**：{bottleneck}。**观察信号**：{signal}")
            has_predict = True
    if positive_feedback_str:
        lines.append(f"> **正反馈**：{positive_feedback_str}")
        has_predict = True
    if negative_feedback_str:
        lines.append(f"> **负反馈**：{negative_feedback_str}")
        has_predict = True
    if not has_predict:
        lines.append("- 待补充正负反馈与拐点。")
    lines.append("")
    # --- 失效信号 ---
    lines.extend(["## 失效信号", ""])
    if falsification:
        for i, fc in enumerate(falsification, 1):
            if isinstance(fc, dict):
                condition = fc.get("condition", "").lstrip("如果").lstrip("，、 ")
                consequence = fc.get("consequence", "")
                lines.append(f"{i}. **如果** {condition}，**则** {consequence}")
    else:
        lines.append("- 待补充可观测失效条件。")
    lines.append("")
    # --- 方法论评估（条件渲染） ---
    if methodology_eval and isinstance(methodology_eval, dict):
        approach = methodology_eval.get("approach", "") or methodology_eval.get("method", "")
        strengths = methodology_eval.get("strengths", []) if isinstance(methodology_eval.get("strengths"), list) else []
        limitations = methodology_eval.get("limitations", []) if isinstance(methodology_eval.get("limitations"), list) else []
        alternatives = methodology_eval.get("alternatives", "") or methodology_eval.get("alternative", "")
        if approach:
            lines.extend(["## 方法论评估", ""])
            lines.append(f"**方法**：{approach}")
            lines.append("")
            if strengths:
                lines.append("**优势**：")
                for s in strengths:
                    lines.append(f"- {s}")
                lines.append("")
            if limitations:
                lines.append("**局限**：")
                for l in limitations:
                    lines.append(f"- {l}")
                lines.append("")
            if alternatives:
                lines.append(f"**替代方案**：{alternatives}")
                lines.append("")
    # --- 关键判断 ---
    if claim_inventory:
        # Separate assumptions from other claims
        assumption_claims = [ci for ci in claim_inventory if isinstance(ci, dict) and ci.get("evidence_type", "").strip() == "assumption"]
        other_claims = [ci for ci in claim_inventory if isinstance(ci, dict) and ci.get("evidence_type", "").strip() != "assumption"]
        actionable = [ci for ci in other_claims if _is_actionable_confidence(ci.get("confidence", ""))]
        non_actionable = [ci for ci in other_claims if not _is_actionable_confidence(ci.get("confidence", ""))]
        lines.extend(["## 关键判断", ""])
        lines.append("> 判断标注证据类型和置信度。[Working]以上可直接引用；[Preliminary]及以下需交叉验证。")
        lines.append("")
        for ci in actionable[:8]:
            if not isinstance(ci, dict):
                continue
            ct = ci.get("claim_type", "interpretation").strip() if isinstance(ci.get("claim_type"), str) else "interpretation"
            etype = ci.get("evidence_type", "").strip() if isinstance(ci.get("evidence_type"), str) else ""
            conf = ci.get("confidence", "Working").strip() if isinstance(ci.get("confidence"), str) else "Working"
            text = ci.get("claim", "").strip() if isinstance(ci.get("claim"), str) else ""
            marker = " ⚠️需验证" if ci.get("verification_needed") else ""
            logic_risk = ci.get("logic_risk", "none").strip() if isinstance(ci.get("logic_risk"), str) else "none"
            risk_marker = f" ⚡{logic_risk}" if logic_risk and logic_risk != "none" else ""
            label = f"{etype}|{conf}" if etype else f"{ct}|{conf}"
            if text:
                lines.append(f"- [{label}] {text}{marker}{risk_marker}")
        if not actionable:
            lines.append("- 无可直接引用的判断。")
        lines.append("")
        if lifecycle == "candidate" and non_actionable:
            lines.extend(["## 待验证判断", ""])
            lines.append("> 以下判断置信度不足，需更多来源验证。")
            lines.append("")
            for ci in non_actionable[:8]:
                if not isinstance(ci, dict):
                    continue
                ct = ci.get("claim_type", "interpretation").strip() if isinstance(ci.get("claim_type"), str) else "interpretation"
                etype = ci.get("evidence_type", "").strip() if isinstance(ci.get("evidence_type"), str) else ""
                conf = ci.get("confidence", "Preliminary").strip() if isinstance(ci.get("confidence"), str) else "Preliminary"
                text = ci.get("claim", "").strip() if isinstance(ci.get("claim"), str) else ""
                marker = " ⚠️需验证" if ci.get("verification_needed") else ""
                label = f"{etype}|{conf}" if etype else f"{ct}|{conf}"
                if text:
                    lines.append(f"- [{label}] {text}{marker}")
            lines.append("")
        elif not lifecycle == "candidate" and non_actionable:
            for ci in non_actionable[:8]:
                if not isinstance(ci, dict):
                    continue
                ct = ci.get("claim_type", "interpretation").strip() if isinstance(ci.get("claim_type"), str) else "interpretation"
                etype = ci.get("evidence_type", "").strip() if isinstance(ci.get("evidence_type"), str) else ""
                conf = ci.get("confidence", "Preliminary").strip() if isinstance(ci.get("confidence"), str) else "Preliminary"
                text = ci.get("claim", "").strip() if isinstance(ci.get("claim"), str) else ""
                marker = " ⚠️需验证" if ci.get("verification_needed") else ""
                label = f"{etype}|{conf}" if etype else f"{ct}|{conf}"
                if text:
                    lines.append(f"- [{label}] {text}{marker}")
        # --- 隐性假设（单独分组） ---
        if assumption_claims or hidden_assumptions:
            lines.extend(["## 隐性假设", ""])
            lines.append("> 作者未明说但论证依赖的前提。如果这些假设不成立，结论需要重新评估。")
            lines.append("")
            for ci in assumption_claims[:5]:
                if not isinstance(ci, dict):
                    continue
                text = ci.get("claim", "").strip() if isinstance(ci.get("claim"), str) else ""
                conf = ci.get("confidence", "Preliminary").strip() if isinstance(ci.get("confidence"), str) else "Preliminary"
                if text:
                    lines.append(f"- [{conf}] {text}")
            for ha in hidden_assumptions[:5]:
                if isinstance(ha, str) and ha.strip():
                    lines.append(f"- {ha.strip()}")
            lines.append("")
    else:
        lines.extend(["## 关键判断", ""])
        lines.append("- 待 LLM 编译补充关键判断。")
        lines.append("")
    # --- 跨域联想 ---
    if cross_domain_insights and isinstance(cross_domain_insights, list):
        valid_insights = [i for i in cross_domain_insights if isinstance(i, dict) and i.get("mapped_concept") and i.get("bridge_logic")]
        if valid_insights:
            lines.extend(["## 跨域联想", ""])
            for insight in valid_insights[:5]:
                concept = insight.get("mapped_concept", "")
                domain = insight.get("target_domain", "")
                logic = insight.get("bridge_logic", "")
                lines.append(f"- **{concept}** → {domain}：{logic}")
            lines.append("")
    # --- 适合谁读 ---
    if who_should_read:
        lines.extend(["## 适合谁读", ""])
        for reader in who_should_read[:3]:
            if isinstance(reader, str) and reader.strip():
                lines.append(f"- {reader.strip()}")
        lines.append("")
    # --- 为什么值得重访 ---
    if why_revisit:
        lines.extend(["## 为什么值得重访", ""])
        for reason in why_revisit[:2]:
            if isinstance(reason, str) and reason.strip():
                lines.append(f"- {reason.strip()}")
        lines.append("")
    # --- 原文入口 ---
    lines.extend(["## 原文入口", "", f"- [[raw/articles/{slug}]]", f"- [[sources/{slug}]]"])
    if article.source and article.source.startswith("http"):
        lines.append(f"- [原文链接]({article.source})")
    elif article.source:
        lines.append(f"- 来源：{article.source}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Source page from compile (LLM-generated, the only source path)
# ---------------------------------------------------------------------------

def build_source_page_from_compile(vault: Path, article: Article, slug: str, compiled: dict[str, object], lifecycle: str = "official") -> str:
    source = compiled.get("source", {}) if isinstance(compiled.get("source"), dict) else {}
    core_summary = source.get("core_summary", []) if isinstance(source.get("core_summary"), list) else []
    concepts = source.get("candidate_concepts", []) if isinstance(source.get("candidate_concepts"), list) else []
    entities = source.get("candidate_entities", []) if isinstance(source.get("candidate_entities"), list) else []
    relation = source.get("knowledge_base_relation", []) if isinstance(source.get("knowledge_base_relation"), list) else []
    contradictions = source.get("contradictions", []) if isinstance(source.get("contradictions"), list) else []
    reinforcements = source.get("reinforcements", []) if isinstance(source.get("reinforcements"), list) else []
    domains = source.get("domains", []) if isinstance(source.get("domains"), list) else []
    domains = [item for item in domains if isinstance(item, str) and item.strip()]
    linked_concepts = existing_taxonomy_links(vault, "concepts", concepts, concept_slug)
    linked_entities = existing_taxonomy_links(vault, "entities", entities, entity_slug)
    candidate_concepts = [name for name in concepts if name not in linked_concepts]
    candidate_entities = [name for name in entities if name not in linked_entities]
    relationship_lines = [f"- {item}" for item in relation[:6]]
    relationship_lines.extend(f"- 强化：{item}" for item in reinforcements[:4])
    relationship_lines.extend(f"- 待验证冲突：{item}" for item in contradictions[:4])
    if not relationship_lines:
        relationship_lines = ["- 待后续 ingest/query/lint 流程补充交叉链接、冲突和综合结论。"]
    claim_inventory = compiled.get("claim_inventory", []) if isinstance(compiled.get("claim_inventory"), list) else []
    conf_dist = _conf_dist_from_claims(claim_inventory)

    lines = [
        "---",
        f'title: "{article.title}"',
        'type: "source"',
        'fidelity: "distilled-with-provenance"',
        f'status: "{"candidate" if lifecycle == "candidate" else "seed"}"',
        'graph_role: "document"',
        'graph_include: "false"',
        f'lifecycle: "{lifecycle}"',
        f'slug: "{slug}"',
        f'confidence: "{article.confidence or "Working"}"',
    ]
    # Add ordinal confidence distribution
    for level in _ORDINAL_LEVELS:
        if conf_dist[level] > 0:
            lines.append(f'claim_confidence_{level.lower()}: "{conf_dist[level]}"')
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
        ]
    )
    if lifecycle == "candidate":
        lines.extend([
            "> [!warning] 候选页待审",
            "> 本页包含低置信判断，尚未通过人工审核。引用时请标注置信度。",
            "",
        ])
    lines.extend([
        "## 来源信息",
        "",
        f"- 作者：{article.author or '未知'}",
        f"- 日期：{article.date or '未知'}",
        f"- 原始链接：{article.source or '未知'}",
        f"- 原文页：[[raw/articles/{slug}]]",
        f"- 快读页/简报页：[[briefs/{slug}]]",
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
    lines.extend(["", "## 关键判断", ""])
    if claim_inventory:
        actionable = [ci for ci in claim_inventory if isinstance(ci, dict) and _is_actionable_confidence(ci.get("confidence", ""))]
        non_actionable = [ci for ci in claim_inventory if isinstance(ci, dict) and not _is_actionable_confidence(ci.get("confidence", ""))]
        lines.append("> 判断标注证据类型和置信度。[Working]以上可沉淀至概念/综合页；[Preliminary]及以下需更多来源验证。")
        lines.append("")
        for ci in actionable[:8]:
            if not isinstance(ci, dict):
                continue
            ct = ci.get("claim_type", "interpretation").strip() if isinstance(ci.get("claim_type"), str) else "interpretation"
            etype = ci.get("evidence_type", "").strip() if isinstance(ci.get("evidence_type"), str) else ""
            conf = ci.get("confidence", "Working").strip() if isinstance(ci.get("confidence"), str) else "Working"
            text = ci.get("claim", "").strip() if isinstance(ci.get("claim"), str) else ""
            marker = " ⚠️需验证" if ci.get("verification_needed") else ""
            label = f"{etype}|{conf}" if etype else f"{ct}|{conf}"
            if text:
                lines.append(f"- [{label}] {text}{marker}")
        if not actionable:
            lines.append("- 无可直接引用的判断。")
        lines.append("")
        if lifecycle == "candidate" and non_actionable:
            lines.extend(["## 待验证判断", ""])
            lines.append("> 以下判断置信度不足，需更多来源验证。")
            lines.append("")
            for ci in non_actionable[:8]:
                if not isinstance(ci, dict):
                    continue
                ct = ci.get("claim_type", "interpretation").strip() if isinstance(ci.get("claim_type"), str) else "interpretation"
                etype = ci.get("evidence_type", "").strip() if isinstance(ci.get("evidence_type"), str) else ""
                conf = ci.get("confidence", "Preliminary").strip() if isinstance(ci.get("confidence"), str) else "Preliminary"
                text = ci.get("claim", "").strip() if isinstance(ci.get("claim"), str) else ""
                marker = " ⚠️需验证" if ci.get("verification_needed") else ""
                label = f"{etype}|{conf}" if etype else f"{ct}|{conf}"
                if text:
                    lines.append(f"- [{label}] {text}{marker}")
            lines.append("")
        elif not lifecycle == "candidate" and non_actionable:
            for ci in non_actionable[:8]:
                if not isinstance(ci, dict):
                    continue
                ct = ci.get("claim_type", "interpretation").strip() if isinstance(ci.get("claim_type"), str) else "interpretation"
                etype = ci.get("evidence_type", "").strip() if isinstance(ci.get("evidence_type"), str) else ""
                conf = ci.get("confidence", "Preliminary").strip() if isinstance(ci.get("confidence"), str) else "Preliminary"
                text = ci.get("claim", "").strip() if isinstance(ci.get("claim"), str) else ""
                marker = " ⚠️需验证" if ci.get("verification_needed") else ""
                label = f"{etype}|{conf}" if etype else f"{ct}|{conf}"
                if text:
                    lines.append(f"- [{label}] {text}{marker}")
    else:
        lines.append("- 待 LLM 编译补充关键判断。")
    lines.extend(["", "## 使用建议", "", "- 快速了解先看本页和 `brief`。", "- 需要精确核对时回看 `raw` 原文。", ""])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Knowledge pages (concept, entity, domain, synthesis, comparison)
# ---------------------------------------------------------------------------

def build_concept_page(name: str, source_slug: str, domains: list[str] | None = None, definition: str = "", related_entities: list[str] | None = None) -> str:
    """Build a concept page. Domains should come from LLM compile, not script detection."""
    domain_links = []
    if domains:
        domain_links = [f"- [[domains/{domain_slug(domain)}]]" for domain in domains]
    else:
        domain_links = ["- 待补充。"]
    entity_links = []
    if related_entities:
        entity_links = [f"- [[entities/{entity_slug(e)}]]" for e in related_entities]
    else:
        entity_links = ["- 待补充。"]
    definition_text = definition.strip() if definition and definition.strip() else "- 待后续 query / lint / 人工复核补充定义。"
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
            definition_text,
            "",
            "## 来自来源",
            "",
            f"- [[sources/{source_slug}]]",
            "",
            "## 相关实体",
            "",
            *entity_links,
            "",
            "## 相关主题域",
            "",
            *domain_links,
            "",
        ]
    )


def build_entity_page(name: str, source_slug: str, domains: list[str] | None = None, definition: str = "", related_concepts: list[str] | None = None) -> str:
    """Build an entity page. Domains should come from LLM compile, not script detection."""
    domain_links = []
    if domains:
        domain_links = [f"- [[domains/{domain_slug(domain)}]]" for domain in domains]
    else:
        domain_links = ["- 待补充。"]
    concept_links = []
    if related_concepts:
        concept_links = [f"- [[concepts/{concept_slug(c)}]]" for c in related_concepts]
    else:
        concept_links = ["- 待补充。"]
    definition_text = definition.strip() if definition and definition.strip() else "- 待补充（人物 / 公司 / 产品 / 方法 / 协议 / 模型）。"
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
            definition_text,
            "",
            "## 来自来源",
            "",
            f"- [[sources/{source_slug}]]",
            "",
            "## 相关概念",
            "",
            *concept_links,
            "",
            "## 相关主题域",
            "",
            *domain_links,
            "",
        ]
    )


def build_domain_page(name: str, source_slug: str, *, definition: str = "", concept_names: list[str] | None = None, entity_names: list[str] | None = None) -> str:
    overview = definition or "待随着更多来源持续演化。"
    concept_links = [f"- [[concepts/{concept_slug(c)}]]" for c in (concept_names or [])] or ["- 待补充。"]
    entity_links = [f"- [[entities/{entity_slug(e)}]]" for e in (entity_names or [])] or ["- 待补充。"]
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
            overview,
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
            *concept_links,
            "",
            "## 相关实体",
            "",
            *entity_links,
            "",
        ]
    )


# Ordinal confidence weights for synthesis claim ranking
_ORDINAL_WEIGHT = {"Seeded": 1, "Preliminary": 2, "Working": 4, "Supported": 6, "Stable": 8}

# Pattern matches both old [ct|conf] and new [etype|conf] formats
CLAIM_PATTERN = re.compile(r"^- \[([^\]|]+)\|([^\]]+)\]\s+(.+)$", re.M)


def _extract_claims_from_source(source_path: Path) -> list[dict[str, str]]:
    text = source_path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    section = ""
    pattern = re.compile(r"##\s+关键判断\s*\n(.*?)(?:\n##\s+|\Z)", re.S)
    match = pattern.search(body)
    if match:
        section = match.group(1)
    if not section:
        return []
    claims = []
    for m in CLAIM_PATTERN.finditer(section):
        claim_text = m.group(3).strip().rstrip("⚠️需验证").strip()
        label1 = m.group(1).strip()
        label2 = m.group(2).strip()
        # Determine which label is evidence_type vs confidence
        # New format: [etype|ordinal], old format: [ct|high/medium/low]
        if label2 in _ORDINAL_WEIGHT:
            evidence_type = label1
            confidence = label2
        elif label1 in _ORDINAL_WEIGHT:
            evidence_type = label2
            confidence = label1
        else:
            # Legacy format [ct|high] or unknown
            evidence_type = label1
            confidence = label2
        claims.append({
            "claim_type": evidence_type,
            "confidence": confidence,
            "claim": claim_text,
            "_source": source_path.stem,
        })
    return claims


def _score_claim(claim: dict[str, str], terms: list[str]) -> int:
    score = _ORDINAL_WEIGHT.get(claim.get("confidence", "Preliminary"), 2)
    text = claim.get("claim", "")
    for term in terms:
        if term and term in text:
            score += 4
    return score


def build_synthesis_page(vault: Path, name: str, source_slug: str, article: Article) -> str:
    source_path = vault / "wiki" / "sources" / f"{source_slug}.md"
    all_claims: list[dict[str, str]] = []
    if source_path.exists():
        all_claims = _extract_claims_from_source(source_path)
    terms = re.findall(r"[A-Za-z0-9\-\+]{2,}|[一-鿿]{2,8}", name)

    if all_claims:
        ranked = sorted(all_claims, key=lambda c: _score_claim(c, terms), reverse=True)
        seen = set()
        deduped = []
        for c in ranked:
            if c["claim"] not in seen:
                seen.add(c["claim"])
                deduped.append(c)
        actionable = [c for c in deduped if _is_actionable_confidence(c.get("confidence", ""))]
        lead_parts = [c["claim"].rstrip("。") for c in (actionable or deduped)[:2]]
        lead = f"{lead_parts[0]}。" if len(lead_parts) == 1 else f"{lead_parts[0]}；{lead_parts[1]}。" if lead_parts else "待补充。"
        claim_lines = []
        for c in deduped[:4]:
            conf = c.get("confidence", "Preliminary")
            marker = conf if _is_actionable_confidence(conf) else f"{conf}⚠️"
            src = c.get("_source", "")
            source_link = f" —— [[sources/{src}]]" if src else ""
            claim_lines.append(f"- [{marker}] {c['claim']}{source_link}")
    else:
        bullets = top_lines(article, limit=4)
        lead = "；".join(b.rstrip("。") for b in bullets[:2]) + "。" if bullets else "待补充。"
        claim_lines = [f"- {item}" for item in bullets[:3]]

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
            lead,
            "",
            "## 核心判断",
            "",
            *claim_lines,
            "",
            "## 近期来源",
            "",
            f"- [[sources/{source_slug}]]",
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
        "---",
        "",
        f"# {subject_a} vs {subject_b}",
        "",
        "## 比较维度",
        "",
        dimension_lines,
        "",
        "## 结论",
        "",
        verdict or "- 待补充。",
        "",
        "## 来源",
        "",
        source_lines,
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def write_page(path: Path, content: str, force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def upsert_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def article_output_exists(vault: Path, slug: str) -> bool:
    raw = vault / "raw" / "articles" / f"{slug}.md"
    brief = vault / "wiki" / "briefs" / f"{slug}.md"
    source = vault / "wiki" / "sources" / f"{slug}.md"
    return raw.exists() or brief.exists() or source.exists()
