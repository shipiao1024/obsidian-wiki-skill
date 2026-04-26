from __future__ import annotations

from pathlib import Path

from source_registry import get_source_config

from .types import (
    AdapterStatus,
    QualityLevel,
    InputKind,
    MediaType,
    AssetItem,
    NormalizedMetadata,
    AdapterResult,
    make_error_result,
    build_success_result,
)
from .utils import (
    normalize_whitespace,
    html_to_plain_text,
    html_to_markdown_fallback,
    normalized_text_length,
    looks_placeholder_title,
    parse_frontmatter,
    parse_configured_command,
)
from .quality import assess_web_quality, assess_video_quality, assess_pdf_quality
from .text import run_plain_text_adapter
from .local import (
    extract_pdf_text,
    run_markdown_file_adapter,
    run_text_file_adapter,
    run_html_file_adapter,
    run_pdf_file_adapter,
    run_local_file_adapter,
)
from .wechat import run_wechat_adapter
from .web import (
    resolve_web_adapter_command,
    classify_web_adapter_failure,
    run_web_adapter,
)
from .video import (
    resolve_video_adapter_command,
    resolve_video_cookie_args,
    resolve_video_cookie_arg_variants,
    default_video_cookie_file,
    default_video_cookie_files,
    is_browser_cookie_copy_error,
    normalize_video_fetch_url,
    classify_video_adapter_failure,
    should_fallback_to_douyin_browser_capture,
    subtitle_to_text,
    danmaku_xml_to_text,
    transcribe_audio_with_asr,
    node_command,
    run_douyin_browser_capture,
    build_douyin_browser_capture_result,
    download_audio_for_asr,
    load_video_metadata,
    extract_embedded_subtitle_text,
    run_video_adapter,
)
from .collection import (
    normalize_collection_entry_url,
    classify_video_collection_failure,
    expand_video_collection_urls,
)


def run_adapter_for_source(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
    options: dict[str, object] | None = None,
    tool_dir: Path | None = None,
    deps_dir: Path | None = None,
) -> AdapterResult:
    config = get_source_config(source_id)
    if not config:
        return make_error_result(
            status="invalid_input",
            reason=f"Unknown source_id: {source_id}",
            input_kind="text",
            source_id=source_id,
            adapter_name="dispatcher",
        )
    kind = config.get("kind")
    if source_id == "plain_text" or kind == "text":
        return run_plain_text_adapter(
            source_id=source_id,
            input_value=input_value,
            work_dir=work_dir,
            options=options,
        )
    if source_id == "wechat_url":
        return run_wechat_adapter(
            source_id=source_id,
            input_value=input_value,
            work_dir=work_dir,
            tool_dir=tool_dir,
            deps_dir=deps_dir,
            options=options,
        )
    if source_id == "web_url":
        return run_web_adapter(
            source_id=source_id,
            input_value=input_value,
            work_dir=work_dir,
            options=options,
        )
    if source_id in {"video_url_youtube", "video_url_bilibili", "video_url_douyin"}:
        return run_video_adapter(
            source_id=source_id,
            input_value=input_value,
            work_dir=work_dir,
            options=options,
        )
    if kind == "file":
        return run_local_file_adapter(
            source_id=source_id,
            input_value=input_value,
            work_dir=work_dir,
            options=options,
        )
    return make_error_result(
        status="unsupported",
        reason=f"Adapter for source_id '{source_id}' is not implemented yet.",
        input_kind="url" if kind == "url" else "text",
        source_id=source_id,
        adapter_name="dispatcher",
    )
