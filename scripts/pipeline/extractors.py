"""Content extraction utilities for the obsidian-wiki pipeline.

Intelligent extraction (domain detection, concept extraction, entity extraction)
is handled by LLM compile v2. This module provides slug generation, page counting,
and vault distribution utilities only.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .types import (
    Article,
    CONCEPT_PAGE_THRESHOLD,
    CONCEPT_STOPWORDS,
    ENTITY_PAGE_THRESHOLD,
)
from .text_utils import plain_text, sanitize_filename, body_text, parse_frontmatter


# ---------------------------------------------------------------------------
# Slug generation (pure utility, no intelligence)
# ---------------------------------------------------------------------------

def concept_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


def entity_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


def domain_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


def comparison_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


# ---------------------------------------------------------------------------
# Page counting and maturity checks
# ---------------------------------------------------------------------------

def page_mention_count(vault: Path, folder: str, term: str) -> int:
    count = 0
    for path in (vault / "wiki" / folder).glob("*.md"):
        text = plain_text(path.read_text(encoding="utf-8"))
        if term in text:
            count += 1
    return count


def mature_concepts(vault: Path, names: list[str]) -> list[str]:
    mature: list[str] = []
    for name in names:
        if page_mention_count(vault, "sources", name) >= CONCEPT_PAGE_THRESHOLD:
            mature.append(name)
    return mature


def mature_entities(vault: Path, names: list[str]) -> list[str]:
    mature: list[str] = []
    for name in names:
        if page_mention_count(vault, "sources", name) >= ENTITY_PAGE_THRESHOLD:
            mature.append(name)
    return mature


def existing_taxonomy_links(
    vault: Path,
    folder: str,
    names: list[str],
    slug_fn,
) -> list[str]:
    linked: list[str] = []
    for name in names:
        if not isinstance(name, str) or not name.strip():
            continue
        path = vault / "wiki" / folder / f"{slug_fn(name)}.md"
        if path.exists() and name not in linked:
            linked.append(name)
    return linked


# ---------------------------------------------------------------------------
# Vault domain distribution (reads existing pages)
# ---------------------------------------------------------------------------

def vault_domain_distribution(vault: Path) -> dict[str, int]:
    """Read existing domain pages and return {domain_name: source_count}."""
    domains: dict[str, int] = {}
    domains_dir = vault / "wiki" / "domains"
    if not domains_dir.exists():
        return domains
    for dpath in domains_dir.glob("*.md"):
        text = dpath.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        name = meta.get("title", "").strip('"') or dpath.stem
        source_links = re.findall(r"\[\[sources/[^\]]+\]\]", text)
        domains[name] = len(source_links)
    return domains


def detect_domain_mismatch(
    article: Article,
    vault: Path,
    article_domains: list[str] | None = None,
) -> dict[str, object]:
    """Detect whether new content's domains mismatch the existing vault.

    When article_domains is None (LLM not available), returns a conservative
    result indicating no mismatch rather than attempting script-based detection.
    """
    vault_domains_map = vault_domain_distribution(vault)
    vault_domain_names = list(vault_domains_map.keys())

    if article_domains is None:
        # LLM not available — cannot determine domains, be conservative
        return {
            "is_mismatch": False,
            "article_domains": [],
            "vault_domains": vault_domain_names,
            "overlap_domains": [],
            "warning": "",
            "suggested_domain_name": "",
        }

    if not vault_domain_names:
        overlap: list[str] = []
    else:
        overlap = [d for d in article_domains if d in vault_domain_names and d != "待归域"]

    is_mismatch = False
    if vault_domain_names and article_domains == ["待归域"]:
        is_mismatch = True
    elif vault_domain_names and not overlap and article_domains != ["待归域"]:
        is_mismatch = True

    warning = ""
    suggested_domain = ""
    if is_mismatch and article_domains:
        suggested_domain = article_domains[0]
        vault_names_str = "、".join(vault_domain_names[:5])
        warning = (
            f"此内容与知识库现有领域（{vault_names_str}）无交叉。"
            f"建议：① 创建「{suggested_domain}」新领域并归入 ② 放入待归域稍后处理"
        )

    return {
        "is_mismatch": is_mismatch,
        "article_domains": article_domains,
        "vault_domains": vault_domain_names,
        "overlap_domains": overlap,
        "warning": warning,
        "suggested_domain_name": suggested_domain,
    }
