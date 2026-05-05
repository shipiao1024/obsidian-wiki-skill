#!/usr/bin/env python
"""Track claim evolution across vault sources.

Three-stage architecture:
  --collect-only : Collect claims → JSON for LLM analysis (Phase 1)
  --apply        : Execute LLM decisions from JSON (Phase 3)
  (default)      : Collect + basic report (legacy, no semantic judgment)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from pipeline.encoding_fix import fix_windows_encoding
from pipeline.shared import resolve_vault, validate_apply_json
from pipeline.text_utils import CLAIM_PATTERN, parse_frontmatter, section_body


def collect_all_claims(vault: Path) -> list[dict[str, str]]:
    """Collect all claims from sources/briefs/outputs/syntheses."""
    claims: list[dict[str, str]] = []
    folders = [
        (vault / "wiki" / "outputs", "output"),
        (vault / "wiki" / "sources", "source"),
        (vault / "wiki" / "briefs", "brief"),
        (vault / "wiki" / "syntheses", "synthesis"),
    ]
    for folder, page_type in folders:
        if not folder.exists():
            continue
        for path in folder.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)
            actual_type = meta.get("type", page_type)
            if actual_type not in {"delta-compile", "source", "brief", "synthesis"}:
                continue
            claims_body = section_body(body, "关键判断")
            for match in CLAIM_PATTERN.finditer(claims_body):
                claims.append({
                    "path": f"{folder.name}/{path.stem}",
                    "claim_type": match.group(1).strip(),
                    "confidence": match.group(2).strip().lower(),
                    "claim_text": match.group(3).strip(),
                    "page_type": actual_type,
                })
    return claims


def collect_claims_json(vault: Path) -> dict:
    """Phase 1: Collect claims data for LLM analysis."""
    claims = collect_all_claims(vault)
    return {
        "claims": claims,
        "total_count": len(claims),
        "by_confidence": {
            "high": sum(1 for c in claims if c["confidence"] == "high"),
            "medium": sum(1 for c in claims if c["confidence"] == "medium"),
            "low": sum(1 for c in claims if c["confidence"] == "low"),
        },
        "by_page_type": {
            pt: sum(1 for c in claims if c["page_type"] == pt)
            for pt in set(c["page_type"] for c in claims)
        } if claims else {},
    }


def apply_claim_evolution_result(vault: Path, result_path: Path) -> None:
    """Phase 3: Write claim-evolution.md from LLM analysis result."""
    result = json.loads(result_path.read_text(encoding="utf-8"))
    validate_apply_json(result, ["relationships"], context="claim_evolution")
    relationships = result.get("relationships", [])
    statistics = result.get("statistics", {})
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    contradicts = [r for r in relationships if r.get("relationship") == "contradict"]
    reinforces = [r for r in relationships if r.get("relationship") == "reinforce"]
    extends = [r for r in relationships if r.get("relationship") == "extend"]

    lines = [
        "---",
        'title: "主张演化追踪"',
        'type: "system-report"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        f'generated: "{today}"',
        'analysis_method: "llm-driven"',
        "---",
        "",
        "# 主张演化追踪",
        "",
        f"> 生成日期：{today}",
        f"> 分析方法：LLM 语义分析（非关键词匹配）",
        "",
        "## 概览",
        "",
        f"- 分析主张对：{statistics.get('total_pairs_analyzed', len(relationships))}",
        f"- 矛盾主张：{len(contradicts)}",
        f"- 强化主张：{len(reinforces)}",
        f"- 延伸主张：{len(extends)}",
        "",
    ]

    if contradicts:
        lines.append("## 矛盾主张")
        lines.append("")
        for item in contradicts:
            left_src = item.get("left_source", "")
            right_src = item.get("right_source", "")
            reasoning = item.get("reasoning", "")
            lines.append(f"- [[{left_src}]] vs [[{right_src}]]")
            lines.append(f"  - {item.get('left_text', '')[:100]}")
            lines.append(f"  - {item.get('right_text', '')[:100]}")
            if reasoning:
                lines.append(f"  - 理由：{reasoning}")
        lines.append("")

    if reinforces:
        lines.append("## 强化主张")
        lines.append("")
        for item in reinforces[:20]:
            left_src = item.get("left_source", "")
            right_src = item.get("right_source", "")
            lines.append(f"- [[{left_src}]] + [[{right_src}]]")
            lines.append(f"  - {item.get('left_text', '')[:80]}")
        lines.append("")

    if extends:
        lines.append("## 延伸主张")
        lines.append("")
        for item in extends[:20]:
            left_src = item.get("left_source", "")
            right_src = item.get("right_source", "")
            lines.append(f"- [[{left_src}]] → [[{right_src}]]")
            lines.append(f"  - {item.get('left_text', '')[:80]}")
            lines.append(f"  - {item.get('right_text', '')[:80]}")
        lines.append("")

    page_path = vault / "wiki" / "claim-evolution.md"
    page_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Claim evolution page written to {page_path}")


def main() -> int:
    fix_windows_encoding()
    parser = argparse.ArgumentParser(description="Track claim evolution across vault sources.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument("--collect-only", action="store_true", help="Collect claims as JSON for LLM analysis.")
    parser.add_argument("--apply", type=Path, dest="apply_json", help="Write claim-evolution.md from LLM result JSON.")
    parser.add_argument("--output", type=Path, help="Output path for --collect-only JSON.")
    args = parser.parse_args()
    vault = resolve_vault(args.vault).resolve()

    if args.apply_json:
        apply_claim_evolution_result(vault, args.apply_json)
        return 0

    if args.collect_only:
        data = collect_claims_json(vault)
        output = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Claims data written to {args.output}")
        else:
            print(output)
        return 0

    # Legacy mode: collect + basic stats (no semantic judgment)
    data = collect_claims_json(vault)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
