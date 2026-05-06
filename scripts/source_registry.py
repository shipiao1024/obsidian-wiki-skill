from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs


_DOUYIN_HOST_RE = re.compile(r"^(?:www\.)?douyin\.com$", re.IGNORECASE)


def pre_normalize_url(url: str) -> str:
    """Rewrite ambiguous Douyin URLs to canonical video URLs before source matching.

    Douyin SPA URLs can carry ``modal_id`` or ``vid`` query parameters that
    point to a specific video, but the URL path may still look like a user
    page, search page, or collection page.  Without normalization the path-based
    source_id wins (priority 95/96), the video-specific parameter is lost, and
    the pipeline tries to ingest the entire user page instead of the intended
    single video.

    Rules (applied in order):
    1. If ``modal_id`` is present → ``https://www.douyin.com/video/{modal_id}``
       (modal_id always wins over vid, because it represents the currently
       active video overlay in the SPA).
    2. If ``vid`` is present (no modal_id) on a non-/video/ Douyin URL
       → ``https://www.douyin.com/video/{vid}``.
    3. Otherwise → return url unchanged.
    """
    parsed = urlparse(url)
    if not _DOUYIN_HOST_RE.match(parsed.hostname or ""):
        return url

    qs = parse_qs(parsed.query)

    modal_id = (qs.get("modal_id") or [""])[0].strip()
    if modal_id.isdigit():
        return f"https://www.douyin.com/video/{modal_id}"

    vid = (qs.get("vid") or [""])[0].strip()
    if vid.isdigit() and not parsed.path.startswith("/video/"):
        return f"https://www.douyin.com/video/{vid}"

    return url


