"""Ingest impact report: post-ingestion guidance for the user.

Three-stage architecture (LLM-first):
  collect_ingest_data()   : Phase 1 — mechanical data collection → JSON
  (LLM analysis)          : Phase 2 — LLM determines related sources semantically
  build_ingest_impact_report() : Phase 3 — assemble report from script data + LLM result

Legacy mode (build_ingest_impact_report without LLM result) still works for
backward compatibility but uses mechanical data only — no keyword-based
semantic judgment.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .shared import (
    Article,
    parse_frontmatter,
    section_excerpt,
)


# ─── Phase 1: Mechanical data collection (no semantic judgment) ───────────


def collect_ingest_data(
    vault: Path,
    slug: str,
    title: str,
    compiled_payload: dict | None = None,
) -> dict:
    """Collect vault data for LLM-driven ingest impact analysis.

    Returns structured JSON. The LLM determines related sources semantically
    per references/prompts/ingest_impact.md — this function does NOT judge
    relatedness.
    """
    result = (compiled_payload or {}).get("result", {})

    # 1. New source metadata
    source_path = vault / "wiki" / "sources" / f"{slug}.md"
    new_source: dict = {"slug": slug, "title": title, "domains": [], "quality": "unknown", "compile_mode": "unknown"}
    if source_path.exists():
        meta, body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
        new_source["domains"] = [d.strip().strip('"') for d in meta.get("domains", "").split(",") if d.strip()]
        new_source["quality"] = meta.get("quality", "unknown")
        new_source["compile_mode"] = meta.get("compile_mode", "unknown")

    # 2. All existing sources (mechanical scan — no keyword filtering)
    existing_sources: list[dict] = []
    sources_dir = vault / "wiki" / "sources"
    if sources_dir.exists():
        for spath in sorted(sources_dir.glob("*.md")):
            if spath.stem == slug:
                continue
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            src_domains = [d.strip().strip('"') for d in meta.get("domains", "").split(",") if d.strip()]
            existing_sources.append({
                "slug": f"sources/{spath.stem}",
                "title": meta.get("title", "").strip('"'),
                "domains": src_domains,
                "quality": meta.get("quality", "unknown"),
                "date": meta.get("created_at", meta.get("date", "")),
                "core_summary": section_excerpt(body, "核心摘要")[:300],
            })

    # 3. Compiled payload proposals
    knowledge_proposals = result.get("knowledge_proposals", {})
    open_questions = result.get("open_questions", [])
    cross_domain_insights = result.get("cross_domain_insights", [])
    stance_impacts = result.get("stance_impacts", [])

    # 4. Existing questions from vault
    existing_questions: list[dict] = []
    questions_dir = vault / "wiki" / "questions"
    if questions_dir.exists():
        for qpath in sorted(questions_dir.glob("*.md")):
            text = qpath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            existing_questions.append({
                "stem": qpath.stem,
                "title": meta.get("title", "").strip('"'),
                "status": meta.get("status", "open"),
                "origin_source": meta.get("origin_source", ""),
            })

    # 5. Existing stances from vault
    existing_stances: list[dict] = []
    stances_dir = vault / "wiki" / "stances"
    if stances_dir.exists():
        for spath in sorted(stances_dir.glob("*.md")):
            text = spath.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            existing_stances.append({
                "stem": spath.stem,
                "title": meta.get("title", "").strip('"'),
                "impacts_raw": meta.get("impacts", "")[:500],
            })

    # 6. Recent log activity
    recent_activity: list[str] = []
    log_path = vault / "wiki" / "log.md"
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8")
        entries = re.findall(r"^## \[.+?\] .+$", log_text, re.M)
        recent_activity = entries[-10:]

    return {
        "new_source": new_source,
        "compiled_payload": {
            "knowledge_proposals": knowledge_proposals,
            "open_questions": open_questions,
            "cross_domain_insights": cross_domain_insights,
            "stance_impacts": stance_impacts,
        },
        "existing_sources": existing_sources,
        "existing_questions": existing_questions,
        "existing_stances": existing_stances,
        "recent_activity": recent_activity,
    }


# ─── Phase 3: Assemble report (backward-compatible) ──────────────────────


def build_ingest_impact_report(
    vault: Path,
    slug: str,
    title: str,
    compiled_payload: dict | None,
    compile_mode: str = "failed",
    article: Article | None = None,
    domain_mismatch: dict | None = None,
    brief_pdf_path: str = "",
    delta_count: int = 0,
) -> dict:
    """Build a post-ingestion impact report and next-step suggestions.

    NOTE: This function no longer performs keyword-based related source
    detection. For semantic related source analysis, use collect_ingest_data()
    → LLM per references/prompts/ingest_impact.md.
    """

    report: dict = {
        "title": title,
        "slug": slug,
        "compile_mode": compile_mode,
        "brief_pdf_path": brief_pdf_path,
        "delta_count": delta_count,
        "skeleton": {},
        "claim_confidence_dist": {},
        "top_claims": [],
        "falsification_signals": [],
        "one_sentence": "",
        "content_questions": [],
        "content_topics": [],
        "cross_domain_insights": [],
        "domain_mismatch": domain_mismatch or {},
        "new_questions": [],
        "answered_questions": [],
        "stance_impacts": [],
        "existing_sources_count": 0,
        "domain_hint": "",
        "insights": [],
    }

    # Prefer LLM-compiled data over heuristic extraction
    result = (compiled_payload or {}).get("result", {})

    # Extract skeleton from v2 document_outputs.brief
    if compiled_payload and compiled_payload.get("schema_version") == "2.0":
        doc_outputs = result.get("document_outputs", {}) if isinstance(result, dict) else {}
        brief_data = doc_outputs.get("brief", {}) if isinstance(doc_outputs, dict) else {}
        if isinstance(brief_data, dict):
            report["one_sentence"] = brief_data.get("one_sentence", "")
            skeleton = brief_data.get("skeleton", {})
            if isinstance(skeleton, dict):
                generators = skeleton.get("generators", [])
                data_points = skeleton.get("data_points", [])
                predict = brief_data.get("predict", {})
                positive_loops = predict.get("positive_loops", []) if isinstance(predict, dict) else []
                negative_loops = predict.get("negative_loops", []) if isinstance(predict, dict) else []
                report["skeleton"] = {
                    "generators": generators[:3] if isinstance(generators, list) else [],
                    "data_points": data_points[:3] if isinstance(data_points, list) else [],
                    "positive_loops": positive_loops[:2] if isinstance(positive_loops, list) else [],
                    "negative_loops": negative_loops[:2] if isinstance(negative_loops, list) else [],
                }
            report["falsification_signals"] = brief_data.get("falsification", [])[:3] if isinstance(brief_data.get("falsification"), list) else []

    # Extract claim confidence distribution and top claims
    claim_inventory = result.get("claim_inventory", []) if isinstance(result, dict) else []
    if isinstance(claim_inventory, list) and claim_inventory:
        _ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}
        dist: dict[str, int] = {}
        for c in claim_inventory:
            if isinstance(c, dict):
                conf = str(c.get("confidence", "")).strip()
                if conf:
                    dist[conf] = dist.get(conf, 0) + 1
        report["claim_confidence_dist"] = dist
        # Top claims: Working+ only, sorted by rank
        actionable = [c for c in claim_inventory if isinstance(c, dict) and _ORDINAL_RANK.get(str(c.get("confidence", "")).strip(), 0) >= 2]
        actionable.sort(key=lambda c: _ORDINAL_RANK.get(str(c.get("confidence", "")).strip(), 0), reverse=True)
        for c in actionable[:4]:
            report["top_claims"].append({
                "claim": c.get("claim", ""),
                "confidence": c.get("confidence", ""),
                "evidence_type": c.get("evidence_type", ""),
            })

    # Questions: from LLM compile only
    if result.get("open_questions"):
        report["content_questions"] = result["open_questions"]

    # Topics: from LLM compile knowledge_proposals only
    proposed_concepts = [
        p["name"]
        for p in (result.get("knowledge_proposals", {}).get("concepts") or [])
        if p.get("action") != "no_page"
    ]
    if proposed_concepts:
        report["content_topics"] = proposed_concepts

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

    # 3. Count existing sources (mechanical — no keyword filtering)
    # For semantic related source analysis, use collect_ingest_data() → LLM
    sources_dir = vault / "wiki" / "sources"
    if sources_dir.exists():
        count = sum(1 for p in sources_dir.glob("*.md") if p.stem != slug)
        report["existing_sources_count"] = count
        # Extract domain hint from the new source's own metadata
        if sources_dir.exists():
            src_path = sources_dir / f"{slug}.md"
            if src_path.exists():
                meta, _ = parse_frontmatter(src_path.read_text(encoding="utf-8"))
                domains_raw = meta.get("domains", "")
                if domains_raw:
                    first_domain = domains_raw.split(",")[0].strip().strip('"')
                    if first_domain:
                        report["domain_hint"] = first_domain
        if not report["domain_hint"]:
            report["domain_hint"] = title[:20]

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
    """Format the impact report as a guided reading experience.

    Design principles:
    - Lead with value: skeleton tells you what the article is about in 10 seconds
    - PDF link for direct access / sharing
    - Reading questions help you think, not just list open problems
    - Maintenance guidance is concrete and actionable, not a single word
    - Confidence distribution gives you a quick quality signal
    """
    slug = report["slug"]
    title = report["title"]
    lines: list[str] = []

    # ━━━ Opening ━━━
    lines.append(f"入库完成：{title}")
    lines.append("")

    # ━━━ 1. Quick access: Obsidian link + PDF ━━━
    lines.append("快速了解：")
    lines.append(f"  [[briefs/{slug}]]")
    pdf_path = report.get("brief_pdf_path", "")
    if pdf_path:
        lines.append(f"  PDF: {pdf_path}")
    lines.append("")

    # ━━━ 2. One-sentence summary ━━━
    one_sentence = report.get("one_sentence", "")
    if one_sentence:
        lines.append(f"一句话：{one_sentence}")
        lines.append("")

    # ━━━ 3. Skeleton: the article's causal backbone ━━━
    skeleton = report.get("skeleton", {})
    if skeleton:
        lines.append("骨架：")
        generators = skeleton.get("generators", [])
        for gen in generators:
            if isinstance(gen, dict):
                name = gen.get("name", "")
                narrative = gen.get("narrative", "")
                if name and narrative:
                    lines.append(f"  {name} — {narrative}")
        data_points = skeleton.get("data_points", [])
        if data_points:
            lines.append("  锚定数据：")
            for dp in data_points:
                if isinstance(dp, dict):
                    label = dp.get("label", "")
                    value = dp.get("value", "")
                    lines.append(f"    {label}: {value}")
        positive_loops = skeleton.get("positive_loops", [])
        negative_loops = skeleton.get("negative_loops", [])
        if positive_loops or negative_loops:
            lines.append("  推演：")
            for pl in positive_loops:
                if isinstance(pl, dict):
                    loop = pl.get("loop", "")
                    implication = pl.get("implication", "")
                    lines.append(f"    [正反馈] {loop} → {implication}")
            for nl in negative_loops:
                if isinstance(nl, dict):
                    bottleneck = nl.get("bottleneck", "")
                    signal = nl.get("observation_signal", "")
                    lines.append(f"    [负反馈] {bottleneck}，观察信号：{signal}")
        lines.append("")

    # ━━━ 4. Confidence distribution ━━━
    conf_dist = report.get("claim_confidence_dist", {})
    if conf_dist:
        dist_parts = [f"{k}: {v}" for k, v in conf_dist.items() if v > 0]
        if dist_parts:
            lines.append(f"置信分布：{' | '.join(dist_parts)}")
            lines.append("")

    # ━━━ 5. Top claims (reading anchors) ━━━
    top_claims = report.get("top_claims", [])
    if top_claims:
        lines.append("阅读锚点（Working 以上可直接引用）：")
        for c in top_claims[:4]:
            conf = c.get("confidence", "")
            etype = c.get("evidence_type", "")
            text = c.get("claim", "")
            label = f"[{etype}|{conf}]" if etype else f"[{conf}]"
            lines.append(f"  {label} {text}")
        lines.append("")

    # ━━━ 6. Falsification signals (what to watch) ━━━
    falsification = report.get("falsification_signals", [])
    if falsification:
        lines.append("失效信号（如果观测到，需重新评估）：")
        for fc in falsification:
            if isinstance(fc, dict):
                condition = fc.get("condition", "").lstrip("如果").lstrip("，、 ")
                consequence = fc.get("consequence", "")
                lines.append(f"  如果 {condition} → {consequence}")
        lines.append("")

    # ━━━ 7. Reading questions (guide thinking, not just list) ━━━
    questions = report.get("content_questions", [])
    cross_insights = report.get("cross_domain_insights", [])
    if questions or cross_insights:
        lines.append("阅读引导：")
        q_idx = 1
        for q in questions[:2]:
            lines.append(f"  {q_idx}. {q}")
            q_idx += 1
        for insight in cross_insights[:2]:
            question = insight.get("potential_question", "")
            if question:
                lines.append(f"  {q_idx}. {question}")
                q_idx += 1
        if q_idx > 1:
            lines.append("  带着这些问题读 brief，找到答案后可直接对话追问")
            lines.append("")

    # ━━━ 8. Cross-domain insights ━━━
    mismatch = report.get("domain_mismatch", {})
    if cross_insights:
        lines.append("跨域碰撞：")
        for insight in cross_insights[:3]:
            concept = insight.get("mapped_concept", "")
            domain = insight.get("target_domain", "")
            logic = insight.get("bridge_logic", "")
            lines.append(f"  {concept} → {domain}")
            lines.append(f"    \"{logic}\"")
        lines.append("")
    elif mismatch.get("is_mismatch"):
        suggested = mismatch.get("suggested_domain_name", "")
        vault_domains = mismatch.get("vault_domains", [])
        vault_names = "、".join(vault_domains[:5]) if vault_domains else "（空）"
        lines.append(f"领域匹配：此内容与知识库现有领域（{vault_names}）无交叉")
        if suggested:
            lines.append(f"  建议：创建「{suggested}」新领域并归入，或放入待归域稍后处理")
        lines.append("")

    # ━━━ 9. Maintenance guidance (concrete, actionable) ━━━
    delta_count = report.get("delta_count", 0)
    stance_impacts = report.get("stance_impacts", [])
    maintenance_items = []
    if delta_count > 0:
        maintenance_items.append(f"审核 {delta_count} 个 delta 提案 → 说 'review' 查看")
    if falsification:
        maintenance_items.append("跟踪失效信号：如观测到上述条件成立，更新 brief 判断")
    if cross_insights:
        maintenance_items.append("跨域关联已建立，后续入库相关内容时会自动链接")
    if stance_impacts:
        stance_desc = "、".join(s[:20] for s in stance_impacts[:2])
        maintenance_items.append(f"立场影响：{stance_desc}，后续可查看 stance 页面追踪")
    if maintenance_items:
        lines.append("维护建议：")
        for item in maintenance_items:
            lines.append(f"  · {item}")
        lines.append("")

    # ━━━ 10. Auto-created questions ━━━
    if report["new_questions"]:
        lines.append("自动创建的开放问题：")
        for q in report["new_questions"][:3]:
            lines.append(f"  · {q}")
        lines.append("")

    # ━━━ 11. Knowledge graph changes ━━━
    topics = report.get("content_topics", [])
    if topics:
        lines.append("知识图谱变更：")
        lines.append(f"  新建概念：{', '.join(topics[:5])}")
    count = report.get("existing_sources_count", 0)
    if count > 0:
        lines.append(f"  知识库来源总数：{count}")
    if report["insights"]:
        for ins in report["insights"][:2]:
            lines.append(f"  {ins}")
    lines.append("")

    # ━━━ 12. Compile quality (only if failed) ━━━
    compile_mode = report.get("compile_mode", "failed")
    if compile_mode == "failed":
        lines.append("编译质量：LLM 编译失败，未生成 brief/source 页面。请检查 LLM 配置后重试。")
        lines.append("")

    return "\n".join(lines)


def format_ingest_dialogue(
    report: dict,
    compiled_payload: dict | None = None,
    fact_inventory: dict | None = None,
) -> str:
    """Format ingest results as a guided dialogue to drive user engagement.

    NOTE: This function is not currently called by ingest_orchestrator.
    It is retained for potential direct-use in interactive dialogue scenarios.
    The orchestrator uses build_ingest_impact_report() + format_ingest_report().

    Unlike format_ingest_report (which is a static summary), this function
    produces a conversational output that:
    1. Presents key findings with evidence anchors
    2. Highlights surprising cross-domain connections
    3. Proposes concrete next actions the user can take
    4. Offers deep-dive entry points
    """
    lines: list[str] = []
    result = (compiled_payload or {}).get("result", {})

    # --- Opening: what we learned ---
    brief = result.get("document_outputs", {}).get("brief", {}) if isinstance(result, dict) else {}
    one_sentence = brief.get("one_sentence", "") if isinstance(brief, dict) else ""
    if one_sentence:
        lines.append(f"核心判断：{one_sentence}")
        lines.append("")

    # --- Evidence-anchored key points ---
    claim_inventory = result.get("claim_inventory", []) if isinstance(result, dict) else []
    if isinstance(claim_inventory, list) and claim_inventory:
        lines.append("关键证据点：")
        for claim in claim_inventory[:3]:
            if not isinstance(claim, dict):
                continue
            text = claim.get("claim", "")
            evidence_type = claim.get("evidence_type", "")
            confidence = claim.get("confidence", "")
            grounding = claim.get("grounding_quote", "")
            tag = f"[{evidence_type}|{confidence}]" if evidence_type else f"[{confidence}]"
            lines.append(f"  {tag} {text}")
            if grounding:
                lines.append(f"    原文：\"{grounding[:80]}...\"" if len(grounding) > 80 else f"    原文：\"{grounding}\"")
        lines.append("")

    # --- Fact inventory summary (if two-step mode) ---
    if fact_inventory and isinstance(fact_inventory, dict):
        facts = fact_inventory.get("atomic_facts", [])
        entities = fact_inventory.get("key_entities", [])
        hooks = fact_inventory.get("cross_domain_hooks", [])
        if facts:
            lines.append(f"提取了 {len(facts)} 条原子事实")
            # Show distribution of evidence types
            type_counts: dict[str, int] = {}
            for f in facts:
                if isinstance(f, dict):
                    et = f.get("evidence_type", "unknown")
                    type_counts[et] = type_counts.get(et, 0) + 1
            if type_counts:
                dist = "、".join(f"{k}:{v}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1]))
                lines.append(f"  证据分布：{dist}")
        if entities:
            lines.append(f"  识别 {len(entities)} 个关键实体")
        if hooks:
            lines.append(f"  发现 {len(hooks)} 个跨域迁移点")
        lines.append("")

    # --- Cross-domain insights: the surprising connections ---
    cross_insights = result.get("cross_domain_insights", []) if isinstance(result, dict) else []
    if isinstance(cross_insights, list) and cross_insights:
        lines.append("跨域碰撞（值得深挖）：")
        for insight in cross_insights[:3]:
            if not isinstance(insight, dict):
                continue
            concept = insight.get("mapped_concept", "")
            domain = insight.get("target_domain", "")
            logic = insight.get("bridge_logic", "")
            question = insight.get("potential_question", "")
            lines.append(f"  {concept} -> {domain}")
            lines.append(f"    逻辑：{logic}")
            if question:
                lines.append(f"    -> 可探索：\"{question}\"")
        lines.append("")

    # --- Knowledge proposals: what to create/link ---
    proposals = result.get("knowledge_proposals", {}) if isinstance(result, dict) else {}
    if isinstance(proposals, dict):
        new_pages = []
        link_pages = []
        for kind in ("domains", "concepts", "entities"):
            items = proposals.get(kind, [])
            if not isinstance(items, list):
                continue
            for p in items:
                if not isinstance(p, dict):
                    continue
                name = p.get("name", "")
                action = p.get("action", "")
                confidence = p.get("confidence", "")
                if action in ("create_candidate", "promote_to_official_candidate"):
                    new_pages.append(f"  [{kind[:-1] if kind.endswith('s') else kind}] {name} ({confidence})")
                elif action == "link_existing":
                    link_pages.append(f"  {name}")
        if new_pages:
            lines.append("建议创建的新页面：")
            lines.extend(new_pages[:6])
            lines.append("")
        if link_pages:
            lines.append("建议链接已有页面：")
            lines.extend(link_pages[:5])
            lines.append("")

    # --- Update proposals: what to modify ---
    update_proposals = result.get("update_proposals", []) if isinstance(result, dict) else []
    if isinstance(update_proposals, list) and update_proposals:
        lines.append("建议更新已有页面：")
        for up in update_proposals[:3]:
            if not isinstance(up, dict):
                continue
            target = up.get("target_page", "")
            reason = up.get("reason", "")
            lines.append(f"  {target}")
            if reason:
                lines.append(f"    原因：{reason}")
        lines.append("")

    # --- Action prompts ---
    lines.append("你可以：")
    actions = []
    if cross_insights:
        actions.append("对跨域联想提问（如：这个模式在 X 领域意味着什么？）")
    if proposals:
        actions.append("审核知识提案（确认/修改/拒绝建议的页面）")
    if update_proposals:
        actions.append("审核更新提案（确认/修改 delta 页面）")
    actions.append("对某个论点追问（如：这个判断的依据是什么？）")
    actions.append("要求深度研究（如：对这个话题做一次 deep research）")
    for i, action in enumerate(actions[:5], 1):
        lines.append(f"  {i}. {action}")
    lines.append("")

    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest impact report: data collection and report generation.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--slug", help="Source slug (without sources/ prefix).")
    parser.add_argument("--title", help="Source title.")
    parser.add_argument("--collect-only", action="store_true", help="Phase 1: collect vault data as JSON for LLM analysis.")
    parser.add_argument("--apply", type=Path, dest="apply_json", help="Phase 3: write report from LLM result JSON.")
    parser.add_argument("--output", type=Path, help="Output path for --collect-only JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.slug or not args.title:
        print("Error: --slug and --title are required.")
        return 1

    vault = args.vault.resolve() if args.vault else Path(".")

    if args.collect_only:
        data = collect_ingest_data(vault, args.slug, args.title)
        output = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Ingest collect data written to {args.output}")
        else:
            print(output)
        return 0

    if args.apply_json:
        # Phase 3: read LLM result and produce final report
        llm_result = json.loads(args.apply_json.read_text(encoding="utf-8"))
        report = build_ingest_impact_report(vault, args.slug, args.title, None)
        # Merge LLM-determined related sources into report
        if "related_sources" in llm_result:
            report["related_sources"] = llm_result["related_sources"]
        if "impact" in llm_result:
            report["llm_impact"] = llm_result["impact"]
        if "suggested_next_steps" in llm_result:
            report["suggested_next_steps"] = llm_result["suggested_next_steps"]
        if "summary" in llm_result:
            report["llm_summary"] = llm_result["summary"]

        report_text = format_ingest_report(report)
        print(report_text)

        # Save full report JSON
        if args.output:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\nFull report JSON written to {args.output}")
        return 0

    # Default: generate report without LLM analysis (backward compatible)
    report = build_ingest_impact_report(vault, args.slug, args.title, None)
    print(format_ingest_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
