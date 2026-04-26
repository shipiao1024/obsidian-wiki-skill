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


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)
WIKILINK = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.S)

DEFAULT_DOMAINS = {
    "自动驾驶": ["自动驾驶", "智驾", "AIDV", "FSD", "L2", "L3", "EEA", "端到端", "BEV"],
    "AI 工程": ["Claude", "Codex", "LLM", "RAG", "Agent", "模型", "推理", "Transformer"],
    "机器人": ["机器人", "具身", "机械臂"],
    "商业分析": ["公司", "市场", "竞争", "商业", "投资", "融资"],
}
DOMAIN_MIN_SCORE = {
    "自动驾驶": 4,
    "AI 工程": 4,
    "机器人": 4,
    "商业分析": 3,
}


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
    parser.add_argument("--schema-version", choices=["1.0", "2.0"], default="2.0", help="Compile output schema version.")
    parser.add_argument("--prepare-only", action="store_true", help="Only emit compile context and prompts for Codex/Claude-style interactive compilation.")
    parser.add_argument("--lean", action="store_true", help="In prepare-only mode, omit system_prompt/user_prompt from output and filter noisy synthesis excerpts. Reduces context payload by ~60%%.")
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


def detect_domains(title: str, body: str) -> list[str]:
    scores: dict[str, int] = {}
    for domain, keywords in DEFAULT_DOMAINS.items():
        score = 0
        for keyword in keywords:
            if keyword in title:
                score += 3
            if keyword in body:
                score += 2 + min(body.count(keyword), 3)
        scores[domain] = score
    found = [domain for domain, score in scores.items() if score >= DOMAIN_MIN_SCORE.get(domain, 3)]
    return found[:3]


def page_excerpt(path: Path, limit: int = 1200) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    return plain_text(body)[:limit].strip()


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


def prompt_path() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "prompts" / "ingest_compile_prompt.md"


def prompt_path_v2() -> Path:
    return Path(__file__).resolve().parents[1] / "references" / "prompts" / "ingest_compile_prompt_v2.md"


def load_prompt() -> str:
    path = prompt_path()
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_prompt_v2() -> str:
    path = prompt_path_v2()
    if not path.exists():
        raise RuntimeError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def build_user_prompt(
    title: str,
    author: str,
    date: str,
    source_url: str,
    raw_body: str,
    context: dict[str, object],
) -> str:
    return "\n".join(
        [
            "请基于以下输入编译单篇来源。",
            "",
            "## 来源元数据",
            f"- 标题：{title}",
            f"- 作者：{author or '未知'}",
            f"- 日期：{date or '未知'}",
            f"- 链接：{source_url or '未知'}",
            "",
            "## 当前相关 wiki 上下文",
            f"- 旧 brief：{context.get('existing_brief') or '无'}",
            f"- 旧 source：{context.get('existing_source') or '无'}",
            f"- 规则检测主题域：{', '.join(context.get('detected_domains', [])) or '无'}",
            "",
            "## 相关主题页上下文",
            json.dumps(context.get("related_domains", {}), ensure_ascii=False, indent=2),
            "",
            "## 原文正文",
            raw_body,
        ]
    )


def build_user_prompt_v2(
    title: str,
    author: str,
    date: str,
    source_url: str,
    raw_body: str,
    context: dict[str, object],
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
    parts.extend([
        "",
        "## 现有上下文",
        json.dumps({k: v for k, v in context.items() if k != "purpose"}, ensure_ascii=False, indent=2),
        "",
        "## 原文正文",
        raw_body,
    ])
    return "\n".join(parts)


def prepare_compile_payload(
    *,
    vault: Path,
    raw_path: Path,
    title: str,
    author: str,
    date: str,
    source_url: str,
    slug: str,
) -> dict[str, object]:
    raw_text = raw_path.read_text(encoding="utf-8")
    _, raw_body = parse_frontmatter(raw_text)
    context = collect_context(vault, slug, title, raw_body)
    system_prompt = load_prompt()
    user_prompt = build_user_prompt(title, author, date, source_url, raw_body, context)
    return {
        "mode": "agent-interactive-compile",
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
        "expected_output_schema": {
            "brief": {
                "one_sentence": "string",
                "key_points": ["string"],
                "who_should_read": ["string"],
                "why_revisit": ["string"],
            },
            "source": {
                "core_summary": ["string"],
                "candidate_concepts": ["string"],
                "candidate_entities": ["string"],
                "domains": ["string"],
                "knowledge_base_relation": ["string"],
                "contradictions": ["string"],
                "reinforcements": ["string"],
            },
        },
    }


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


def coerce_confidence(value: object) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"high", "medium", "low"}:
            return normalized
    return "low"


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
                "confidence": coerce_confidence(item.get("confidence")),
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


