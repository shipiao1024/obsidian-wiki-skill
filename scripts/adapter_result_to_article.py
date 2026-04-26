from __future__ import annotations

import shutil
from pathlib import Path

from source_adapters import AdapterResult
from wiki_ingest_wechat import Article


def safe_filename(name: str) -> str:
    invalid = '\\/:*?"<>|\r\n'
    result = "".join("_" if ch in invalid else ch for ch in name.strip())
    return result.strip(" .") or "untitled"


def build_adapter_frontmatter(result: AdapterResult) -> str:
    metadata = result.get("metadata", {})
    title = str(metadata.get("title", "Untitled")).strip() or "Untitled"
    author = str(metadata.get("author", "")).strip()
    date = str(metadata.get("date", "")).strip()
    source_url = str(metadata.get("source_url", "")).strip()
    source_id = str(metadata.get("source_id", result.get("source_id", ""))).strip()
    source_kind = str(metadata.get("source_kind", "")).strip()

    lines = ["---", f'title: "{title}"']
    if author:
        lines.append(f'author: "{author}"')
    if date:
        lines.append(f'date: "{date}"')
    if source_url:
        lines.append(f'source: "{source_url}"')
    if source_id:
        lines.append(f'source_id: "{source_id}"')
    if source_kind:
        lines.append(f'source_kind: "{source_kind}"')
    lines.extend(["---", ""])
    return "\n".join(lines)


def rewrite_markdown_asset_links(markdown_body: str, assets_map: dict[str, str]) -> str:
    updated = markdown_body
    for original, rewritten in assets_map.items():
        updated = updated.replace(original, rewritten)
    return updated


def stage_assets_for_article(*, assets: list[dict[str, object]], article_dir: Path) -> dict[str, str]:
    images_dir = article_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rewritten_map: dict[str, str] = {}
    used_names: set[str] = set()

    for item in assets:
        local_path = str(item.get("local_path", "")).strip()
        media_type = str(item.get("media_type", "")).strip()
        if not local_path:
            continue
        src = Path(local_path)
        if not src.exists() or not src.is_file():
            continue
        if media_type != "image":
            continue

        base_name = safe_filename(src.name)
        candidate = base_name
        stem = Path(base_name).stem
        suffix = Path(base_name).suffix
        index = 1
        while candidate in used_names:
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        used_names.add(candidate)

        dst = images_dir / candidate
        shutil.copy2(src, dst)
        rewritten_map[local_path] = f"images/{candidate}"
    return rewritten_map


def stage_supporting_assets_for_article(
    *, assets: list[dict[str, object]], article_dir: Path
) -> dict[str, str]:
    attachments_dir = article_dir / "attachments"
    attachments_dir.mkdir(parents=True, exist_ok=True)
    supporting_map: dict[str, str] = {}
    used_names: set[str] = set()

    for item in assets:
        local_path = str(item.get("local_path", "")).strip()
        media_type = str(item.get("media_type", "")).strip()
        if not local_path or media_type == "image":
            continue
        src = Path(local_path)
        if not src.exists() or not src.is_file():
            continue

        base_name = safe_filename(src.name)
        candidate = base_name
        stem = Path(base_name).stem
        suffix = Path(base_name).suffix
        index = 1
        while candidate in used_names:
            candidate = f"{stem}-{index}{suffix}"
            index += 1
        used_names.add(candidate)

        dst = attachments_dir / candidate
        shutil.copy2(src, dst)
        if media_type not in supporting_map:
            supporting_map[media_type] = candidate
    return supporting_map


def transcript_fields_from_result(result: AdapterResult, rewritten_body: str) -> dict[str, str]:
    metadata = result.get("metadata", {})
    source_kind = str(metadata.get("source_kind", "")).strip()
    if source_kind not in {"youtube", "bilibili", "douyin"}:
        return {}

    extra = result.get("extra", {})
    subtitle_source = str(extra.get("subtitle_source", "")).strip()
    stage = ""
    source = ""
    confidence = ""
    if subtitle_source == "platform":
        stage = "subtitle"
        source = "platform_subtitle"
        confidence = "high"
    elif subtitle_source == "embedded-metadata":
        stage = "subtitle"
        source = "embedded_subtitle"
        confidence = "medium"
    elif subtitle_source == "asr":
        stage = "asr"
        source = "asr"
        confidence = str(extra.get("confidence_hint", "")).strip() or "low"

    if not stage:
        return {}

    language = (
        str(extra.get("subtitle_language", "")).strip()
        or str(metadata.get("language", "")).strip()
    )
    return {
        "transcript_stage": stage,
        "transcript_source": source,
        "transcript_language": language,
        "transcript_confidence_hint": confidence,
        "transcript_body": rewritten_body.strip(),
    }


def adapter_result_to_article(*, result: AdapterResult, staging_root: Path) -> Article:
    if result.get("status") != "ok":
        raise ValueError(
            f"Adapter result is not usable: {result.get('status')} - {result.get('reason', '')}"
        )

    metadata = result.get("metadata", {})
    title = str(metadata.get("title", "Untitled")).strip() or "Untitled"
    author = str(metadata.get("author", "")).strip()
    date = str(metadata.get("date", "")).strip()
    source_url = str(metadata.get("source_url", "")).strip()

    markdown_body = str(result.get("markdown_body", "")).strip()
    plain_text_body = str(result.get("plain_text_body", "")).strip()
    body = markdown_body or plain_text_body
    if not body:
        raise ValueError("Adapter result has no markdown_body or plain_text_body.")

    article_dir = staging_root / safe_filename(title)
    article_dir.mkdir(parents=True, exist_ok=True)

    assets = result.get("assets", [])
    assets_map = stage_assets_for_article(
        assets=assets if isinstance(assets, list) else [],
        article_dir=article_dir,
    )
    supporting_assets = stage_supporting_assets_for_article(
        assets=assets if isinstance(assets, list) else [],
        article_dir=article_dir,
    )

    rewritten_body = rewrite_markdown_asset_links(body, assets_map)
    frontmatter = build_adapter_frontmatter(result)
    md_path = article_dir / f"{safe_filename(title)}.md"
    md_path.write_text(frontmatter + rewritten_body.strip() + "\n", encoding="utf-8")
    transcript_fields = transcript_fields_from_result(result, rewritten_body)

    return Article(
        title=title,
        author=author,
        date=date,
        source=source_url,
        body=rewritten_body.strip(),
        src_dir=article_dir,
        md_path=md_path,
        quality=str(result.get("quality", "")).strip(),
        transcript_stage=transcript_fields.get("transcript_stage", ""),
        transcript_source=transcript_fields.get("transcript_source", ""),
        transcript_language=transcript_fields.get("transcript_language", ""),
        transcript_confidence_hint=transcript_fields.get("transcript_confidence_hint", ""),
        transcript_body=transcript_fields.get("transcript_body", ""),
        transcript_subtitle_asset=supporting_assets.get("subtitle", ""),
        transcript_audio_asset=supporting_assets.get("audio", ""),
    )
