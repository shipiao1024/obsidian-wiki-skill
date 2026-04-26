"""Text processing utilities for the obsidian-wiki pipeline."""

from __future__ import annotations

import re

from .types import Article, DOMAIN_EXCLUDE_LINES

INVALID_CHARS = re.compile(r'[\\/:*?"<>|\r\n]+')
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
CODE_BLOCK = re.compile(r"```.*?```", re.S)
HEADING = re.compile(r"^\s*#+\s*", re.M)


def sanitize_filename(name: str, max_length: int = 96) -> str:
    name = INVALID_CHARS.sub("_", name.strip())
    name = re.sub(r"_+", "_", name).strip("_")
    return (name[:max_length].rstrip("_. ") or "untitled")


def slugify_article(date_str: str, title: str) -> str:
    day = ""
    if date_str:
        match = re.match(r"(\d{4}-\d{2}-\d{2})", date_str)
        if match:
            day = match.group(1)
    stem = sanitize_filename(title)
    return f"{day}--{stem}" if day else stem


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
    text = IMAGE.sub("", text)
    text = LINK.sub(r"\1", text)
    text = HEADING.sub("", text)
    text = re.sub(r"[>*_`~\-\|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", text)
    return [p.strip() for p in parts if len(p.strip()) >= 14]


def normalize_sentence(sentence: str, title: str) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    sentence = sentence.replace(title, "").strip(" ：:,-")
    sentence = re.sub(r"^副标题[：:]\s*", "", sentence)
    sentence = re.sub(r"^系列导读[：:]\s*", "", sentence)
    sentence = re.sub(r"^开场[：:]\s*", "", sentence)
    sentence = re.sub(r"^\W+", "", sentence)
    return sentence.strip()


def top_lines(article: Article, limit: int = 6) -> list[str]:
    text = plain_text(article.body)
    lines = [normalize_sentence(item, article.title) for item in split_sentences(text)]
    filtered: list[str] = []
    skip_patterns = ("上一篇", "系列导读", "副标题", "本文是", "开场")
    for line in lines:
        if len(line) < 16:
            continue
        if any(pattern in line for pattern in skip_patterns):
            continue
        filtered.append(line)
    lines = filtered or lines
    return lines[:limit] or [text[:320]]


def brief_lead(article: Article, bullets: list[str]) -> str:
    if not bullets:
        return "这是一篇待人工补充的一句话结论。"
    if len(bullets) >= 2:
        return f"{bullets[0]} {bullets[1]}"
    return bullets[0]


def section_excerpt(body: str, heading: str) -> str:
    pattern = re.compile(
        rf"##\s+{re.escape(heading)}\s*\n(.*?)(?:\n##\s+|\Z)",
        re.S,
    )
    match = pattern.search(body)
    if not match:
        return ""
    text = plain_text(match.group(1))
    return text[:240].strip()


def filename_stem(path) -> str:
    return path.stem


def body_text(article: Article, limit: int | None = None) -> str:
    text = plain_text(article.body)
    if limit is not None:
        return text[:limit]
    return text


def body_lines(article: Article) -> list[str]:
    lines: list[str] = []
    for raw_line in article.body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("!"):
            continue
        text = plain_text(line)
        if not text:
            continue
        if any(marker in text for marker in DOMAIN_EXCLUDE_LINES):
            continue
        lines.append(text)
    return lines