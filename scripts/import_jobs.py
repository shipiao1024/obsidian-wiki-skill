from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)
SECTION_PATTERN = re.compile(r"##\s+(.+?)\s*\n(.*?)(?=\n##\s+|\Z)", re.S)
COMPLETED_ITEM_PATTERN = re.compile(r"-\s+`([^`]+)`\s+\|\s+\[\[sources/([^\]]+)\]\]")


def sanitize_job_slug(source_kind: str, source_url: str) -> str:
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:10]
    prefix = re.sub(r"[^a-z0-9]+", "-", source_kind.lower()).strip("-") or "import-job"
    return f"{prefix}-{digest}"


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
    lines = ["---"]
    for key, value in meta.items():
        lines.append(f'{key}: "{value}"')
    lines.extend(["---", ""])
    return "\n".join(lines)


def section_body(body: str, heading: str) -> str:
    for match in SECTION_PATTERN.finditer(body):
        if match.group(1).strip() == heading:
            return match.group(2).strip()
    return ""


def load_import_job(path: Path) -> dict[str, object]:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    return {
        "path": path,
        "meta": meta,
        "body": body,
    }


def write_import_job(path: Path, meta: dict[str, str], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_frontmatter(meta) + body.strip() + "\n", encoding="utf-8")


def ensure_import_job(vault: Path, source_kind: str, source_url: str, max_items_per_run: int = 20) -> Path:
    jobs_dir = vault / "wiki" / "import-jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    path = jobs_dir / f"{sanitize_job_slug(source_kind, source_url)}.md"
    if path.exists():
        return path

    meta = {
        "title": f"{source_kind} import job",
        "type": "import-job",
        "source_kind": source_kind,
        "source_url": source_url,
        "status": "active",
        "max_items_per_run": str(max_items_per_run),
        "discovered_count": "0",
        "completed_count": "0",
        "remaining_count": "0",
        "last_run_at": "",
        "last_failure_reason": "",
        "cooldown_until": "",
        "graph_role": "working",
        "graph_include": "false",
        "lifecycle": "working",
    }
    body = "\n".join(
        [
            "# Import Job",
            "",
            "## 已完成视频",
            "",
            "- （空）",
            "",
            "## 待处理视频",
            "",
            "- （空）",
            "",
            "## 最近一次结果",
            "",
            "- 尚未运行。",
            "",
            "## 最近失败",
            "",
            "- 无",
        ]
    )
    write_import_job(path, meta, body)
    return path


def completed_video_ids(job: dict[str, object]) -> set[str]:
    return {item["video_id"] for item in completed_video_items(job)}


def completed_video_items(job: dict[str, object]) -> list[dict[str, str]]:
    body = str(job.get("body", ""))
    completed = section_body(body, "已完成视频")
    items: list[dict[str, str]] = []
    for line in completed.splitlines():
        match = COMPLETED_ITEM_PATTERN.match(line.strip())
        if not match:
            continue
        items.append(
            {
                "video_id": match.group(1),
                "source_slug": match.group(2),
            }
        )
    return items


def update_import_job(
    *,
    path: Path,
    source_kind: str,
    source_url: str,
    discovered_items: list[dict[str, str]],
    completed_items: list[dict[str, str]],
    remaining_items: list[dict[str, str]],
    status: str,
    processed_count: int,
    skipped_count: int,
    failed_count: int,
    last_failure_reason: str = "",
    cooldown_until: str = "",
) -> None:
    current = load_import_job(path) if path.exists() else {"meta": {}}
    previous_meta = current.get("meta", {})
    max_items_per_run = str(previous_meta.get("max_items_per_run", "20"))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    meta = {
        "title": f"{source_kind} import job",
        "type": "import-job",
        "source_kind": source_kind,
        "source_url": source_url,
        "status": status,
        "max_items_per_run": max_items_per_run,
        "discovered_count": str(len(discovered_items)),
        "completed_count": str(len(completed_items)),
        "remaining_count": str(len(remaining_items)),
        "last_run_at": timestamp,
        "last_failure_reason": last_failure_reason,
        "cooldown_until": cooldown_until,
        "graph_role": "working",
        "graph_include": "false",
        "lifecycle": "working",
    }

    completed_lines = [
        f"- `{item['video_id']}` | [[sources/{item['source_slug']}]]"
        for item in completed_items
        if item.get("video_id") and item.get("source_slug")
    ]
    if not completed_lines:
        completed_lines = ["- （空）"]

    remaining_lines = [
        f"- `{item['video_id']}` | {item['video_url']}"
        for item in remaining_items
        if item.get("video_id") and item.get("video_url")
    ]
    if not remaining_lines:
        remaining_lines = ["- （空）"]

    failure_lines = [f"- {last_failure_reason}"] if last_failure_reason else ["- 无"]

    body = "\n".join(
        [
            "# Import Job",
            "",
            "## 已完成视频",
            "",
            *completed_lines,
            "",
            "## 待处理视频",
            "",
            *remaining_lines,
            "",
            "## 最近一次结果",
            "",
            f"- {timestamp} | processed={processed_count} | skipped={skipped_count} | failed={failed_count}",
            "",
            "## 最近失败",
            "",
            *failure_lines,
        ]
    )
    write_import_job(path, meta, body)