def normalize_result(data: dict[str, object]) -> dict[str, object]:
    brief = data.get("brief") if isinstance(data.get("brief"), dict) else {}
    source = data.get("source") if isinstance(data.get("source"), dict) else {}
    result = {
        "brief": {
            "one_sentence": brief.get("one_sentence", "").strip() if isinstance(brief.get("one_sentence"), str) else "",
            "key_points": normalize_string_list(brief.get("key_points"), limit=7),
            "who_should_read": normalize_string_list(brief.get("who_should_read"), limit=4),
            "why_revisit": normalize_string_list(brief.get("why_revisit"), limit=4),
        },
        "source": {
            "core_summary": normalize_string_list(source.get("core_summary"), limit=8),
            "candidate_concepts": normalize_string_list(source.get("candidate_concepts"), limit=10),
            "candidate_entities": normalize_string_list(source.get("candidate_entities"), limit=10),
            "domains": normalize_string_list(source.get("domains"), limit=3),
            "knowledge_base_relation": normalize_string_list(source.get("knowledge_base_relation"), limit=6),
            "contradictions": normalize_string_list(source.get("contradictions"), limit=4),
            "reinforcements": normalize_string_list(source.get("reinforcements"), limit=4),
        },
    }
    if not result["brief"]["one_sentence"]:
        raise RuntimeError("LLM compile result missing brief.one_sentence")
    if not result["brief"]["key_points"]:
        raise RuntimeError("LLM compile result missing brief.key_points")
    if not result["source"]["core_summary"]:
        raise RuntimeError("LLM compile result missing source.core_summary")
    return result


def normalize_result_v2(data: dict[str, object]) -> dict[str, object]:
    if str(data.get("version", "")).strip() != "2.0":
        raise RuntimeError("LLM compile result missing version 2.0")
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


def compile_article(
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
    prepare_compile_payload(
        vault=vault,
        raw_path=raw_path,
        title=title,
        author=author,
        date=date,
        source_url=source_url,
        slug=slug,
    )
    config = env_config(model_override=model_override)
    if config is None:
        raise RuntimeError("LLM compile is not configured. Set WECHAT_WIKI_API_KEY and WECHAT_WIKI_COMPILE_MODEL.")
    if "mock_file" in config:
        mock_path = Path(str(config["mock_file"])).expanduser().resolve()
        if not mock_path.exists():
            raise RuntimeError(f"Mock compile file not found: {mock_path}")
        return normalize_result(json.loads(mock_path.read_text(encoding="utf-8")))
    payload = prepare_compile_payload(
        vault=vault,
        raw_path=raw_path,
        title=title,
        author=author,
        date=date,
        source_url=source_url,
        slug=slug,
    )
    system_prompt = str(payload["system_prompt"])
    user_prompt = str(payload["user_prompt"])
    content = call_openai_compatible(system_prompt, user_prompt, config)
    data = extract_json(content)
    return normalize_result(data)


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
    if schema_version == "1.0":
        return {
            "schema_version": "1.0",
            "result": compile_article(
                vault=vault,
                raw_path=raw_path,
                title=title,
                author=author,
                date=date,
                source_url=source_url,
                slug=slug,
                model_override=model_override,
            ),
        }
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


def main() -> int:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    slug = args.slug or args.raw.stem
    if args.prepare_only:
        lean = args.lean
        if args.schema_version == "1.0":
            result = prepare_compile_payload(
                vault=args.vault.resolve(),
                raw_path=args.raw.resolve(),
                title=args.title,
                author=args.author,
                date=args.date,
                source_url=args.source_url,
                slug=slug,
            )
            if lean:
                result.pop("system_prompt", None)
                result.pop("user_prompt", None)
        else:
            result = prepare_compile_payload_v2(
                vault=args.vault.resolve(),
                raw_path=args.raw.resolve(),
                title=args.title,
                author=args.author,
                date=args.date,
                source_url=args.source_url,
                slug=slug,
                lean=lean,
            )
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
            schema_version=args.schema_version,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
