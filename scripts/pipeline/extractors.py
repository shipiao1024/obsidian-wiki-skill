"""Content extraction utilities for the obsidian-wiki pipeline."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .types import (
    Article,
    CONCEPT_PAGE_THRESHOLD,
    CONCEPT_STOPWORDS,
    DEFAULT_DOMAINS,
    DOMAIN_MIN_SCORE,
    ENTITY_PAGE_THRESHOLD,
    GENERIC_ENTITY_STOPWORDS,
    ENGLISH_ENTITY_STOPWORDS,
)
from .text_utils import plain_text, sanitize_filename, body_text, body_lines, parse_frontmatter

_CONCEPT_PARTICLES = set("的了是在和与或而但如把被让给到从向对为以上下中里外前后时地得着过呢吧吗啊呀嘛么也又都还就只已可要会能该")

_DEFINITION_PATTERNS = [
    re.compile(r"所谓([一-鿿]{2,6})(?:是指|指的是|，|。|$)", re.M),
    re.compile(r"([一-鿿]{2,6})(?:是指|指的是)", re.M),
]

_QUESTION_STOPWORDS = CONCEPT_STOPWORDS | {"什么", "为什么", "如何", "怎么", "怎样", "哪个", "哪些"}


def _is_clean_concept(text: str) -> bool:
    if len(text) < 2:
        return False
    if text[0] in _CONCEPT_PARTICLES or text[-1] in _CONCEPT_PARTICLES:
        return False
    particle_count = sum(1 for ch in text if ch in _CONCEPT_PARTICLES)
    if len(text) <= 3:
        return particle_count == 0
    return particle_count <= 1


def _extract_clean_concepts(text: str, max_concepts: int = 20) -> list[str]:
    """Extract clean concept terms from text using n-gram frequency analysis.

    Works by splitting text into sentences first, then extracting n-grams
    within each sentence to avoid cross-sentence noise.
    Prefers longer concepts over their shorter substrings.
    """
    # Step 1: Extract from definition patterns (high precision)
    concepts: list[str] = []
    seen: set[str] = set()

    for pat in _DEFINITION_PATTERNS:
        for m in pat.finditer(text):
            term = m.group(1)
            if _is_clean_concept(term) and term not in seen:
                seen.add(term)
                concepts.append(term)

    # Step 2: Extract from heading patterns
    for m in re.finditer(r"#+\s+([一-鿿A-Za-z0-9\s]{2,20})", text):
        heading = m.group(1).strip()
        cjk_parts = re.findall(r"[一-鿿]{2,6}", heading)
        for part in cjk_parts:
            if _is_clean_concept(part) and part not in seen:
                seen.add(part)
                concepts.append(part)

    # Step 3: High-frequency n-grams as supplement
    sentences = re.split(r"[。！？!?；;\n]+", text)
    all_ngrams: list[str] = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 2:
            continue
        cjk_only = re.sub(r"[^一-鿿]", "", sent)
        for n in range(2, min(7, len(cjk_only) + 1)):
            for i in range(len(cjk_only) - n + 1):
                all_ngrams.append(cjk_only[i:i + n])

    counts = Counter(all_ngrams)
    sorted_by_len = sorted(counts.keys(), key=lambda w: (-len(w), -counts[w]))
    for word in sorted_by_len:
        freq = counts[word]
        if freq < 3 or word in CONCEPT_STOPWORDS or not _is_clean_concept(word):
            continue
        if word in seen:
            continue
        is_substring = any(word in s and word != s for s in seen)
        if is_substring:
            continue
        seen.add(word)
        concepts.append(word)

    return concepts[:max_concepts]


def _extract_concepts_by_frequency(text: str, limit: int) -> list[str]:
    """Extract key topics from any content domain using frequency analysis."""
    words = re.findall(r"[一-鿿]{2,6}", text)
    counts = Counter(words)
    candidates = [
        word for word, freq in counts.most_common(limit * 3)
        if word not in CONCEPT_STOPWORDS and freq >= 3 and len(word) >= 2
    ]
    return candidates[:limit]


def detect_domains(article: Article) -> list[str]:
    title_text = article.title
    content_text = body_text(article, limit=5000)
    content_lines = body_lines(article)
    scores: Counter[str] = Counter()
    for domain, keywords in DEFAULT_DOMAINS.items():
        for keyword in keywords:
            if keyword in title_text:
                scores[domain] += 3
            if keyword in content_text:
                scores[domain] += 2
            line_hits = sum(1 for line in content_lines if keyword in line)
            scores[domain] += min(line_hits, 3)
    found = [
        domain
        for domain, score in scores.items()
        if score >= DOMAIN_MIN_SCORE.get(domain, 3)
    ]
    return found or ["待归域"]


def extract_entities(article: Article, limit: int = 8) -> list[str]:
    text = f"{article.title} {body_text(article)}"
    patterns = [
        r"\b(?:Tesla|FSD|NVIDIA|DRIVE Thor|NVLink-C2C|UniAD|VAD|ChatGPT|Transformer|ViT|BEV)\b",
        r"\b[A-Z][A-Za-z0-9\-\+]{1,20}\b",
        r"(?:[A-Z]{2,}[A-Za-z0-9\-\+]{0,20})",
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text))
    normalized: list[str] = []
    for item in found:
        item = item.strip()
        if len(item) < 2:
            continue
        if item.upper() in GENERIC_ENTITY_STOPWORDS:
            normalized.append(item)
            continue
        if item.lower() in {"the", "and", "for", "with"}:
            continue
        if item.startswith("##"):
            continue
        normalized.append(item)
    counts = Counter(normalized)
    ranked = [name for name, _ in counts.most_common(limit * 2)]
    deduped: list[str] = []
    for name in ranked:
        if name.upper() in GENERIC_ENTITY_STOPWORDS and name not in {"FSD"}:
            continue
        if name in ENGLISH_ENTITY_STOPWORDS:
            continue
        if name not in deduped:
            deduped.append(name)
        if len(deduped) >= limit:
            break
    return deduped


def extract_concepts(article: Article, limit: int = 10) -> list[str]:
    text = f"{article.title} {plain_text(article.body)}"
    seed = [
        "电子电气架构", "区域式 EEA", "中央计算", "软件定义汽车",
        "AI 定义汽车", "端到端", "神经网络", "感知", "预测", "规划",
        "控制", "数据飞轮", "BEV", "时序融合", "推理延迟",
        "模型级 OTA", "模块化栈", "可解释性", "可验证性",
    ]
    found = [concept for concept in seed if concept in text]
    if found:
        if len(found) < limit:
            matches = re.findall(r"([一-鿿A-Za-z0-9\-]{2,20}(?:架构|模型|系统|网络|飞轮|延迟|算力|规划|控制|验证|推理))", text)
            for item in matches:
                if item not in found:
                    found.append(item)
                if len(found) >= limit:
                    break
        return found[:limit]
    return _extract_concepts_by_frequency(text, limit)


def concept_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


def entity_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


def domain_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


def comparison_slug(name: str) -> str:
    return sanitize_filename(name, max_length=80)


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


def extract_content_questions(article: Article, limit: int = 5) -> list[str]:
    """Extract high-value questions from article content (heuristic)."""
    text = plain_text(article.body)
    questions: list[str] = []
    seen: set[str] = set()

    concepts = _extract_clean_concepts(text, max_concepts=20)
    if not concepts:
        return questions

    # Pattern 2a: Definition sentences -> "什么是 X？"
    for pat in _DEFINITION_PATTERNS:
        for m in pat.finditer(text):
            topic = m.group(1)
            if topic in concepts and topic not in seen:
                seen.add(topic)
                questions.append(f"什么是{topic}？")
                if len(questions) >= limit:
                    return questions

    # Pattern 2b: "X是什么" / "什么是X"
    for concept in concepts:
        if concept in seen:
            continue
        if f"{concept}是什么" in text or f"什么是{concept}" in text:
            seen.add(concept)
            questions.append(f"什么是{concept}？")
            if len(questions) >= limit:
                return questions

    # Pattern 2c: "X的本质/原理/底层"
    for concept in concepts:
        if concept in seen:
            continue
        if f"{concept}的本质" in text or f"{concept}的原理" in text or f"{concept}的底层" in text:
            seen.add(concept)
            questions.append(f"{concept}的本质/原理是什么？")
            if len(questions) >= limit:
                return questions

    # Pattern 2d: "X和Y的区别"
    for i, c1 in enumerate(concepts):
        for c2 in concepts[i + 1:]:
            pair_key = f"{c1}+{c2}"
            if pair_key in seen:
                continue
            if f"{c1}和{c2}" in text or f"{c2}和{c1}" in text:
                seen.add(pair_key)
                questions.append(f"{c1}和{c2}有什么区别？")
                if len(questions) >= limit:
                    return questions

    # Fallback: "什么是 X？" for remaining concepts
    for concept in concepts:
        if concept in seen:
            continue
        seen.add(concept)
        questions.append(f"什么是{concept}？")
        if len(questions) >= limit:
            break

    return questions


def extract_content_topics(article: Article, limit: int = 5) -> list[str]:
    """Extract key topics from article content."""
    headings = re.findall(r"^#+\s+(.+)$", article.body, re.M)
    topics: list[str] = []
    seen: set[str] = set()
    for h in headings:
        h_clean = re.sub(r"^[#*\s]+", "", h).strip()
        if len(h_clean) >= 2 and h_clean not in seen and h_clean not in CONCEPT_STOPWORDS:
            seen.add(h_clean)
            topics.append(h_clean)
    if len(topics) < limit:
        text = plain_text(article.body)
        words = re.findall(r"[一-鿿]{2,6}", text)
        counts = Counter(w for w in words if w not in CONCEPT_STOPWORDS)
        for word, freq in counts.most_common(limit * 2):
            if word not in seen and freq >= 3:
                seen.add(word)
                topics.append(word)
                if len(topics) >= limit:
                    break
    return topics[:limit]


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
    """Detect whether new content's domains mismatch the existing vault."""
    if article_domains is None:
        article_domains = detect_domains(article)
    vault_domains_map = vault_domain_distribution(vault)
    vault_domain_names = list(vault_domains_map.keys())

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
    if is_mismatch:
        topics = extract_content_topics(article, limit=3)
        if topics:
            suggested_domain = topics[0]
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