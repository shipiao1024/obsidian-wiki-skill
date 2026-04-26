from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .types import AdapterStatus, AdapterResult, make_error_result
from .video import (
    resolve_video_adapter_command,
    resolve_video_cookie_args,
    classify_video_adapter_failure,
)


def normalize_collection_entry_url(source_id: str, entry: dict[str, object]) -> str | None:
    webpage_url = entry.get("webpage_url")
    if isinstance(webpage_url, str) and webpage_url.strip():
        return webpage_url.strip()

    url = entry.get("url")
    if isinstance(url, str) and url.strip():
        value = url.strip()
        if value.startswith("http://") or value.startswith("https://"):
            return value
        if source_id == "video_playlist_youtube":
            return f"https://www.youtube.com/watch?v={value}"
        if source_id == "video_playlist_bilibili" and value.startswith("BV"):
            return f"https://www.bilibili.com/video/{value}"
        if source_id == "video_playlist_douyin":
            return f"https://www.douyin.com/video/{value}"
        if source_id == "video_collection_douyin":
            return f"https://www.douyin.com/video/{value}"
        return value

    item_id = entry.get("id")
    if isinstance(item_id, str) and item_id.strip():
        value = item_id.strip()
        if source_id == "video_playlist_youtube":
            return f"https://www.youtube.com/watch?v={value}"
        if source_id == "video_playlist_bilibili" and value.startswith("BV"):
            return f"https://www.bilibili.com/video/{value}"
        if source_id == "video_playlist_douyin":
            return f"https://www.douyin.com/video/{value}"
        if source_id == "video_collection_douyin":
            return f"https://www.douyin.com/video/{value}"
    return None


def classify_video_collection_failure(exc: subprocess.CalledProcessError) -> tuple[AdapterStatus, str]:
    parts = [
        str(getattr(exc, "stdout", "") or ""),
        str(getattr(exc, "stderr", "") or ""),
        str(exc),
    ]
    message = " ".join(part for part in parts if part).strip()
    lowered = message.lower()

    if "winerror 10013" in lowered or "failed to establish a new connection" in lowered:
        return "network_failed", f"Video collection expansion hit a network/socket error: {message}"
    if "http error 412" in lowered or "precondition failed" in lowered:
        return "platform_blocked", f"Video collection expansion was blocked by the platform (likely needs cookies.txt): {message}"
    if "sign in" in lowered or "login" in lowered or "cookie" in lowered:
        return "platform_blocked", f"Video collection expansion likely requires cookies.txt: {message}"
    return "runtime_failed", f"Video collection expansion failed: {message or exc}"


def expand_video_collection_urls(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
) -> list[str]:
    base_cmd = resolve_video_adapter_command()
    if not base_cmd:
        raise RuntimeError(
            "Video adapter is not configured or not on PATH. Set WECHAT_WIKI_VIDEO_ADAPTER_BIN or install yt-dlp."
        )
    work_dir.mkdir(parents=True, exist_ok=True)
    base_args = ["--flat-playlist", "--dump-single-json", input_value]
    cookie_args = resolve_video_cookie_args()
    cmd = [*base_cmd, *cookie_args, *base_args]

    try:
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Video adapter executable not found: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        _, reason = classify_video_collection_failure(exc)
        raise RuntimeError(reason) from exc

    payload = json.loads(completed.stdout or "{}")
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = normalize_collection_entry_url(source_id, entry)
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls