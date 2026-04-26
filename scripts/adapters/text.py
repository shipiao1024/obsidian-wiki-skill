from __future__ import annotations

from pathlib import Path

from .types import AdapterResult, make_error_result, build_success_result


def run_plain_text_adapter(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
    options: dict[str, object] | None = None,
) -> AdapterResult:
    del work_dir, options
    text = (input_value or "").strip()
    if not text:
        return make_error_result(
            status="empty_result",
            reason="No text content provided.",
            input_kind="text",
            source_id=source_id,
            adapter_name="direct_ingest",
        )
    title = text.splitlines()[0].strip()[:80] or "Pasted Text"
    return build_success_result(
        input_kind="text",
        source_id=source_id,
        adapter_name="direct_ingest",
        title=title,
        source_kind="plain_text",
        markdown_body=text,
        plain_text_body=text,
    )
