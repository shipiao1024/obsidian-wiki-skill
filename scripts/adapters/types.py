from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


AdapterStatus = Literal[
    "ok",
    "not_configured",
    "dependency_missing",
    "browser_not_ready",
    "platform_blocked",
    "network_failed",
    "runtime_failed",
    "unsupported",
    "empty_result",
    "invalid_input",
]
QualityLevel = Literal["low", "acceptable", "high"]
InputKind = Literal["url", "file", "text"]
MediaType = Literal["image", "audio", "video", "html_snapshot", "subtitle", "other"]


class AssetItem(TypedDict):
    source_url: NotRequired[str]
    local_path: str
    media_type: MediaType


class NormalizedMetadata(TypedDict):
    title: str
    author: NotRequired[str]
    date: NotRequired[str]
    source_url: NotRequired[str]
    source_id: str
    source_kind: str
    language: NotRequired[str]


class AdapterResult(TypedDict):
    status: AdapterStatus
    reason: str
    input_kind: InputKind
    source_id: str
    adapter_name: str
    quality: NotRequired[QualityLevel]
    metadata: NotRequired[NormalizedMetadata]
    markdown_body: NotRequired[str]
    plain_text_body: NotRequired[str]
    assets: list[AssetItem]
    extra: dict[str, object]


def make_error_result(
    *,
    status: AdapterStatus,
    reason: str,
    input_kind: InputKind,
    source_id: str,
    adapter_name: str,
) -> AdapterResult:
    return {
        "status": status,
        "reason": reason,
        "input_kind": input_kind,
        "source_id": source_id,
        "adapter_name": adapter_name,
        "assets": [],
        "extra": {},
    }


def build_success_result(
    *,
    input_kind: InputKind,
    source_id: str,
    adapter_name: str,
    title: str,
    source_kind: str,
    markdown_body: str,
    plain_text_body: str,
    source_url: str | None = None,
    author: str | None = None,
    date: str | None = None,
    language: str | None = None,
    quality: QualityLevel | None = None,
    assets: list[AssetItem] | None = None,
    extra: dict[str, object] | None = None,
) -> AdapterResult:
    from .utils import normalize_whitespace

    metadata: NormalizedMetadata = {
        "title": title.strip() or "Untitled",
        "source_id": source_id,
        "source_kind": source_kind,
    }
    if source_url:
        metadata["source_url"] = source_url
    if author:
        metadata["author"] = author
    if date:
        metadata["date"] = date
    if language:
        metadata["language"] = language

    result: AdapterResult = {
        "status": "ok",
        "reason": "",
        "input_kind": input_kind,
        "source_id": source_id,
        "adapter_name": adapter_name,
        "metadata": metadata,
        "markdown_body": normalize_whitespace(markdown_body),
        "plain_text_body": normalize_whitespace(plain_text_body),
        "assets": assets or [],
        "extra": extra or {},
    }
    if quality is not None:
        result["quality"] = quality
    return result
