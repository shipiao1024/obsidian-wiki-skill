#!/usr/bin/env python
"""Compile a raw article into structured brief/source content using an OpenAI-compatible API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from env_compat import resolve_env
from pipeline.types import DEFAULT_DOMAINS, DOMAIN_MIN_SCORE
from pipeline.encoding_fix import fix_windows_encoding


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)
WIKILINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)


def default_runtime_dir() -> Path:
    candidates: list[Path] = []
    configured = resolve_env("KWIKI_RUNTIME_DIR")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(Path.cwd() / ".runtime-fetch")
    candidates.append(Path(__file__).resolve().parent.parent / ".runtime-fetch")
    for root in candidates:
        try:
            root.mkdir(parents=True, exist_ok=True)
            return root
        except OSError:
            continue
    raise OSError("No writable runtime directory available.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or run one structured brief/source compile for a raw article.")
    parser.add_argument("--vault", type=Path, required=True, help="Obsidian vault root.")
    parser.add_argument("--raw", type=Path, required=True, help="Raw article markdown path.")
    parser.add_argument("--title", required=True, help="Article title.")
    parser.add_argument("--author", default="", help="Article author.")
    parser.add_argument("--date", default="", help="Article date.")
    parser.add_argument("--source-url", default="", help="Original article URL.")
    parser.add_argument("--slug", help="Article slug. Defaults to raw filename stem.")
    parser.add_argument("--model", help="Override model name.")
    parser.add_argument("--prepare-only", action="store_true", help="Only emit compile context and prompts for Codex/Claude-style interactive compilation.")
    parser.add_argument("--lean", action="store_true", help="In prepare-only mode, omit system_prompt/user_prompt from output and filter noisy synthesis excerpts. Reduces context payload by ~60%%.")
    parser.add_argument("--two-step", action="store_true", help="Use two-step CoT ingest: extract facts first, then compile wiki structure constrained by facts.")
    parser.add_argument("--extract-facts-only", action="store_true", help="Only run Step 1 (fact extraction) without Step 2 (compile).")
    parser.add_argument("--chunked", action="store_true", help="Split large documents into chunks by chapter headings and generate per-chunk compile payloads. Outputs JSON file with chunk list.")
    parser.add_argument("--chunk-size", type=int, default=500, help="Max lines per chunk when no chapter headings are found (default: 500).")
    parser.add_argument("--chunk-output", type=Path, default=None, help="Path to write chunked payload JSON file. Defaults to .runtime-fetch/compile-payloads/{slug}_chunks.json.")
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


def plain_text(md: str) -> str:
    text = FRONTMATTER.sub("", md)
    text = CODE_BLOCK.sub("", text)
    text = re.sub(r"!\[\[[^\]]+\]\]", "", text)
    text = WIKILINK.sub(lambda m: m.group(2) or m.group(1), text)
    text = MARKDOWN_LINK.sub(r"\1", text)
    text = HEADING.sub("", text)
    text = re.sub(r"[>*_`~\-\|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def page_excerpt(path: Path, limit: int = 1200) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    return plain_text(body)[:limit].strip()


def detect_domains(title: str, body: str) -> list[str]:
    """Detect which knowledge domains the article belongs to by keyword matching.

    Scans title + body against DEFAULT_DOMAINS keyword lists.
    Returns domains whose match count meets DOMAIN_MIN_SCORE threshold.
    Title matches are weighted 3x.
    """
    combined = f"{title} {body}"
    results: list[str] = []
    for domain, keywords in DEFAULT_DOMAINS.items():
        score = 0
        for kw in keywords:
            # Title matches count 3x
            if kw.lower() in title.lower():
                score += 3
            # Body matches count 1x (limit scan to first 5000 chars for speed)
            score += combined[:5000].lower().count(kw.lower())
        min_score = DOMAIN_MIN_SCORE.get(domain, 3)
        if score >= min_score:
            results.append(domain)
    return results if results else ["待归域"]


_SYNTHESIS_NOISE_HEURISTICS = [
    "什么时候我们说话自己都签了",
    "案发现场心智模式在时间运行",
    "后台里面全是木马",
    "操控界面上全是弹窗",
    "小管高能运行",
    "讲话学习吧",
    "欢迎来到汤质看本质",
    "欢迎回来好久不见",
]


def _is_noisy_synthesis_excerpt(text: str) -> bool:
    if not text:
        return False
    matches = sum(1 for h in _SYNTHESIS_NOISE_HEURISTICS if h in text)
    return matches >= 2


def collect_context(vault: Path, slug: str, title: str, raw_body: str, lean: bool = False) -> dict[str, object]:
    existing_source = vault / "wiki" / "sources" / f"{slug}.md"
    existing_brief = vault / "wiki" / "briefs" / f"{slug}.md"
    domains = detect_domains(title, raw_body)
    related_domains: dict[str, dict[str, str]] = {}
    for domain in domains:
        domain_path = vault / "wiki" / "domains" / f"{domain}.md"
        synthesis_path = vault / "wiki" / "syntheses" / f"{domain}--综合分析.md"
        domain_excerpt = page_excerpt(domain_path, limit=600)
        synthesis_excerpt = page_excerpt(synthesis_path, limit=900)
        if lean and _is_noisy_synthesis_excerpt(synthesis_excerpt):
            synthesis_excerpt = ""
        related_domains[domain] = {
            "domain_page": domain_excerpt,
            "synthesis_page": synthesis_excerpt,
        }
    purpose_path = vault / "purpose.md"
    purpose_text = ""
    if purpose_path.exists():
        purpose_text = purpose_path.read_text(encoding="utf-8")[:1500].strip()
    ctx = {
        "existing_source": page_excerpt(existing_source),
        "existing_brief": page_excerpt(existing_brief),
        "related_domains": related_domains,
        "detected_domains": domains,
        "purpose": purpose_text,
    }
    if lean:
        ctx.pop("existing_source", None)
        ctx.pop("existing_brief", None)
    return ctx


def collect_related_pages(
    vault: Path,
    *,
    title: str,
    raw_body: str,
    slug: str,
    limit: int = 5,
    lean: bool = False,
) -> dict[str, list[dict[str, str]]]:
    terms = [term for term in re.findall(r"[A-Za-z0-9\-\+]{2,}|[\u4e00-\u9fff]{2,8}", f"{title} {raw_body[:1200]}") if term]
    deduped_terms: list[str] = []
    stopwords = {"这篇", "文章", "一个", "我们", "他们", "以及", "如果", "因为", "所以"}
    for term in terms:
        if term in stopwords:
            continue
        if term not in deduped_terms:
            deduped_terms.append(term)
        if len(deduped_terms) >= 12:
            break

    def score(path: Path) -> int:
        text = page_excerpt(path, limit=900)
        if not text:
            return 0
        value = 0
        for term in deduped_terms:
            if term in path.stem:
                value += 5
            value += text.count(term)
        return value

    groups = {
        "related_sources": vault / "wiki" / "sources",
        "related_concepts": vault / "wiki" / "concepts",
        "related_entities": vault / "wiki" / "entities",
        "related_syntheses": vault / "wiki" / "syntheses",
        "pending_deltas": vault / "wiki" / "outputs",
    }
    result: dict[str, list[dict[str, str]]] = {}
    for key, folder in groups.items():
        items: list[tuple[int, Path]] = []
        if not folder.exists():
            result[key] = []
            continue
        for path in folder.glob("*.md"):
            if path.stem == slug:
                continue
            if key == "pending_deltas" and "delta" not in path.stem:
                continue
            value = score(path)
            if value <= 0:
                continue
            items.append((value, path))
        items.sort(key=lambda item: item[0], reverse=True)
        entries = []
        for _, path in items[:limit]:
            excerpt = page_excerpt(path, limit=500)
            if lean and key == "related_syntheses" and _is_noisy_synthesis_excerpt(excerpt):
                excerpt = ""
            entries.append({"path": str(path.relative_to(vault)), "title": path.stem, "excerpt": excerpt})
        result[key] = entries
    return result


def prompt_path_v2() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "prompts" / "ingest_compile_prompt_v2.md"


def load_prompt_v2() -> str:
    path = prompt_path_v2()
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def fact_extraction_prompt_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "prompts" / "fact_extraction_prompt.md"


def load_fact_extraction_prompt() -> str:
    path = fact_extraction_prompt_path()
    if not path.exists():
        raise RuntimeError(f"Fact extraction prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def build_user_prompt_v2(
    title: str,
    author: str,
    date: str,
    source_url: str,
    raw_body: str,
    context: dict[str, object],
    *,
    fact_inventory: dict[str, object] | None = None,
) -> str:
    parts = [
        "请基于以下输入执行 v2 编译。",
        "",
        "## 来源元数据",
        f"- 标题：{title}",
        f"- 作者：{author or '未知'}",
        f"- 日期：{date or '未知'}",
        f"- 链接：{source_url or '未知'}",
    ]
    purpose_text = context.get("purpose", "") if isinstance(context, dict) else ""
    if purpose_text:
        parts.extend([
            "",
            "## 研究方向（purpose.md）",
            "如果内容与下方关注领域相关，优先提取相关实体/话题；排除范围内的内容仅标注但不创建独立页面。",
            purpose_text,
        ])
    if fact_inventory:
        parts.extend([
            "",
            "## 事实清单（fact_inventory）",
            "以下是从事原文中提取的原子事实和论证结构。你的编译输出必须受此约束：",
            "- knowledge_proposals 中的每条建议必须引用 fact_inventory 中的事实 ID",
            "- claim_inventory 不得超出 atomic_facts 的范围",
            "- 如果某个提议无法锚定到 fact_inventory 中的事实，降级为 assumption",
            json.dumps(fact_inventory, ensure_ascii=False, indent=2),
        ])
    parts.extend([
        "",
        "## 现有上下文",
        json.dumps({k: v for k, v in context.items() if k != "purpose"}, ensure_ascii=False, indent=2),
        "",
        "## 原文正文",
        raw_body,
    ])
    return "\n".join(parts)


def prepare_compile_payload_v2(
    *,
    vault: Path,
    raw_path: Path,
    title: str,
    author: str,
    date: str,
    source_url: str,
    slug: str,
    lean: bool = False,
) -> dict[str, object]:
    raw_text = raw_path.read_text(encoding="utf-8")
    _, raw_body = parse_frontmatter(raw_text)
    context = collect_context(vault, slug, title, raw_body, lean=lean)
    context.update(collect_related_pages(vault, title=title, raw_body=raw_body, slug=slug, lean=lean))
    system_prompt = load_prompt_v2()
    user_prompt = build_user_prompt_v2(title, author, date, source_url, raw_body, context)
    result = {
        "mode": "agent-interactive-compile-v2",
        "metadata": {
            "title": title,
            "author": author,
            "date": date,
            "source_url": source_url,
            "slug": slug,
            "vault": str(vault),
            "raw": str(raw_path),
        },
        "context": context,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "expected_output_schema_version": "2.0",
    }
    if lean:
        result.pop("system_prompt", None)
        result.pop("user_prompt", None)
    return result


# ---------------------------------------------------------------------------
# Chunked compilation: split large documents into sections for per-chunk
# extraction, then synthesize into a full compile JSON.
# ---------------------------------------------------------------------------

# Patterns for detecting chapter/section headings in raw markdown
_CHAPTER_HEADING = re.compile(
    r"^#{1,3}\s+(Chapter\s+\d+|CHAPTER\s+\d+|第\d+章|Part\s+[IVX\d]+|PART\s+[IVX\d]+|Section\s+\d+)",
    re.M | re.I,
)
# Plain-text chapter headings (PDF-extracted, no # prefix)
_PLAIN_CHAPTER = re.compile(
    r"^(Chapter\s+\d+|CHAPTER\s+\d+|第\d+章|Part\s+[IVX\d]+|PART\s+[IVX\d]+)\b",
    re.M | re.I,
)
# Generic heading pattern for fallback splitting
_GENERIC_HEADING = re.compile(r"^#{1,4}\s+\S", re.M)


def _split_by_headings(lines: list[str], heading_pattern: re.Pattern[str]) -> list[tuple[str, int, int]]:
    """Split lines into chunks bounded by heading matches.

    Returns list of (chunk_title, start_line_0based, end_line_exclusive).
    Skips lines that look like table-of-contents entries (containing '...' or page numbers).
    """
    heading_indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if heading_pattern.match(stripped):
            # Skip table-of-contents lines (contain dots leader or trailing page numbers)
            if "..." in stripped or re.search(r"\d+\s*$", stripped):
                continue
            heading_indices.append(i)
    if not heading_indices:
        return []
    chunks = []
    for idx, start in enumerate(heading_indices):
        # Extract title from heading line, strip # marks
        title = re.sub(r"^#+\s*", "", lines[start]).strip()
        end = heading_indices[idx + 1] if idx + 1 < len(heading_indices) else len(lines)
        chunks.append((title, start, end))
    return chunks


def _split_by_line_count(lines: list[str], chunk_size: int) -> list[tuple[str, int, int]]:
    """Split lines into fixed-size chunks when no headings are found.

    For each chunk, attempt to extract a meaningful title from the first
    non-empty line (skip blank lines and short lines < 20 chars).
    """
    chunks = []
    for i in range(0, len(lines), chunk_size):
        # Find first meaningful line in chunk for title
        title = f"chunk_{i // chunk_size + 1}"
        for line in lines[i:i + chunk_size]:
            stripped = line.strip()
            if stripped and len(stripped) >= 20 and not stripped.startswith("---"):
                title = stripped[:80]
                break
        chunks.append((title, i, min(i + chunk_size, len(lines))))
    return chunks


def chunk_raw_document(
    raw_body: str,
    *,
    chunk_size: int = 500,
) -> list[dict[str, object]]:
    """Split a raw document body into chunks for per-chunk extraction.

    Strategy:
      1. Try chapter/section headings first (best semantic boundaries)
      2. Fall back to generic headings (# through ####)
      3. Fall back to fixed line count

    Each chunk dict has: chunk_id, chunk_title, chunk_body, start_line, end_line.
    """
    lines = raw_body.splitlines()

    # Strategy 1: chapter/section headings (Markdown # prefix)
    chunks = _split_by_headings(lines, _CHAPTER_HEADING)
    if chunks:
        strategy = "chapter_headings"
    else:
        # Strategy 2: generic headings (at least 3 to be meaningful)
        chunks = _split_by_headings(lines, _GENERIC_HEADING)
        if len(chunks) >= 3:
            strategy = "generic_headings"
        else:
            # Strategy 3: fixed line count
            # (plain-text chapter headings like "Chapter N" are unreliable
            # in PDF-extracted text — they appear in cross-references too)
            chunks = _split_by_line_count(lines, chunk_size)
            strategy = "fixed_lines"

    result = []
    for chunk_id, (title, start, end) in enumerate(chunks, start=1):
        body = "\n".join(lines[start:end])
        if not body.strip():
            continue
        result.append({
            "chunk_id": f"chunk_{chunk_id}",
            "chunk_title": title,
            "chunk_body": body,
            "start_line": start + 1,  # 1-based for user readability
            "end_line": end,          # 1-based inclusive
            "line_count": end - start,
        })
    return result


def prepare_chunked_payloads(
    *,
    vault: Path,
    raw_path: Path,
    title: str,
    author: str,
    date: str,
    source_url: str,
    slug: str,
    chunk_size: int = 500,
) -> dict[str, object]:
    """Generate chunked compile payloads for a large document.

    Returns a dict with:
      - metadata: article metadata
      - context: vault context (shared across all chunks)
      - chunks: list of per-chunk payloads, each containing:
          chunk_id, chunk_title, chunk_body, start_line, end_line,
          system_prompt (chunk-specific), user_prompt (chunk-specific)
      - chunk_prompt_template: template for per-chunk extraction
      - synthesis_prompt: prompt for final synthesis across all chunks
      - expected_output_schema_version: "2.0"
    """
    raw_text = raw_path.read_text(encoding="utf-8")
    _, raw_body = parse_frontmatter(raw_text)
    total_lines = len(raw_body.splitlines())

    # Collect vault context (shared across all chunks)
    context = collect_context(vault, slug, title, raw_body[:2000], lean=False)
    context.update(collect_related_pages(vault, title=title, raw_body=raw_body[:2000], slug=slug, lean=False))

    # Split into chunks
    chunks = chunk_raw_document(raw_body, chunk_size=chunk_size)
    if not chunks:
        raise RuntimeError("Document too short to chunk — use regular compile instead.")

    # Load system prompt for chunk extraction
    system_prompt = load_prompt_v2()

    # Build per-chunk user prompts
    chunk_payloads = []
    for chunk in chunks:
        chunk_user_prompt = _build_chunk_user_prompt(
            title=title,
            author=author,
            date=date,
            source_url=source_url,
            chunk_title=chunk["chunk_title"],
            chunk_body=chunk["chunk_body"],
            chunk_id=chunk["chunk_id"],
            total_chunks=len(chunks),
            context=context,
        )
        chunk_payloads.append({
            "chunk_id": chunk["chunk_id"],
            "chunk_title": chunk["chunk_title"],
            "chunk_body": chunk["chunk_body"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "line_count": chunk["line_count"],
            "system_prompt": system_prompt,
            "user_prompt": chunk_user_prompt,
        })

    # Build synthesis prompt (instructions for merging chunk results)
    synthesis_prompt = _build_synthesis_prompt(title, len(chunks))

    result = {
        "mode": "chunked-compile",
        "metadata": {
            "title": title,
            "author": author,
            "date": date,
            "source_url": source_url,
            "slug": slug,
            "vault": str(vault),
            "raw": str(raw_path),
            "total_lines": total_lines,
            "total_chunks": len(chunks),
        },
        "context": context,
        "chunks": chunk_payloads,
        "synthesis_prompt": synthesis_prompt,
        "expected_output_schema_version": "2.0",
        "chunk_extract_schema": _chunk_extract_schema(),
    }
    return result


def _build_chunk_user_prompt(
    *,
    title: str,
    author: str,
    date: str,
    source_url: str,
    chunk_title: str,
    chunk_body: str,
    chunk_id: str,
    total_chunks: int,
    context: dict[str, object],
) -> str:
    """Build a per-chunk extraction prompt."""
    parts = [
        f"你正在对一篇大文档的第 {chunk_id} 块（共 {total_chunks} 块）执行局部精读提取。",
        "",
        f"## 文档元数据",
        f"- 标题：{title}",
        f"- 作者：{author or '未知'}",
        f"- 当前块：{chunk_title}（{chunk_id}/{total_chunks}）",
        "",
        "## 任务",
        "对当前块的原文进行精读，提取以下结构化信息。只提取**当前块中确实出现的内容**，不要推测其他块可能包含的信息。",
        "",
        "## 输出格式",
        "输出一个合法 JSON 对象（不要输出 Markdown 围栏或解释文字），结构如下：",
        "",
        json.dumps(_chunk_extract_schema(), ensure_ascii=False, indent=2),
        "",
        "## 现有上下文",
        json.dumps({k: v for k, v in context.items() if k != "purpose"}, ensure_ascii=False, indent=2),
        "",
        "## 当前块原文",
        chunk_body,
    ]
    return "\n".join(parts)


def _build_synthesis_prompt(title: str, total_chunks: int) -> str:
    """Build the final synthesis prompt that instructs LLM how to merge chunk results."""
    return (
        f"你已完成对「{title}」的 {total_chunks} 块逐块精读提取。现在需要将所有块的结果合成为一份完整的 V2.0 compile JSON。\n"
        "\n"
        "## 合成规则\n"
        "\n"
        "1. **骨架生成力**：从所有块的 claims 中识别反复出现的核心因果驱动因素。生成力必须满足：\n"
        "   - 生成性：用它能推出文中关键现象\n"
        "   - 最小性：拿掉它，有现象解释不了\n"
        "   - 独立性：每对都能找到'一个变了另一个没变'的案例\n"
        "   1-3根生成力，每根一段 narrative。\n"
        "\n"
        "2. **key_points**：从所有块的 key_points 中筛选最重要的 5-8 条。优先选择跨多个块出现的论点。\n"
        "\n"
        "3. **claim_inventory**：从所有块的 claims 中筛选最重要的 4-6 条。优先选择跨块 reinforce 的 claim。\n"
        "   grounding_quote 使用该 claim 首次出现的块中的原文引用。\n"
        "\n"
        "4. **cross_domain_insights**：基于全部块的精读结果，寻找与 vault 已有知识的跨域联想。\n"
        "   必须包含 bridge_logic 和 migration_conclusion。\n"
        "\n"
        "5. **knowledge_proposals**：基于全部块的论点和 vault 上下文，判断值得建立的概念/实体/域页。\n"
        "\n"
        "6. **输出必须是完整的 V2.0 compile JSON**——按 ingest_compile_prompt_v2.md 的 schema 结构。\n"
        "   document_outputs 包含 brief 和 source；claim_inventory、knowledge_proposals 等在顶层。\n"
    )


def _chunk_extract_schema() -> dict[str, object]:
    """Schema for per-chunk extraction output (lighter than full V2.0)."""
    return {
        "chunk_id": "chunk_1",
        "chunk_title": "Chapter title",
        "claims": [
            {
                "claim": "one-sentence claim from this chunk",
                "claim_type": "observation | interpretation | prediction",
                "evidence_type": "fact | inference | assumption | hypothesis",
                "logic_risk": "none | circular | over_generalization | correlation_causation | selective_evidence",
                "confidence": "Seeded | Preliminary | Working | Supported | Stable",
                "grounding_quote": "exact text from this chunk (mandatory — must be found in chunk_body)",
                "evidence": ["supporting evidence"],
            }
        ],
        "key_points": [
            "one-sentence key point from this chunk",
        ],
        "data_points": [
            {"label": "metric name", "value": "metric value", "baseline": "comparison baseline"},
        ],
        "hidden_assumptions": [
            "assumption this chunk's argument depends on but doesn't state",
        ],
        "cross_references": [
            "references to other chunks or external concepts mentioned in this chunk",
        ],
    }


def extract_json(text: str) -> dict[str, object]:
    match = JSON_BLOCK.search(text)
    candidate = match.group(1) if match else text.strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        candidate = candidate[start : end + 1]
    return json.loads(candidate)


def env_config(model_override: str | None = None) -> dict[str, object] | None:
    mock_file = resolve_env("KWIKI_COMPILE_MOCK_FILE")
    if mock_file:
        return {"mock_file": mock_file}
    api_key = resolve_env("KWIKI_API_KEY")
    model = (model_override or resolve_env("KWIKI_COMPILE_MODEL")).strip()
    base = resolve_env("KWIKI_API_BASE") or "https://api.openai.com/v1"
    if not api_key or not model:
        return None
    return {
        "api_key": api_key,
        "model": model,
        "base": base.rstrip("/"),
        "temperature": float(resolve_env("KWIKI_COMPILE_TEMPERATURE", "0.2")),
        "max_tokens": int(resolve_env("KWIKI_COMPILE_MAX_TOKENS", "2200")),
    }


def call_openai_compatible(system_prompt: str, user_prompt: str, config: dict[str, object]) -> str:
    url = f"{config['base']}/chat/completions"
    payload = {
        "model": config["model"],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"LLM compile HTTP error: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM compile network error: {exc}") from exc
    try:
        return raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LLM compile response shape: {raw}") from exc


def normalize_string_list(value: object, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = re.sub(r"\s+", " ", item).strip().strip('"')
        if not text:
            continue
        if text not in normalized:
            normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


VALID_ORDINAL = {"Seeded", "Preliminary", "Working", "Supported", "Stable"}
VALID_EVIDENCE_TYPE = {"fact", "inference", "assumption", "hypothesis", "disputed", "gap"}


def coerce_confidence(value: object) -> str:
    """Coerce a confidence value to an ordinal label.

    Accepts the 5 ordinal labels. Falls back to 'Preliminary' for unknown values.
    """
    if isinstance(value, str):
        normalized = value.strip()
        if normalized in VALID_ORDINAL:
            return normalized
        # Backward compat: map legacy high/medium/low
        legacy = normalized.lower()
        if legacy == "high":
            return "Supported"
        if legacy == "medium":
            return "Working"
        if legacy == "low":
            return "Preliminary"
    return "Preliminary"


def coerce_evidence_type(value: object) -> str:
    """Coerce an evidence type value to a valid label."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_EVIDENCE_TYPE:
            return normalized
    return "assumption"


def normalize_proposal_list(value: object, limit: int = 8) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "").strip() if isinstance(item.get("name"), str) else ""
        action = item.get("action", "").strip() if isinstance(item.get("action"), str) else "defer"
        reason = item.get("reason", "").strip() if isinstance(item.get("reason"), str) else ""
        evidence = normalize_string_list(item.get("evidence"), limit=4)
        if not name or not reason:
            continue
        normalized.append(
            {
                "name": name,
                "action": action or "defer",
                "reason": reason,
                "confidence": coerce_confidence(item.get("confidence")),
                "evidence_type": coerce_evidence_type(item.get("evidence_type")),
                "grounding_quote": item.get("grounding_quote", "").strip() if isinstance(item.get("grounding_quote"), str) else "",
                "evidence": evidence,
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def normalize_cross_domain_insights(value: object, limit: int = 5) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        mapped_concept = item.get("mapped_concept", "").strip() if isinstance(item.get("mapped_concept"), str) else ""
        target_domain = item.get("target_domain", "").strip() if isinstance(item.get("target_domain"), str) else ""
        bridge_logic = item.get("bridge_logic", "").strip() if isinstance(item.get("bridge_logic"), str) else ""
        if not mapped_concept or not target_domain or not bridge_logic:
            continue
        normalized.append(
            {
                "mapped_concept": mapped_concept,
                "target_domain": target_domain,
                "bridge_logic": bridge_logic,
                "potential_question": item.get("potential_question", "").strip() if isinstance(item.get("potential_question"), str) else "",
                "confidence": coerce_confidence(item.get("confidence")),
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def normalize_update_proposals(value: object, limit: int = 8) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        target_page = item.get("target_page", "").strip() if isinstance(item.get("target_page"), str) else ""
        target_type = item.get("target_type", "").strip() if isinstance(item.get("target_type"), str) else ""
        action = item.get("action", "").strip() if isinstance(item.get("action"), str) else "defer"
        reason = item.get("reason", "").strip() if isinstance(item.get("reason"), str) else ""
        patch = item.get("patch") if isinstance(item.get("patch"), dict) else {}
        if not target_page or not target_type or not reason:
            continue
        normalized.append(
            {
                "target_page": target_page,
                "target_type": target_type,
                "action": action,
                "reason": reason,
                "confidence": coerce_confidence(item.get("confidence")),
                "evidence": normalize_string_list(item.get("evidence"), limit=4),
                "patch": {
                    "mode": patch.get("mode", "draft_note") if isinstance(patch.get("mode"), str) else "draft_note",
                    "section": patch.get("section", "").strip() if isinstance(patch.get("section"), str) else "",
                    "content": normalize_string_list(patch.get("content"), limit=8),
                    "summary_delta": normalize_string_list(patch.get("summary_delta"), limit=6),
                    "questions_open": normalize_string_list(patch.get("questions_open"), limit=4),
                },
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def normalize_claim_inventory(value: object, limit: int = 10) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        claim = item.get("claim", "").strip() if isinstance(item.get("claim"), str) else ""
        claim_type = item.get("claim_type", "").strip() if isinstance(item.get("claim_type"), str) else "interpretation"
        if not claim:
            continue
        normalized.append(
            {
                "claim": claim,
                "claim_type": claim_type,
                "evidence_type": coerce_evidence_type(item.get("evidence_type")),
                "confidence": coerce_confidence(item.get("confidence")),
                "grounding_quote": item.get("grounding_quote", "").strip() if isinstance(item.get("grounding_quote"), str) else "",
                "evidence": normalize_string_list(item.get("evidence"), limit=4),
                "suggested_destination": normalize_string_list(item.get("suggested_destination"), limit=4),
                "verification_needed": bool(item.get("verification_needed", False)),
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def normalize_stance_impact_list(value: object, limit: int = 5) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, object]] = []
    valid_impacts = {"reinforce", "contradict", "extend", "neutral"}
    for item in value:
        if not isinstance(item, dict):
            continue
        topic = item.get("stance_topic", "").strip() if isinstance(item.get("stance_topic"), str) else ""
        impact = item.get("impact", "neutral").strip().lower() if isinstance(item.get("impact"), str) else "neutral"
        evidence = item.get("evidence", "").strip() if isinstance(item.get("evidence"), str) else ""
        if not topic:
            continue
        if impact not in valid_impacts:
            impact = "neutral"
        normalized.append(
            {
                "stance_topic": topic,
                "impact": impact,
                "evidence": evidence,
                "confidence": coerce_confidence(item.get("confidence")),
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def normalize_review_hints(value: object) -> dict[str, object]:
    data = value if isinstance(value, dict) else {}
    priority = data.get("priority", "medium") if isinstance(data.get("priority"), str) else "medium"
    if priority not in {"high", "medium", "low"}:
        priority = "medium"
    return {
        "priority": priority,
        "needs_human_review": bool(data.get("needs_human_review", True)),
        "suggested_review_targets": normalize_string_list(data.get("suggested_review_targets"), limit=6),
    }


def normalize_result_v2(data: dict[str, object]) -> dict[str, object]:
    if str(data.get("version", "")).strip() != "2.0":
        # Friendly hint if LLM used schema_version instead of version
        if "schema_version" in data:
            raise RuntimeError(
                f"LLM output uses 'schema_version' instead of 'version'. "
                f"Expected: {{\"version\": \"2.0\", \"document_outputs\": {{...}}}}. "
                f"Got keys: {list(data.keys())[:10]}"
            )
        raise RuntimeError(
            f"LLM compile result missing 'version: \"2.0\"'. "
            f"Expected: {{\"version\": \"2.0\", \"document_outputs\": {{...}}}}. "
            f"Got keys: {list(data.keys())[:10]}"
        )
    compile_target = data.get("compile_target") if isinstance(data.get("compile_target"), dict) else {}
    document_outputs = data.get("document_outputs") if isinstance(data.get("document_outputs"), dict) else {}
    brief = document_outputs.get("brief") if isinstance(document_outputs.get("brief"), dict) else {}
    source = document_outputs.get("source") if isinstance(document_outputs.get("source"), dict) else {}
    result = {
        "version": "2.0",
        "compile_target": {
            "vault": compile_target.get("vault", "").strip() if isinstance(compile_target.get("vault"), str) else "",
            "raw_path": compile_target.get("raw_path", "").strip() if isinstance(compile_target.get("raw_path"), str) else "",
            "slug": compile_target.get("slug", "").strip() if isinstance(compile_target.get("slug"), str) else "",
            "title": compile_target.get("title", "").strip() if isinstance(compile_target.get("title"), str) else "",
            "author": compile_target.get("author", "").strip() if isinstance(compile_target.get("author"), str) else "",
            "date": compile_target.get("date", "").strip() if isinstance(compile_target.get("date"), str) else "",
            "source_url": compile_target.get("source_url", "").strip() if isinstance(compile_target.get("source_url"), str) else "",
        },
        "document_outputs": {
            "brief": {
                "one_sentence": brief.get("one_sentence", "").strip() if isinstance(brief.get("one_sentence"), str) else "",
                "key_points": normalize_string_list(brief.get("key_points"), limit=7),
                "who_should_read": normalize_string_list(brief.get("who_should_read"), limit=4),
                "why_revisit": normalize_string_list(brief.get("why_revisit"), limit=4),
            },
            "source": {
                "core_summary": normalize_string_list(source.get("core_summary"), limit=8),
                "knowledge_base_relation": normalize_string_list(source.get("knowledge_base_relation"), limit=6),
                "contradictions": normalize_string_list(source.get("contradictions"), limit=4),
                "reinforcements": normalize_string_list(source.get("reinforcements"), limit=4),
            },
        },
        "knowledge_proposals": {
            "domains": normalize_proposal_list((data.get("knowledge_proposals") or {}).get("domains") if isinstance(data.get("knowledge_proposals"), dict) else [], limit=6),
            "concepts": normalize_proposal_list((data.get("knowledge_proposals") or {}).get("concepts") if isinstance(data.get("knowledge_proposals"), dict) else [], limit=10),
            "entities": normalize_proposal_list((data.get("knowledge_proposals") or {}).get("entities") if isinstance(data.get("knowledge_proposals"), dict) else [], limit=10),
        },
        "update_proposals": normalize_update_proposals(data.get("update_proposals"), limit=8),
        "claim_inventory": normalize_claim_inventory(data.get("claim_inventory"), limit=10),
        "open_questions": normalize_string_list(data.get("open_questions"), limit=6),
        "cross_domain_insights": normalize_cross_domain_insights(data.get("cross_domain_insights"), limit=5),
        "stance_impacts": normalize_stance_impact_list(data.get("stance_impacts"), limit=5),
        "review_hints": normalize_review_hints(data.get("review_hints")),
    }
    if not result["document_outputs"]["brief"]["one_sentence"]:
        raise RuntimeError("LLM compile result missing document_outputs.brief.one_sentence")
    if not result["document_outputs"]["brief"]["key_points"]:
        raise RuntimeError("LLM compile result missing document_outputs.brief.key_points")
    if not result["document_outputs"]["source"]["core_summary"]:
        raise RuntimeError("LLM compile result missing document_outputs.source.core_summary")
    return result


def compile_article_v2(
    *,
    vault: Path,
    raw_path: Path,
    title: str,
    author: str,
    date: str,
    source_url: str,
    slug: str,
    model_override: str | None = None,
) -> dict[str, object]:
    config = env_config(model_override=model_override)
    if config is None:
        raise RuntimeError("LLM compile is not configured. Set WECHAT_WIKI_API_KEY and WECHAT_WIKI_COMPILE_MODEL.")
    if "mock_file" in config:
        mock_path = Path(str(config["mock_file"])).expanduser().resolve()
        if not mock_path.exists():
            raise RuntimeError(f"Mock compile file not found: {mock_path}")
        return {"schema_version": "2.0", "result": normalize_result_v2(json.loads(mock_path.read_text(encoding="utf-8")))}
    payload = prepare_compile_payload_v2(
        vault=vault,
        raw_path=raw_path,
        title=title,
        author=author,
        date=date,
        source_url=source_url,
        slug=slug,
    )
    content = call_openai_compatible(str(payload["system_prompt"]), str(payload["user_prompt"]), config)
    return {"schema_version": "2.0", "result": normalize_result_v2(extract_json(content))}


def compile_article_auto(
    *,
    vault: Path,
    raw_path: Path,
    title: str,
    author: str,
    date: str,
    source_url: str,
    slug: str,
    model_override: str | None = None,
    schema_version: str = "2.0",
) -> dict[str, object]:
    # V1.0 compile removed — always use v2
    return compile_article_v2(
        vault=vault,
        raw_path=raw_path,
        title=title,
        author=author,
        date=date,
        source_url=source_url,
        slug=slug,
        model_override=model_override,
    )


# ---------------------------------------------------------------------------
# Two-step CoT Ingest: Step 1 — fact extraction
# ---------------------------------------------------------------------------

def build_fact_extraction_user_prompt(
    title: str,
    author: str,
    date: str,
    source_url: str,
    raw_body: str,
    context: dict[str, object],
) -> str:
    parts = [
        "请从以下文章中提取结构化事实清单。",
        "",
        "## 来源元数据",
        f"- 标题：{title}",
        f"- 作者：{author or '未知'}",
        f"- 日期：{date or '未知'}",
        f"- 链接：{source_url or '未知'}",
    ]
    purpose_text = context.get("purpose", "") if isinstance(context, dict) else ""
    if purpose_text:
        parts.extend([
            "",
            "## 研究方向（purpose.md）",
            "提取事实时，优先关注与以下领域相关的内容。",
            purpose_text,
        ])
    parts.extend([
        "",
        "## 原文正文",
        raw_body,
    ])
    return "\n".join(parts)


def normalize_fact_inventory(data: dict[str, object]) -> dict[str, object]:
    """Validate and normalize a fact_inventory from LLM output."""
    inventory = data.get("fact_inventory") if isinstance(data.get("fact_inventory"), dict) else data
    if not isinstance(inventory, dict):
        raise RuntimeError("fact_inventory is not a dict")

    # Normalize atomic_facts
    raw_facts = inventory.get("atomic_facts", [])
    if not isinstance(raw_facts, list):
        raw_facts = []
    atomic_facts: list[dict[str, object]] = []
    for i, item in enumerate(raw_facts):
        if not isinstance(item, dict):
            continue
        fact_text = item.get("fact", "").strip() if isinstance(item.get("fact"), str) else ""
        if not fact_text:
            continue
        atomic_facts.append({
            "id": item.get("id", f"f{i+1}").strip() if isinstance(item.get("id"), str) else f"f{i+1}",
            "fact": fact_text,
            "evidence_type": coerce_evidence_type(item.get("evidence_type")),
            "confidence": coerce_confidence(item.get("confidence")),
            "grounding_quote": item.get("grounding_quote", "").strip() if isinstance(item.get("grounding_quote"), str) else "",
            "paragraph_ref": item.get("paragraph_ref", "").strip() if isinstance(item.get("paragraph_ref"), str) else "",
        })

    # Normalize argument_structure
    arg_struct = inventory.get("argument_structure") if isinstance(inventory.get("argument_structure"), dict) else {}
    generators: list[dict[str, str]] = []
    for g in arg_struct.get("generators", []):
        if not isinstance(g, dict):
            continue
        name = g.get("name", "").strip() if isinstance(g.get("name"), str) else ""
        narrative = g.get("narrative", "").strip() if isinstance(g.get("narrative"), str) else ""
        if name and narrative:
            generators.append({
                "name": name,
                "narrative": narrative,
                "counterfactual": g.get("counterfactual", "").strip() if isinstance(g.get("counterfactual"), str) else "",
            })

    logic_chain: list[dict[str, object]] = []
    for step in arg_struct.get("logic_chain", []):
        if not isinstance(step, dict):
            continue
        step_text = step.get("step", "").strip() if isinstance(step.get("step"), str) else ""
        if not step_text:
            continue
        step_type = step.get("type", "intermediate") if isinstance(step.get("type"), str) else "intermediate"
        if step_type not in {"premise", "intermediate", "conclusion"}:
            step_type = "intermediate"
        depends_on = step.get("depends_on", []) if isinstance(step.get("depends_on"), list) else []
        logic_chain.append({
            "step": step_text,
            "type": step_type,
            "depends_on": [d for d in depends_on if isinstance(d, str)],
        })

    assumptions = normalize_string_list(arg_struct.get("assumptions"), limit=8)

    # Normalize key_entities
    raw_entities = inventory.get("key_entities", [])
    if not isinstance(raw_entities, list):
        raw_entities = []
    valid_entity_types = {"person", "org", "product", "theory", "method", "concept", "other"}
    key_entities: list[dict[str, str]] = []
    for e in raw_entities:
        if not isinstance(e, dict):
            continue
        name = e.get("name", "").strip() if isinstance(e.get("name"), str) else ""
        if not name:
            continue
        etype = e.get("type", "other") if isinstance(e.get("type"), str) else "other"
        if etype not in valid_entity_types:
            etype = "other"
        key_entities.append({
            "name": name,
            "type": etype,
            "definition": e.get("definition", "").strip() if isinstance(e.get("definition"), str) else "",
            "grounding_quote": e.get("grounding_quote", "").strip() if isinstance(e.get("grounding_quote"), str) else "",
        })

    # Normalize cross_domain_hooks
    raw_hooks = inventory.get("cross_domain_hooks", [])
    if not isinstance(raw_hooks, list):
        raw_hooks = []
    cross_domain_hooks: list[dict[str, object]] = []
    for h in raw_hooks:
        if not isinstance(h, dict):
            continue
        pattern = h.get("pattern", "").strip() if isinstance(h.get("pattern"), str) else ""
        bridge_logic = h.get("bridge_logic", "").strip() if isinstance(h.get("bridge_logic"), str) else ""
        if not pattern or not bridge_logic:
            continue
        potential_domains = [d for d in (h.get("potential_domains") or []) if isinstance(d, str)]
        cross_domain_hooks.append({
            "pattern": pattern,
            "potential_domains": potential_domains,
            "bridge_logic": bridge_logic,
            "confidence": coerce_confidence(h.get("confidence")),
        })

    # Normalize quantitative_markers
    raw_markers = inventory.get("quantitative_markers", [])
    if not isinstance(raw_markers, list):
        raw_markers = []
    quantitative_markers: list[dict[str, str]] = []
    for m in raw_markers:
        if not isinstance(m, dict):
            continue
        marker = m.get("marker", "").strip() if isinstance(m.get("marker"), str) else ""
        value = m.get("value", "").strip() if isinstance(m.get("value"), str) else ""
        if not marker:
            continue
        quantitative_markers.append({
            "marker": marker,
            "value": value,
            "context": m.get("context", "").strip() if isinstance(m.get("context"), str) else "",
        })

    open_questions = normalize_string_list(inventory.get("open_questions"), limit=8)

    return {
        "atomic_facts": atomic_facts,
        "argument_structure": {
            "generators": generators,
            "logic_chain": logic_chain,
            "assumptions": assumptions,
        },
        "key_entities": key_entities,
        "cross_domain_hooks": cross_domain_hooks,
        "open_questions": open_questions,
        "quantitative_markers": quantitative_markers,
    }


def extract_facts(
    *,
    vault: Path,
    raw_path: Path,
    title: str,
    author: str,
    date: str,
    source_url: str,
    model_override: str | None = None,
) -> dict[str, object]:
    """Step 1 of two-step CoT: extract fact_inventory from the source article."""
    config = env_config(model_override=model_override)
    if config is None:
        raise RuntimeError("LLM compile is not configured. Set WECHAT_WIKI_API_KEY and WECHAT_WIKI_COMPILE_MODEL.")

    raw_text = raw_path.read_text(encoding="utf-8")
    _, raw_body = parse_frontmatter(raw_text)
    context = collect_context(vault, Path(raw_path).stem, title, raw_body)

    system_prompt = load_fact_extraction_prompt()
    user_prompt = build_fact_extraction_user_prompt(title, author, date, source_url, raw_body, context)

    content = call_openai_compatible(system_prompt, user_prompt, config)
    data = extract_json(content)
    return normalize_fact_inventory(data)


def compile_article_two_step(
    *,
    vault: Path,
    raw_path: Path,
    title: str,
    author: str,
    date: str,
    source_url: str,
    slug: str,
    model_override: str | None = None,
) -> dict[str, object]:
    """Two-step CoT ingest: Step 1 extracts facts, Step 2 compiles wiki structure constrained by facts.

    Returns:
        {
            "schema_version": "2.0",
            "fact_inventory": { ... },
            "result": { ... }  # the v2 compile output
        }
    """
    # Step 1: Extract facts
    fact_inventory = extract_facts(
        vault=vault,
        raw_path=raw_path,
        title=title,
        author=author,
        date=date,
        source_url=source_url,
        model_override=model_override,
    )

    # Step 2: Compile wiki structure constrained by fact_inventory
    config = env_config(model_override=model_override)
    if config is None:
        raise RuntimeError("LLM compile is not configured.")

    if "mock_file" in config:
        mock_path = Path(str(config["mock_file"])).expanduser().resolve()
        if not mock_path.exists():
            raise RuntimeError(f"Mock compile file not found: {mock_path}")
        result = normalize_result_v2(json.loads(mock_path.read_text(encoding="utf-8")))
        return {"schema_version": "2.0", "fact_inventory": fact_inventory, "result": result}

    raw_text = raw_path.read_text(encoding="utf-8")
    _, raw_body = parse_frontmatter(raw_text)
    context = collect_context(vault, slug, title, raw_body)
    context.update(collect_related_pages(vault, title=title, raw_body=raw_body, slug=slug))

    system_prompt = load_prompt_v2()
    user_prompt = build_user_prompt_v2(
        title, author, date, source_url, raw_body, context,
        fact_inventory=fact_inventory,
    )

    content = call_openai_compatible(system_prompt, user_prompt, config)
    result = normalize_result_v2(extract_json(content))

    return {
        "schema_version": "2.0",
        "fact_inventory": fact_inventory,
        "result": result,
    }


def main() -> int:
    fix_windows_encoding()
    args = parse_args()
    slug = args.slug or args.raw.stem
    if args.extract_facts_only:
        result = extract_facts(
            vault=args.vault.resolve(),
            raw_path=args.raw.resolve(),
            title=args.title,
            author=args.author,
            date=args.date,
            source_url=args.source_url,
            model_override=args.model,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.chunked:
        payload = prepare_chunked_payloads(
            vault=args.vault.resolve(),
            raw_path=args.raw.resolve(),
            title=args.title,
            author=args.author,
            date=args.date,
            source_url=args.source_url,
            slug=slug,
            chunk_size=args.chunk_size,
        )
        # Write to file (chunked payloads are too large for stdout)
        if args.chunk_output:
            out_path = args.chunk_output
        else:
            out_path = default_runtime_dir() / "compile-payloads" / f"{slug}_chunks.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {
            "mode": "chunked-compile",
            "total_chunks": payload["metadata"]["total_chunks"],
            "total_lines": payload["metadata"]["total_lines"],
            "output_file": str(out_path),
            "chunks": [
                {"chunk_id": c["chunk_id"], "chunk_title": c["chunk_title"], "line_count": c["line_count"]}
                for c in payload["chunks"]
            ],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.two_step:
        result = compile_article_two_step(
            vault=args.vault.resolve(),
            raw_path=args.raw.resolve(),
            title=args.title,
            author=args.author,
            date=args.date,
            source_url=args.source_url,
            slug=slug,
            model_override=args.model,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.prepare_only:
        result = prepare_compile_payload_v2(
            vault=args.vault.resolve(),
            raw_path=args.raw.resolve(),
            title=args.title,
            author=args.author,
            date=args.date,
            source_url=args.source_url,
            slug=slug,
            lean=args.lean,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = compile_article_auto(
            vault=args.vault.resolve(),
            raw_path=args.raw.resolve(),
            title=args.title,
            author=args.author,
            date=args.date,
            source_url=args.source_url,
            slug=slug,
            model_override=args.model,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