SOURCE_REGISTRY: dict[str, dict[str, object]] = {
    "wechat_url": {
        "label": "微信公众号文章",
        "kind": "url",
        "subtype": "wechat",
        "priority": 100,
        "match": {"url_patterns": [r"^https://mp\.weixin\.qq\.com/s"]},
        "adapter": {"name": "wechat-article-to-markdown", "mode": "fetch_to_markdown"},
    },
    "web_url": {
        "label": "通用网页",
        "kind": "url",
        "subtype": "web",
        "priority": 10,
        "match": {"url_patterns": [r"^https?://"]},
        "adapter": {"name": "baoyu-url-to-markdown", "mode": "fetch_to_markdown"},
    },
    "video_url_youtube": {
        "label": "YouTube 视频",
        "kind": "url",
        "subtype": "youtube",
        "priority": 90,
        "match": {
            "url_patterns": [
                r"^https?://(www\.)?youtube\.com/watch",
                r"^https?://youtu\.be/",
            ]
        },
        "adapter": {"name": "yt-dlp", "mode": "subtitle_or_audio"},
    },
    "video_playlist_youtube": {
        "label": "YouTube 播放列表",
        "kind": "url",
        "subtype": "youtube_playlist",
        "priority": 95,
        "match": {
            "url_patterns": [
                r"^https?://(www\.)?youtube\.com/playlist\?list=",
                r"^https?://(www\.)?youtube\.com/@[^/]+/videos/?(?:\?.*)?$",
                r"^https?://(www\.)?youtube\.com/channel/[^/]+/videos/?(?:\?.*)?$",
                r"^https?://(www\.)?youtube\.com/c/[^/]+/videos/?(?:\?.*)?$",
            ]
        },
        "adapter": {"name": "yt-dlp", "mode": "playlist_expand"},
    },
    "video_url_bilibili": {
        "label": "Bilibili 视频",
        "kind": "url",
        "subtype": "bilibili",
        "priority": 90,
        "match": {
            "url_patterns": [
                r"^https?://(www\.)?bilibili\.com/video/",
                r"^https?://b23\.tv/",
            ]
        },
        "adapter": {"name": "yt-dlp", "mode": "subtitle_or_audio"},
    },
    "video_playlist_bilibili": {
        "label": "Bilibili 合集/系列",
        "kind": "url",
        "subtype": "bilibili_playlist",
        "priority": 95,
        "match": {
            "url_patterns": [
                r"^https?://space\.bilibili\.com/\d+/channel/(?:collectiondetail|seriesdetail)\?sid=",
                r"^https?://(www\.)?bilibili\.com/list/",
            ]
        },
        "adapter": {"name": "yt-dlp", "mode": "playlist_expand"},
    },
    "video_collection_douyin": {
        "label": "抖音合集",
        "kind": "url",
        "subtype": "douyin_collection",
        "priority": 96,
        "match": {
            "url_patterns": [
                r"^https?://(www\.)?douyin\.com/collection/",
            ]
        },
        "adapter": {"name": "yt-dlp", "mode": "playlist_expand"},
    },
    "video_url_douyin": {
        "label": "抖音视频",
        "kind": "url",
        "subtype": "douyin",
        "priority": 90,
        "match": {
            "url_patterns": [
                r"^https?://(www\.)?douyin\.com/video/",
                r"^https?://(www\.)?douyin\.com/.*[?&]modal_id=\d+",
                r"^https?://v\.douyin\.com/",
            ]
        },
        "adapter": {"name": "yt-dlp", "mode": "subtitle_or_audio"},
    },
    "video_playlist_douyin": {
        "label": "抖音用户主页",
        "kind": "url",
        "subtype": "douyin_playlist",
        "priority": 95,
        "match": {
            "url_patterns": [
                r"^https?://(www\.)?douyin\.com/user/",
            ]
        },
        "adapter": {"name": "yt-dlp", "mode": "playlist_expand"},
    },
    "local_file_md": {
        "label": "本地 Markdown",
        "kind": "file",
        "subtype": "markdown",
        "priority": 100,
        "match": {"extensions": [".md", ".markdown"]},
        "adapter": {"name": "direct_read", "mode": "local_text"},
    },
    "local_file_text": {
        "label": "本地文本",
        "kind": "file",
        "subtype": "text",
        "priority": 100,
        "match": {"extensions": [".txt"]},
        "adapter": {"name": "direct_read", "mode": "local_text"},
    },
    "local_file_html": {
        "label": "本地 HTML",
        "kind": "file",
        "subtype": "html",
        "priority": 100,
        "match": {"extensions": [".html", ".htm"]},
        "adapter": {"name": "html_to_markdown", "mode": "local_html"},
    },
    "local_file_pdf": {
        "label": "本地 PDF",
        "kind": "file",
        "subtype": "pdf",
        "priority": 100,
        "match": {"extensions": [".pdf"]},
        "adapter": {"name": "pdf_text_extract", "mode": "local_pdf"},
    },
    "local_file_docx": {
        "label": "本地 DOCX",
        "kind": "file",
        "subtype": "docx",
        "priority": 100,
        "match": {"extensions": [".docx"]},
        "adapter": {"name": "markitdown_convert", "mode": "local_docx"},
    },
    "local_file_pptx": {
        "label": "本地 PPTX",
        "kind": "file",
        "subtype": "pptx",
        "priority": 100,
        "match": {"extensions": [".pptx"]},
        "adapter": {"name": "markitdown_convert", "mode": "local_pptx"},
    },
    "local_file_xlsx": {
        "label": "本地 XLSX",
        "kind": "file",
        "subtype": "xlsx",
        "priority": 100,
        "match": {"extensions": [".xlsx", ".xls"]},
        "adapter": {"name": "xlsx_to_markdown", "mode": "local_xlsx"},
    },
    "local_file_epub": {
        "label": "本地 EPUB",
        "kind": "file",
        "subtype": "epub",
        "priority": 100,
        "match": {"extensions": [".epub"]},
        "adapter": {"name": "epub_to_markdown", "mode": "local_epub"},
    },
    "plain_text": {
        "label": "纯文本粘贴",
        "kind": "text",
        "subtype": "plain_text",
        "priority": 100,
        "match": {"input_mode": "direct_text"},
        "adapter": {"name": "direct_ingest", "mode": "plain_text"},
    },
}


def match_source_from_url(url: str) -> str | None:
    matches: list[tuple[int, str]] = []
    for source_id, config in SOURCE_REGISTRY.items():
        patterns = config.get("match", {}).get("url_patterns", [])
        if not isinstance(patterns, list):
            continue
        for pattern in patterns:
            if isinstance(pattern, str) and re.search(pattern, url):
                matches.append((int(config.get("priority", 0)), source_id))
                break
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


def match_source_from_file(path: Path) -> str | None:
    ext = path.suffix.lower()
    matches: list[tuple[int, str]] = []
    for source_id, config in SOURCE_REGISTRY.items():
        extensions = config.get("match", {}).get("extensions", [])
        if isinstance(extensions, list) and ext in extensions:
            matches.append((int(config.get("priority", 0)), source_id))
    if not matches:
        return None
    matches.sort(reverse=True)
    return matches[0][1]


def get_source_config(source_id: str) -> dict[str, object] | None:
    value = SOURCE_REGISTRY.get(source_id)
    return value if isinstance(value, dict) else None
