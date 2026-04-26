#!/usr/bin/env python
"""Apply approved outputs/delta drafts back into official wiki pages."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from pipeline.shared import resolve_vault


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
LINK_PATTERN = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply an approved output/delta draft into official wiki pages.")
    parser.add_argument("output", help="Output ref like outputs/foo or absolute path to wiki/outputs/*.md.")
    parser.add_argument("--vault", type=Path, help="Obsidian vault root.")
    parser.add_argument(
        "--target",
        help="Optional explicit target ref, e.g. syntheses/自动驾驶--综合分析 or sources/<slug>.",
    )
    return parser.parse_args()



def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, text[match.end():]


def render_frontmatter(meta: dict[str, str]) -> str:
    preferred_order = [
        "title",
        "type",
        "status",
        "fidelity",
        "graph_role",
        "graph_include",
        "lifecycle",
        "slug",
        "question",
        "source_page",
        "raw_source",
        "brief_page",
        "created_at",
        "approved_at",
        "absorbed_into",
        "updated_at",
        "domain",
        "author",
        "date",
        "source",
    ]
    lines = ["---"]
    emitted: set[str] = set()
    for key in preferred_order:
        if key in meta:
            lines.append(f'{key}: "{meta[key]}"')
            emitted.add(key)
    for key in sorted(meta):
        if key not in emitted:
            lines.append(f'{key}: "{meta[key]}"')
    lines.extend(["---", ""])
    return "\n".join(lines)


def resolve_output_path(vault: Path, output_arg: str) -> Path:
    candidate = Path(output_arg)
    if candidate.is_absolute():
        return candidate
    ref = output_arg.replace("\\", "/").strip()
    if ref.startswith("wiki/"):
        return vault / f"{ref}.md" if not ref.endswith(".md") else vault / ref
    if ref.startswith("outputs/"):
        return vault / "wiki" / f"{ref}.md" if not ref.endswith(".md") else vault / "wiki" / ref
    return vault / "wiki" / "outputs" / (ref if ref.endswith(".md") else f"{ref}.md")


def resolve_wiki_ref(vault: Path, ref: str) -> Path:
    normalized = ref.replace("\\", "/").strip()
    if normalized.startswith("wiki/"):
        normalized = normalized[5:]
    return vault / "wiki" / (normalized if normalized.endswith(".md") else f"{normalized}.md")


def section_body(body: str, heading: str) -> str:
    pattern = re.compile(rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s+|\Z)", re.S)
    match = pattern.search(body)
    if not match:
        return ""
    return match.group(1).strip()


def section_lines(body: str, heading: str) -> list[str]:
    return [line.strip() for line in section_body(body, heading).splitlines() if line.strip()]


def replace_section(body: str, heading: str, content_lines: list[str]) -> str:
    pattern = re.compile(rf"(##\s+{re.escape(heading)}\s*\n)(.*?)(?=\n##\s+|\Z)", re.S)
    content = "\n".join(content_lines).rstrip() + "\n\n"
    match = pattern.search(body)
    if match:
        return body[:match.start()] + match.group(1) + content + body[match.end():]
    suffix = body.rstrip() + "\n\n" if body.strip() else ""
    return suffix + f"## {heading}\n" + "\n".join(content_lines).rstrip() + "\n"


def merge_bullets(existing_lines: list[str], new_lines: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for line in [*existing_lines, *new_lines]:
        normalized = line.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def extract_refs(text: str, prefix: str) -> list[str]:
    refs: list[str] = []
    for match in LINK_PATTERN.finditer(text):
        ref = match.group(1).strip()
        if ref.startswith(prefix):
            refs.append(ref)
    return refs


def clean_answer_lines(body: str) -> list[str]:
    lines = section_lines(body, "回答") or section_lines(body, "建议回答")
    cleaned: list[str] = []
    for line in lines:
        if not line or line in {"结论：", "补充依据：", "原文核对："}:
            continue
        if line.startswith("问题："):
            continue
        if line.startswith("- "):
            candidate = line[2:].strip()
        else:
            candidate = line
        parts = [item.strip() for item in re.split(r"(?<=[。！？!?；;])\s*", candidate) if item.strip()]
        cleaned.extend(parts or [candidate])
    return cleaned


def apply_source_delta(vault: Path, output_path: Path, meta: dict[str, str], body: str) -> list[str]:
    source_ref = meta.get("source_page", "")
    if not source_ref:
        raise SystemExit("Delta source page is missing source_page in frontmatter.")
    source_ref = source_ref.strip("[]")
    raw_source = meta.get("raw_source", "")
    source_path = resolve_wiki_ref(vault, source_ref.strip("[]"))
    source_meta, source_body = parse_frontmatter(source_path.read_text(encoding="utf-8"))
    brief_ref = source_meta.get("brief_page", "").strip("[]")
    if not brief_ref:
        raise SystemExit("Target source page is missing brief_page in frontmatter.")
    brief_path = resolve_wiki_ref(vault, brief_ref.strip("[]"))
    brief_meta, brief_body = parse_frontmatter(brief_path.read_text(encoding="utf-8"))

    lead = section_body(body, "建议替换的一句话结论").strip() or "待补充。"
    brief_bullets = [line if line.startswith("- ") else f"- {line.lstrip('- ').strip()}" for line in section_lines(body, "建议替换的快读要点")]
    source_bullets = [line if line.startswith("- ") else f"- {line.lstrip('- ').strip()}" for line in section_lines(body, "建议替换的来源摘要")]
    evidence_lines = [line if line.startswith("- ") else f"- {line.lstrip('- ').strip()}" for line in section_lines(body, "使用证据")]

    updated_brief = replace_section(brief_body, "一句话结论", [lead])
    updated_brief = replace_section(updated_brief, "核心要点", brief_bullets or ["- 待补充。"])
    absorption_brief = [f"- 已吸收 [[outputs/{output_path.stem}]]", f"- 吸收时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    updated_brief = replace_section(updated_brief, "吸收记录", merge_bullets(section_lines(updated_brief, "吸收记录"), absorption_brief))
    brief_meta["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    brief_path.write_text(render_frontmatter(brief_meta) + updated_brief.lstrip("\n"), encoding="utf-8")

    updated_source = replace_section(source_body, "核心摘要", source_bullets or ["- 待补充。"])
    existing_relation = section_lines(updated_source, "与现有知识库的关系")
    relation_note = f"- 已吸收 [[outputs/{output_path.stem}]] 的人工确认结果。"
    updated_source = replace_section(updated_source, "与现有知识库的关系", merge_bullets(existing_relation, [relation_note]))
    updated_source = replace_section(updated_source, "吸收证据", merge_bullets(section_lines(updated_source, "吸收证据"), evidence_lines))
    source_meta["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if raw_source and "raw_source" not in source_meta:
        source_meta["raw_source"] = raw_source
    source_path.write_text(render_frontmatter(source_meta) + updated_source.lstrip("\n"), encoding="utf-8")
    return [f"sources/{source_path.stem}", f"briefs/{brief_path.stem}"]


def detect_synthesis_target(body: str, explicit_target: str | None) -> str | None:
    if explicit_target:
        return explicit_target.replace("\\", "/").removesuffix(".md")
    for heading in ("使用证据", "使用页面"):
        for ref in extract_refs(section_body(body, heading), "syntheses/"):
            return ref
    return None


def apply_answer_into_synthesis(vault: Path, output_path: Path, target_ref: str, body: str) -> list[str]:
    synthesis_path = resolve_wiki_ref(vault, target_ref)
    if not synthesis_path.exists():
        raise SystemExit(f"Target synthesis page not found: {target_ref}")
    synth_meta, synth_body = parse_frontmatter(synthesis_path.read_text(encoding="utf-8"))

    answer_lines = clean_answer_lines(body)
    current_lines = [line if line.startswith("- ") else f"- {line}" for line in section_lines(synth_body, "核心判断")]
    new_answer_bullets = []
    for line in answer_lines:
        normalized = line
        if normalized.endswith("："):
            continue
        bullet = normalized if normalized.startswith("- ") else f"- {normalized}"
        bullet_text = bullet.lstrip("- ").strip()
        if any(
            bullet_text != existing.lstrip("- ").strip()
            and bullet_text in existing.lstrip("- ").strip()
            for existing in current_lines
        ):
            continue
        if bullet.startswith("- "):
            new_answer_bullets.append(bullet)
        else:
            new_answer_bullets.append(f"- {normalized}")
    updated_synth = replace_section(synth_body, "核心判断", merge_bullets(current_lines, new_answer_bullets))

    current_conclusion = section_body(updated_synth, "当前结论").strip()
    if new_answer_bullets:
        lead = new_answer_bullets[0].lstrip("- ").strip()
        if lead and lead not in current_conclusion:
            merged_conclusion = f"{current_conclusion}；{lead}".strip("；") if current_conclusion else lead
            if not merged_conclusion.endswith("。"):
                merged_conclusion += "。"
            updated_synth = replace_section(updated_synth, "当前结论", [merged_conclusion])

    evidence_heading = "使用证据" if section_body(body, "使用证据") else "使用页面"
    evidence_lines = []
    for line in section_lines(body, evidence_heading):
        match = LINK_PATTERN.search(line)
        ref = match.group(1).strip() if match else ""
        if ref and not (ref.startswith("sources/") or ref.startswith("raw/articles/")):
            continue
        evidence_lines.append(line if line.startswith("- ") else f"- {line.lstrip('- ').strip()}")
    recent_sources = merge_bullets(section_lines(updated_synth, "近期来源"), evidence_lines)
    updated_synth = replace_section(updated_synth, "近期来源", recent_sources)
    absorbed_notes = merge_bullets(
        section_lines(updated_synth, "已吸收问答"),
        [f"- [[outputs/{output_path.stem}]]"],
    )
    updated_synth = replace_section(updated_synth, "已吸收问答", absorbed_notes)
    synth_meta["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    synthesis_path.write_text(render_frontmatter(synth_meta) + updated_synth.lstrip("\n"), encoding="utf-8")
    return [target_ref]


def mark_output_absorbed(output_path: Path, targets: list[str]) -> None:
    meta, body = parse_frontmatter(output_path.read_text(encoding="utf-8"))
    meta["status"] = "accepted"
    meta["lifecycle"] = "absorbed"
    meta["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta["absorbed_into"] = ", ".join(targets)
    updated_body = replace_section(
        body,
        "吸收记录",
        [f"- 已吸收到 [[{target}]]" for target in targets] + [f"- 吸收时间：{meta['approved_at']}"],
    )
    output_path.write_text(render_frontmatter(meta) + updated_body.lstrip("\n"), encoding="utf-8")


def append_log(vault: Path, output_stem: str, targets: list[str]) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"## [{timestamp}] apply_delta | {output_stem}",
        "",
        f"- output: [[outputs/{output_stem}]]",
    ]
    lines.extend(f"- absorbed_into: [[{target}]]" for target in targets)
    lines.extend(["", ""])
    with (vault / "wiki" / "log.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def rebuild_index(vault: Path) -> None:
    sections = [
        ("Sources", "sources"),
        ("Briefs", "briefs"),
        ("Concepts", "concepts"),
        ("Entities", "entities"),
        ("Domains", "domains"),
        ("Syntheses", "syntheses"),
        ("Outputs", "outputs"),
    ]
    lines = [
        "---",
        'title: "Wiki Index"',
        'type: "system-index"',
        'graph_role: "system"',
        'graph_include: "false"',
        'lifecycle: "canonical"',
        "---",
        "",
        "# Wiki Index",
        "",
        "> 先扫描本页，再按需打开相关页面。",
        "",
    ]
    for title, folder in sections:
        lines.extend([f"## {title}", ""])
        files = sorted((vault / "wiki" / folder).glob("*.md"))
        visible_count = 0
        for file in files:
            meta, body = parse_frontmatter(file.read_text(encoding="utf-8"))
            if folder == "outputs" and meta.get("lifecycle") == "absorbed":
                continue
            visible_count += 1
            page_type = meta.get("type", "")
            if page_type == "source":
                summary = section_body(body, "核心摘要")
            elif page_type == "brief":
                summary = section_body(body, "一句话结论")
            elif page_type in {"output", "delta-compile"}:
                summary = section_body(body, "建议替换的一句话结论") or section_body(body, "回答")
            else:
                summary = body[:240].strip()
            lines.append(f"- [[{folder}/{file.stem}]]: {(summary or '待补充摘要').replace(chr(10), ' ')}")
        if visible_count == 0:
            lines.append("- （空）")
        lines.append("")
    (vault / "wiki" / "index.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    vault = resolve_vault(args.vault).resolve()
    output_path = resolve_output_path(vault, args.output)
    if not output_path.exists():
        raise SystemExit(f"Output page not found: {output_path}")

    meta, body = parse_frontmatter(output_path.read_text(encoding="utf-8"))
    page_type = meta.get("type", "")
    targets: list[str]

    if page_type == "delta-compile" and meta.get("source_page"):
        targets = apply_source_delta(vault, output_path, meta, body)
    else:
        target_ref = detect_synthesis_target(body, args.target)
        if not target_ref:
            raise SystemExit("Could not determine a synthesis target automatically. Pass --target explicitly.")
        targets = apply_answer_into_synthesis(vault, output_path, target_ref, body)

    mark_output_absorbed(output_path, targets)
    append_log(vault, output_path.stem, targets)
    rebuild_index(vault)

    print(json.dumps({"output": str(output_path), "absorbed_into": targets}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
