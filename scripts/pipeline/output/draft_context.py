"""Mode: draft-context — copy-paste-ready material pack with citations."""

from __future__ import annotations

from pathlib import Path

from . import _read_page, _page_title
from pipeline.text_utils import parse_frontmatter, section_excerpt, plain_text, get_one_sentence


def build_draft_context_output(
    vault: Path,
    question: str,
    candidates: list[object],
) -> str:
    """Copy-paste-ready material pack with citations for feeding into an LLM."""
    lines: list[str] = [f"# 素材包：{question}", ""]

    lines.append("## 使用说明")
    lines.append("")
    lines.append("- 以下素材均来自本地知识库，每条标注来源页。")
    lines.append("- 可直接粘贴到 LLM 对话中作为上下文。")
    lines.append("")

    lines.append("## 来源摘要")
    lines.append("")
    for i, cand in enumerate(candidates[:6], 1):
        ref = cand.ref  # type: ignore[attr-defined]
        meta, body = _read_page(vault, ref)
        title = _page_title(meta, cand.path.stem)  # type: ignore[attr-defined]

        if meta.get("type") == "source":
            core = section_excerpt(body, "核心摘要")
            relation = section_excerpt(body, "与现有知识库的关系")
        elif meta.get("type") == "brief":
            core = get_one_sentence(meta, body)
            relation = ""
        elif meta.get("type") == "synthesis":
            core = section_excerpt(body, "当前结论")
            relation = section_excerpt(body, "近期来源")
        else:
            core = plain_text(body)[:300]
            relation = ""

        lines.append(f"### [{i}] {title}")
        lines.append(f"来源：[[{ref}]]")
        lines.append("")
        if core:
            lines.append(core[:500])
            lines.append("")
        if relation:
            lines.append(f"知识库关联：{relation[:300]}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # Raw sources
    lines.append("## 原文摘录（精确引用用）")
    lines.append("")
    for cand in candidates[:3]:
        ref = cand.ref  # type: ignore[attr-defined]
        if not ref.startswith("sources/"):
            continue
        slug = ref.split("/", 1)[1]
        raw_path = vault / "raw" / "articles" / f"{slug}.md"
        if not raw_path.exists():
            continue
        raw_text = raw_path.read_text(encoding="utf-8")
        _, raw_body = parse_frontmatter(raw_text)
        plain = plain_text(raw_body)
        lines.append(f"### [[raw/articles/{slug}]]")
        lines.append("")
        lines.append(plain[:800])
        lines.append("")
        lines.append("...")
        lines.append("")

    return "\n".join(lines)