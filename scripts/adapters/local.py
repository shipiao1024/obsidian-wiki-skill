from __future__ import annotations

from pathlib import Path

from .types import AdapterResult, make_error_result, build_success_result, AssetItem
from .utils import html_to_markdown_fallback, html_to_plain_text
from .quality import assess_pdf_quality


def extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("PDF extractor dependency missing: pypdf") from exc

    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks).strip()


def run_markdown_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return make_error_result(
            status="runtime_failed",
            reason="Markdown file is not valid UTF-8.",
            input_kind="file",
            source_id=source_id,
            adapter_name="direct_read",
        )
    if not text.strip():
        return make_error_result(
            status="empty_result",
            reason="Markdown file is empty.",
            input_kind="file",
            source_id=source_id,
            adapter_name="direct_read",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="direct_read",
        title=path.stem,
        source_kind="markdown",
        markdown_body=text,
        plain_text_body=text,
        extra={"file_path": str(path)},
    )


def run_text_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return make_error_result(
            status="runtime_failed",
            reason="Text file is not valid UTF-8.",
            input_kind="file",
            source_id=source_id,
            adapter_name="direct_read",
        )
    if not text.strip():
        return make_error_result(
            status="empty_result",
            reason="Text file is empty.",
            input_kind="file",
            source_id=source_id,
            adapter_name="direct_read",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="direct_read",
        title=path.stem,
        source_kind="text",
        markdown_body=text,
        plain_text_body=text,
        extra={"file_path": str(path)},
    )


def run_html_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    try:
        html = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return make_error_result(
            status="runtime_failed",
            reason="HTML file is not valid UTF-8.",
            input_kind="file",
            source_id=source_id,
            adapter_name="html_to_markdown",
        )
    if not html.strip():
        return make_error_result(
            status="empty_result",
            reason="HTML file is empty.",
            input_kind="file",
            source_id=source_id,
            adapter_name="html_to_markdown",
        )
    markdown_body = html_to_markdown_fallback(html)
    plain_text_body = html_to_plain_text(html)
    if not plain_text_body:
        return make_error_result(
            status="empty_result",
            reason="HTML file produced no readable text.",
            input_kind="file",
            source_id=source_id,
            adapter_name="html_to_markdown",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="html_to_markdown",
        title=path.stem,
        source_kind="html",
        markdown_body=markdown_body,
        plain_text_body=plain_text_body,
        extra={"file_path": str(path)},
    )


def run_pdf_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    try:
        text = extract_pdf_text(path)
    except RuntimeError as exc:
        return make_error_result(
            status="dependency_missing",
            reason=str(exc),
            input_kind="file",
            source_id=source_id,
            adapter_name="pdf_text_extract",
        )
    except Exception as exc:
        return make_error_result(
            status="runtime_failed",
            reason=f"PDF extraction failed: {exc}",
            input_kind="file",
            source_id=source_id,
            adapter_name="pdf_text_extract",
        )
    if not text.strip():
        return make_error_result(
            status="unsupported",
            reason="PDF contains no extractable text. Scanned/OCR PDFs are not supported yet.",
            input_kind="file",
            source_id=source_id,
            adapter_name="pdf_text_extract",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="pdf_text_extract",
        title=path.stem,
        source_kind="pdf",
        markdown_body=text,
        plain_text_body=text,
        quality=assess_pdf_quality(title=path.stem, plain_text_body=text),
        extra={"file_path": str(path)},
    )


def run_local_file_adapter(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
    options: dict[str, object] | None = None,
) -> AdapterResult:
    del work_dir, options
    path = Path(input_value).expanduser().resolve()
    if not path.exists():
        return make_error_result(
            status="invalid_input",
            reason=f"File not found: {path}",
            input_kind="file",
            source_id=source_id,
            adapter_name="local_file_dispatch",
        )
    if not path.is_file():
        return make_error_result(
            status="invalid_input",
            reason=f"Not a file: {path}",
            input_kind="file",
            source_id=source_id,
            adapter_name="local_file_dispatch",
        )
    ext = path.suffix.lower()
    if ext in {".md", ".markdown"}:
        return run_markdown_file_adapter(source_id=source_id, path=path)
    if ext == ".txt":
        return run_text_file_adapter(source_id=source_id, path=path)
    if ext in {".html", ".htm"}:
        return run_html_file_adapter(source_id=source_id, path=path)
    if ext == ".pdf":
        return run_pdf_file_adapter(source_id=source_id, path=path)
    return make_error_result(
        status="unsupported",
        reason=f"Unsupported local file type: {ext or 'unknown'}",
        input_kind="file",
        source_id=source_id,
        adapter_name="local_file_dispatch",
    )
