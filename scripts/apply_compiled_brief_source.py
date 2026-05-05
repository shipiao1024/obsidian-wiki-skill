#!/usr/bin/env python
"""Supporting script for the apply stage in the WeChat Obsidian LLM wiki.

This script accepts a structured compile result and applies it into
official brief/source pages plus review-ready delta drafts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from wiki_ingest_wechat import (
    Article,
    build_brief_page_from_compile,
    build_source_page_from_compile,
    sanitize_filename,
    ensure_synthesis_pages,
    ensure_taxonomy_pages,
    parse_frontmatter,
    rebuild_index,
)
from pipeline.validate_compile import validate_compile_result, grounding_validate, density_check
from pipeline.encoding_fix import fix_windows_encoding


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supporting script for the apply stage: write brief/source from a structured compile result.")
    parser.add_argument("--vault", type=Path, required=True, help="Obsidian vault root.")
    parser.add_argument("--raw", type=Path, default=None, help="Raw article markdown path. If omitted, extracted from compile_target.raw_path in the compiled JSON.")
    parser.add_argument("--compiled-json", type=Path, required=True, help="Structured compile result JSON path.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing brief/source pages.")
    parser.add_argument("--validate-only", action="store_true", help="Only validate the compiled JSON without applying. Checks structure, grounding, and evidence density.")
    return parser.parse_args()


def article_from_raw(raw_path: Path) -> tuple[Article, str]:
    text = raw_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    title = meta.get("title") or raw_path.stem
    article = Article(
        title=title,
        author=meta.get("author", ""),
        date=meta.get("date", ""),
        source=meta.get("source", ""),
        body=body.strip(),
        src_dir=raw_path.parent,
        md_path=raw_path,
    )
    return article, raw_path.stem


def _sanitize_json_text(text: str) -> str:
    """Pre-process JSON text to fix common LLM-generated encoding issues.

    Replaces Chinese/fullwidth quotes that conflict with JSON string delimiters.
    """
    # Replace Chinese double quotes with escaped English quotes
    text = text.replace(""", '\\"').replace(""", '\\"')
    # Replace fullwidth double quotes
    text = text.replace("＂", '\\"')
    return text


def load_compiled_json(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = json.loads(_sanitize_json_text(raw))
    if not isinstance(data, dict):
        raise SystemExit(f"Compiled result must be a JSON object: {path}")
    if "brief" not in data or "source" not in data:
        raise SystemExit(f"Compiled result missing brief/source keys: {path}")
    return data


_EVIDENCE_TYPE_MAP = {
    "observation": "fact", "empirical": "fact", "measurement": "fact", "statistical": "fact",
    "statistic": "fact", "data_point": "fact", "historical_fact": "fact", "direct_observation": "fact",
    "speculation": "hypothesis", "conjecture": "hypothesis", "prediction": "hypothesis",
    "proposed": "hypothesis", "theoretical": "hypothesis", "future_projection": "hypothesis",
    "expert_judgment": "inference", "expert_opinion": "inference", "author_inference": "inference",
    "logical_deduction": "inference", "inductive": "inference", "deductive": "inference",
    "cross_chapter_reinforcement": "inference", "synthesis": "inference", "argument": "inference",
    "reasoning": "inference", "implication": "inference", "extrapolation": "inference",
    "case_study": "inference", "anecdotal": "inference", "analogical": "inference",
    "unsupported": "assumption", "premise": "assumption", "taken_for_granted": "assumption",
    "implicit": "assumption", "axiom": "assumption", "foundational": "assumption",
    "controversial": "disputed", "debated": "disputed", "contradictory": "disputed",
    "challenged": "disputed", "contrary_evidence": "disputed", "opposing_view": "disputed",
    "missing": "gap", "absent": "gap", "unaddressed": "gap", "unknown": "gap",
    "under researched": "gap", "lack_of_evidence": "gap", "open_question": "gap",
}

_IMPACT_MAP = {
    "推翻": "contradict", "否定": "contradict", "反驳": "contradict", "contradiction": "contradict",
    "反对": "contradict", "挑战": "contradict", "conflict": "contradict", "refute": "contradict",
    "修正": "extend", "扩展": "extend", "深化": "extend", "补充": "extend", "细化": "extend",
    "extension": "extend", "refinement": "extend", "elaboration": "extend", "nuance": "extend",
    "支持": "reinforce", "强化": "reinforce", "确认": "reinforce", "验证": "reinforce",
    "reinforcement": "reinforce", "confirmation": "reinforce", "corroboration": "reinforce",
    "中立": "neutral", "无关": "neutral", "independent": "neutral", "parallel": "neutral",
}


def _auto_correct_v2_nesting(data: dict) -> dict:
    """Auto-correct common V2.0 compile JSON nesting and enum errors.

    Modifies data in place and returns it. Logs each correction to stderr.
    """
    corrections = []

    # 1. schema_version inside metadata → move to top level
    if "schema_version" not in data and isinstance(data.get("metadata"), dict):
        sv = data["metadata"].get("schema_version")
        if sv:
            data["schema_version"] = sv
            del data["metadata"]["schema_version"]
            corrections.append("Moved schema_version to top level")

    # 2. If data uses "document_outputs" at top level, wrap into result
    if "document_outputs" in data and "result" not in data:
        result = {"document_outputs": data.pop("document_outputs")}
        for key in ("claim_inventory", "open_questions", "cross_domain_insights",
                     "stance_impacts", "review_hints", "knowledge_proposals",
                     "update_proposals", "compile_target", "metadata"):
            if key in data:
                result[key] = data.pop(key)
        data["result"] = result
        if "schema_version" not in data:
            data["schema_version"] = "2.0"
        corrections.append("Wrapped document_outputs into result")

    result = data.get("result") if isinstance(data.get("result"), dict) else data

    # 3. Move fields from document_outputs to result top level
    doc_out = result.get("document_outputs") if isinstance(result.get("document_outputs"), dict) else None
    if doc_out:
        promoted_keys = ("claim_inventory", "open_questions", "cross_domain_insights",
                         "stance_impacts", "review_hints", "knowledge_proposals", "update_proposals")
        for key in promoted_keys:
            if key in doc_out and key not in result:
                result[key] = doc_out.pop(key)
                corrections.append(f"Promoted {key} from document_outputs to result")

    # 4. Move source from brief to document_outputs (sibling of brief)
    brief = doc_out.get("brief") if isinstance(doc_out, dict) and isinstance(doc_out.get("brief"), dict) else None
    if brief and "source" in brief and isinstance(brief["source"], dict):
        if doc_out is not None:
            doc_out["source"] = brief.pop("source")
            corrections.append("Moved source from brief to document_outputs")

    # 5. Move key_points from skeleton to brief
    if brief:
        skeleton = brief.get("skeleton")
        if isinstance(skeleton, dict) and "key_points" in skeleton:
            if "key_points" not in brief:
                brief["key_points"] = skeleton.pop("key_points")
            else:
                skeleton.pop("key_points")
            corrections.append("Moved key_points from skeleton to brief")

    # 6. Correct evidence_type enum values in claim_inventory
    claim_inventory = result.get("claim_inventory") if isinstance(result.get("claim_inventory"), list) else None
    if claim_inventory:
        for item in claim_inventory:
            if not isinstance(item, dict):
                continue
            et = item.get("evidence_type", "")
            if isinstance(et, str) and et not in ("fact", "inference", "assumption", "hypothesis", "disputed", "gap"):
                mapped = _EVIDENCE_TYPE_MAP.get(et.lower().replace(" ", "_").replace("-", "_"))
                if mapped:
                    item["evidence_type"] = mapped
                    corrections.append(f"evidence_type: {et} → {mapped}")
                else:
                    item["evidence_type"] = "assumption"
                    corrections.append(f"evidence_type: {et} → assumption (default)")

    # 7. Correct stance_impacts.impact enum values
    stance_impacts = result.get("stance_impacts") if isinstance(result.get("stance_impacts"), list) else None
    if stance_impacts:
        for item in stance_impacts:
            if not isinstance(item, dict):
                continue
            impact = item.get("impact", "")
            if isinstance(impact, str) and impact not in ("reinforce", "contradict", "extend", "neutral"):
                mapped = _IMPACT_TYPE_MAP(impact)
                if mapped:
                    item["impact"] = mapped
                    corrections.append(f"stance_impacts.impact: {impact} → {mapped}")
                else:
                    item["impact"] = "neutral"
                    corrections.append(f"stance_impacts.impact: {impact} → neutral (default)")

    # 8. Convert open_questions objects to strings
    open_questions = result.get("open_questions") if isinstance(result.get("open_questions"), list) else None
    if open_questions:
        new_oq = []
        for item in open_questions:
            if isinstance(item, dict):
                text = item.get("question") or item.get("text") or str(item)
                new_oq.append(text)
            elif isinstance(item, str):
                new_oq.append(item)
        if len(new_oq) != len(open_questions) or any(isinstance(item, dict) for item in open_questions):
            result["open_questions"] = new_oq
            corrections.append("Converted open_questions objects to strings")

    # 9. Wrap string skeleton into generators structure
    if brief:
        skeleton = brief.get("skeleton")
        if isinstance(skeleton, str) and skeleton.strip():
            brief["skeleton"] = {
                "generators": [{"name": "综合骨架", "narrative": skeleton.strip()}],
                "diagram": "",
            }
            corrections.append("Wrapped string skeleton into generators structure")

    if corrections:
        print("[auto-correct] V2.0 nesting corrections applied:", file=sys.stderr)
        for c in corrections:
            print(f"  [auto-correct] {c}", file=sys.stderr)

    return data


def _IMPACT_TYPE_MAP(impact: str) -> str:
    """Map descriptive impact text to valid enum."""
    impact_lower = impact.lower().strip()
    if impact_lower in _IMPACT_MAP:
        return _IMPACT_MAP[impact_lower]
    for key, val in _IMPACT_MAP.items():
        if key in impact_lower:
            return val
    return ""


def load_compiled_json_any(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = json.loads(_sanitize_json_text(raw))
    if not isinstance(data, dict):
        raise SystemExit(f"Compiled result must be a JSON object: {path}")
    if str(data.get("version", "")).strip() == "2.0" or str(data.get("schema_version", "")).strip() == "2.0":
        data = _auto_correct_v2_nesting(data)
        return {"schema_version": "2.0", "result": data.get("result", data)}
    if "schema_version" in data and "result" in data:
        schema_version = str(data.get("schema_version", "")).strip() or "1.0"
        result = data.get("result")
        if not isinstance(result, dict):
            raise SystemExit(f"Compiled result wrapper missing object result: {path}")
        return {"schema_version": schema_version, "result": result}
    if "brief" in data and "source" in data:
        return {"schema_version": "1.0", "result": data}
    # Friendly hint for common LLM mistake: schema_version at top level with document_outputs
    if "schema_version" in data and "document_outputs" in data:
        hint = (
            'Compiled JSON has "schema_version" at top level but uses "document_outputs" instead of "result".\n'
            '  Hint: wrap your output as {"version": "2.0", "document_outputs": {...}}\n'
            '  or   {"schema_version": "2.0", "result": {"document_outputs": {...}}}\n'
            f'  Got keys: {list(data.keys())[:10]}'
        )
        raise SystemExit(hint)
    raise SystemExit(
        f"Compiled result missing recognized schema keys: {path}\n"
        f"Expected V2 format: {{\"version\": \"2.0\", \"document_outputs\": {{\"brief\": ..., \"source\": ...}}}}\n"
        f"   or wrapper format: {{\"schema_version\": \"2.0\", \"result\": {{...}}}}\n"
        f"   or V1 format:     {{\"brief\": ..., \"source\": ...}}\n"
        f"Got keys: {list(data.keys())[:10]}"
    )


def extract_document_outputs(compiled_payload: dict[str, object]) -> dict[str, object]:
    schema_version = compiled_payload.get("schema_version")
    result = compiled_payload.get("result")
    if not isinstance(result, dict):
        raise SystemExit("Compiled payload result must be an object.")
    if schema_version == "2.0":
        outputs = result.get("document_outputs")
        if not isinstance(outputs, dict):
            raise SystemExit("V2 compiled payload missing document_outputs.")
        return outputs
    return result


def to_legacy_compile_shape(document_outputs: dict[str, object], compiled_payload: dict[str, object]) -> dict[str, object]:
    schema_version = compiled_payload.get("schema_version")
    if schema_version != "2.0":
        return document_outputs
    result = compiled_payload.get("result")
    knowledge_proposals = result.get("knowledge_proposals") if isinstance(result, dict) else {}
    domains = []
    candidate_concepts = []
    candidate_entities = []
    if isinstance(knowledge_proposals, dict):
        for item in knowledge_proposals.get("domains", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
            action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
            if name and action != "no_page":
                domains.append(name)
        for item in knowledge_proposals.get("concepts", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
            action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
            if name and action == "create_candidate":
                candidate_concepts.append(name)
        for item in knowledge_proposals.get("entities", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
            action = item.get("action", "").strip() if isinstance(item.get("action"), str) else ""
            if name and action == "create_candidate":
                candidate_entities.append(name)
    source = document_outputs.get("source") if isinstance(document_outputs.get("source"), dict) else {}
    claim_inventory_raw = result.get("claim_inventory") if isinstance(result, dict) else []
    claim_inventory = [c for c in claim_inventory_raw if isinstance(c, dict)] if isinstance(claim_inventory_raw, list) else []
    return {
        "brief": document_outputs.get("brief", {}),
        "source": {
            "core_summary": source.get("core_summary", []),
            "candidate_concepts": candidate_concepts,
            "candidate_entities": candidate_entities,
            "domains": domains,
            "knowledge_base_relation": source.get("knowledge_base_relation", []),
            "contradictions": source.get("contradictions", []),
            "reinforcements": source.get("reinforcements", []),
        },
        "claim_inventory": claim_inventory,
    }


def extract_update_proposals(compiled_payload: dict[str, object]) -> list[dict[str, object]]:
    if compiled_payload.get("schema_version") != "2.0":
        return []
    result = compiled_payload.get("result")
    proposals = result.get("update_proposals") if isinstance(result, dict) else []
    claim_inventory = result.get("claim_inventory") if isinstance(result, dict) else []
    claim_items = claim_inventory if isinstance(claim_inventory, list) else []
    normalized_claims = [item for item in claim_items if isinstance(item, dict)]
    if not isinstance(proposals, list):
        return []
    extracted: list[dict[str, object]] = []
    for item in proposals:
        if not isinstance(item, dict):
            continue
        proposal = dict(item)
        if not isinstance(proposal.get("claims"), list):
            proposal["claims"] = normalized_claims
        extracted.append(proposal)
    return extracted


def compiled_domains(compiled: dict[str, object]) -> list[str]:
    source = compiled.get("source")
    if not isinstance(source, dict):
        return []
    domains = source.get("domains")
    if not isinstance(domains, list):
        return []
    return [item for item in domains if isinstance(item, str) and item.strip()]


def append_log(vault: Path, slug: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## [{timestamp}] compile_apply | {slug}",
        "",
        f"- source: [[sources/{slug}]]",
        f"- brief: [[briefs/{slug}]]",
        "",
    ]
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def append_log_v2(vault: Path, slug: str, emitted_deltas: list[Path]) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## [{timestamp}] compile_apply_v2 | {slug}",
        "",
        f"- source: [[sources/{slug}]]",
        f"- brief: [[briefs/{slug}]]",
    ]
    for path in emitted_deltas:
        lines.append(f"- delta: [[outputs/{path.stem}]]")
    lines.append("")
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def build_delta_page_from_update_proposal(
    *,
    proposal: dict[str, object],
    source_slug: str,
    article_title: str,
) -> tuple[str, str]:
    target_page = proposal.get("target_page", "").strip() if isinstance(proposal.get("target_page"), str) else ""
    target_type = proposal.get("target_type", "").strip() if isinstance(proposal.get("target_type"), str) else "source"
    action = proposal.get("action", "").strip() if isinstance(proposal.get("action"), str) else "draft_delta"
    reason = proposal.get("reason", "").strip() if isinstance(proposal.get("reason"), str) else "待人工审核。"
    confidence = proposal.get("confidence", "low")
    evidence = proposal.get("evidence", []) if isinstance(proposal.get("evidence"), list) else []
    patch = proposal.get("patch") if isinstance(proposal.get("patch"), dict) else {}
    claims = proposal.get("claims") if isinstance(proposal.get("claims"), list) else []
    # Determine if this delta has actual draft content (for review queue prioritization)
    summary_delta = patch.get("summary_delta", []) if isinstance(patch.get("summary_delta"), list) else []
    content = patch.get("content", []) if isinstance(patch.get("content"), list) else []
    questions_open = patch.get("questions_open", []) if isinstance(patch.get("questions_open"), list) else []
    has_draft = bool(summary_delta or content or questions_open)
    slug = sanitize_filename(f"delta-{source_slug}-{Path(target_page).stem or target_type}")
    lines = [
        "---",
        f'title: "{article_title} Delta Proposal"',
        'type: "delta-compile"',
        'status: "review-needed"',
        'lifecycle: "review-needed"',
        'graph_role: "working"',
        'graph_include: "false"',
        f'source_page: "wiki/sources/{source_slug}.md"',
        f'target_page: "{target_page}"',
        f'target_type: "{target_type}"',
        f'has_draft: "{str(has_draft).lower()}"',
        "---",
        "",
        "# Delta Proposal",
        "",
        "## 目标页面",
        "",
        f"- `{target_page or 'unknown'}`",
        "",
        "## 动作",
        "",
        f"- `{action}`",
        "",
        "## 原因",
        "",
        f"- {reason}",
        "",
        "## 置信度",
        "",
        f"- {confidence}",
        "",
        "## 证据",
        "",
    ]
    lines.extend(f"- {item}" for item in evidence[:6])
    if not evidence:
        lines.append("- 待人工补充证据。")
    lines.extend(["", "## 关键判断", ""])
    for item in claims[:6]:
        if not isinstance(item, dict):
            continue
        claim = item.get("claim", "").strip() if isinstance(item.get("claim"), str) else ""
        claim_type = item.get("claim_type", "").strip() if isinstance(item.get("claim_type"), str) else "interpretation"
        confidence_label = item.get("confidence", "low")
        if claim:
            lines.append(f"- [{claim_type}|{confidence_label}] {claim}")
    if lines[-1] == "":
        lines.append("- 待人工补充关键判断。")
    lines.extend(["", "## 建议修改", ""])
    lines.extend(f"- {item}" for item in summary_delta[:6])
    lines.extend(f"- {item}" for item in content[:6])
    lines.extend(f"- 待验证：{item}" for item in questions_open[:4])
    if not summary_delta and not content and not questions_open:
        lines.append("- 待人工补充草稿内容。")
    lines.append("")
    return slug, "\n".join(lines)


def emit_update_proposals_as_deltas(
    *,
    vault: Path,
    proposals: list[dict[str, object]],
    source_slug: str,
    article_title: str,
) -> list[Path]:
    outputs_dir = vault / "wiki" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    emitted: list[Path] = []
    for proposal in proposals:
        claims = proposal.get("claims")
        if not isinstance(claims, list):
            proposal["claims"] = []
        slug, page = build_delta_page_from_update_proposal(
            proposal=proposal,
            source_slug=source_slug,
            article_title=article_title,
        )
        path = outputs_dir / f"{slug}.md"
        path.write_text(page, encoding="utf-8")
        emitted.append(path)
    return emitted


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    vault = args.vault.resolve()
    compiled_payload = load_compiled_json_any(args.compiled_json.resolve())

    # Resolve raw path: --raw flag takes priority, then compile_target.raw_path
    if args.raw:
        raw_path = args.raw.resolve()
    else:
        compile_target = compiled_payload.get("compile_target") or compiled_payload.get("result", {}).get("compile_target") or {}
        raw_path_str = compile_target.get("raw_path", "") if isinstance(compile_target, dict) else ""
        if not raw_path_str:
            raise SystemExit("--raw not provided and compile_target.raw_path not found in compiled JSON.")
        raw_path = Path(raw_path_str).resolve()
        if not raw_path.exists():
            # Try relative to vault
            raw_path = (vault / raw_path_str).resolve()

    article, slug = article_from_raw(raw_path)

    # --- Validation gate ---
    is_valid, reason = validate_compile_result(compiled_payload)
    validation_report: dict[str, object] = {"structural_valid": is_valid, "reason": reason}

    if is_valid:
        # Grounding check (needs raw text)
        raw_text = raw_path.read_text(encoding="utf-8")
        _, body = parse_frontmatter(raw_text)
        grounding_ok, violations = grounding_validate(compiled_payload, body.strip())
        validation_report["grounding_ok"] = grounding_ok
        validation_report["grounding_violations"] = violations

        # Evidence density
        maturity, density_warnings = density_check(compiled_payload)
        validation_report["maturity"] = maturity
        validation_report["density_warnings"] = density_warnings

    if args.validate_only:
        print(json.dumps(validation_report, ensure_ascii=False, indent=2))
        return 0 if is_valid else 1

    if not is_valid:
        print(f"Validation failed: {reason}", file=sys.stderr)
        print("Run with --validate-only to see full report.", file=sys.stderr)
        return 1

    document_outputs = extract_document_outputs(compiled_payload)
    compiled = to_legacy_compile_shape(document_outputs, compiled_payload)

    brief_path = vault / "wiki" / "briefs" / f"{slug}.md"
    source_path = vault / "wiki" / "sources" / f"{slug}.md"
    if (brief_path.exists() or source_path.exists()) and not args.force:
        raise SystemExit("Target brief/source already exist. Pass --force to overwrite.")

    brief_path.write_text(build_brief_page_from_compile(article, slug, compiled), encoding="utf-8")
    source_path.write_text(build_source_page_from_compile(vault, article, slug, compiled), encoding="utf-8")
    domains = compiled_domains(compiled)
    ensure_taxonomy_pages(vault, article, slug, args.force, domains_override=domains or None)
    ensure_synthesis_pages(vault, article, slug, domains_override=domains or None)
    emitted_deltas = emit_update_proposals_as_deltas(
        vault=vault,
        proposals=extract_update_proposals(compiled_payload),
        source_slug=slug,
        article_title=article.title,
    )
    rebuild_index(vault)
    if compiled_payload.get("schema_version") == "2.0":
        append_log_v2(vault, slug, emitted_deltas)
    else:
        append_log(vault, slug)

    print(
        json.dumps(
            {
                "brief": str(brief_path),
                "source": str(source_path),
                "compile_mode": "agent-interactive-v2" if compiled_payload.get("schema_version") == "2.0" else "agent-interactive",
                "delta_outputs": [str(path) for path in emitted_deltas],
                "delta_note": f"共 {len(emitted_deltas)} 个 delta 提案待审核。说 'review' 查看审核队列，或逐个检查 wiki/outputs/ 下的文件。" if emitted_deltas else "",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
