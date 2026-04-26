from __future__ import annotations

import re
import shlex


def normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_plain_text(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def html_to_markdown_fallback(html: str) -> str:
    return normalize_whitespace(html_to_plain_text(html))


def normalized_text_length(value: str) -> int:
    text = normalize_whitespace(value)
    text = re.sub(r"[#>*`_\-\[\]\(\)!]", " ", text)
    text = re.sub(r"\s+", "", text)
    return len(text)


def looks_placeholder_title(title: str) -> bool:
    normalized = title.strip().lower()
    return normalized in {"", "untitled", "video", "---"}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, text[match.end() :]


def parse_configured_command(value: str) -> list[str]:
    return shlex.split(value, posix=False)
