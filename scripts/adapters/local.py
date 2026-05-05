from __future__ import annotations

import re
from pathlib import Path

from .types import AdapterResult, make_error_result, build_success_result, AssetItem
from .utils import html_to_markdown_fallback, html_to_plain_text
from .quality import assess_pdf_quality


# ---------------------------------------------------------------------------
# Format normalization: standard tools for multi-format → Markdown conversion
# ---------------------------------------------------------------------------

def _try_markitdown_convert(path: Path) -> str:
    """Convert a file to Markdown using Microsoft markitdown.

    Falls back gracefully if markitdown is not installed.
    Raises RuntimeError if conversion fails.
    """
    try:
        from markitdown import MarkItDown
    except ImportError:
        raise RuntimeError(
            f"markitdown is not installed. Install with: pip install markitdown"
        ) from None
    md = MarkItDown()
    result = md.convert(str(path))
    text = getattr(result, "text_content", None) or str(result)
    if not text.strip():
        raise RuntimeError(f"markitdown produced empty output for {path.name}")
    return text.strip()


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
    # Try markitdown first (better structure preservation), fall back to pypdf
    try:
        text = _try_markitdown_convert(path)
        adapter_name = "markitdown"
    except Exception:
        try:
            text = extract_pdf_text(path)
            adapter_name = "pdf_text_extract"
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
            adapter_name=adapter_name,
        )
    # Clean download-site markers from title
    clean_title = re.sub(r"\s*\((?:z-library\.\w+|1lib\.\w+|z-lib\.\w+|z-lib\.sk|1lib\.sk|z-library\.sk)[^)]*\)", "", path.stem, flags=re.IGNORECASE).strip()
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name=adapter_name,
        title=clean_title or path.stem,
        source_kind="pdf",
        markdown_body=text,
        plain_text_body=text,
        quality=assess_pdf_quality(title=clean_title or path.stem, plain_text_body=text),
        extra={"file_path": str(path)},
    )


def run_docx_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    """DOCX → Markdown via markitdown."""
    try:
        text = _try_markitdown_convert(path)
    except RuntimeError as exc:
        return make_error_result(
            status="dependency_missing",
            reason=str(exc),
            input_kind="file",
            source_id=source_id,
            adapter_name="markitdown",
        )
    except Exception as exc:
        return make_error_result(
            status="runtime_failed",
            reason=f"DOCX conversion failed: {exc}",
            input_kind="file",
            source_id=source_id,
            adapter_name="markitdown",
        )
    if not text.strip():
        return make_error_result(
            status="empty_result",
            reason="DOCX file produced no readable text.",
            input_kind="file",
            source_id=source_id,
            adapter_name="markitdown",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="markitdown",
        title=path.stem,
        source_kind="docx",
        markdown_body=text,
        plain_text_body=text,
        extra={"file_path": str(path)},
    )


def run_pptx_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    """PPTX → Markdown via markitdown."""
    try:
        text = _try_markitdown_convert(path)
    except RuntimeError as exc:
        return make_error_result(
            status="dependency_missing",
            reason=str(exc),
            input_kind="file",
            source_id=source_id,
            adapter_name="markitdown",
        )
    except Exception as exc:
        return make_error_result(
            status="runtime_failed",
            reason=f"PPTX conversion failed: {exc}",
            input_kind="file",
            source_id=source_id,
            adapter_name="markitdown",
        )
    if not text.strip():
        return make_error_result(
            status="empty_result",
            reason="PPTX file produced no readable text.",
            input_kind="file",
            source_id=source_id,
            adapter_name="markitdown",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="markitdown",
        title=path.stem,
        source_kind="pptx",
        markdown_body=text,
        plain_text_body=text,
        extra={"file_path": str(path)},
    )


def run_xlsx_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    """XLSX/XLS → Markdown tables via pandas."""
    try:
        import pandas as pd
    except ImportError:
        return make_error_result(
            status="dependency_missing",
            reason="pandas is not installed. Install with: pip install pandas openpyxl",
            input_kind="file",
            source_id=source_id,
            adapter_name="xlsx_to_markdown",
        )
    try:
        sheets = pd.read_excel(str(path), sheet_name=None)
    except Exception as exc:
        return make_error_result(
            status="runtime_failed",
            reason=f"XLSX read failed: {exc}",
            input_kind="file",
            source_id=source_id,
            adapter_name="xlsx_to_markdown",
        )
    if not sheets:
        return make_error_result(
            status="empty_result",
            reason="XLSX file contains no sheets.",
            input_kind="file",
            source_id=source_id,
            adapter_name="xlsx_to_markdown",
        )
    parts: list[str] = []
    for sheet_name, df in sheets.items():
        if df.empty:
            continue
        parts.append(f"## {sheet_name}\n\n{df.to_markdown(index=False)}")
    text = "\n\n".join(parts).strip()
    if not text:
        return make_error_result(
            status="empty_result",
            reason="XLSX file contains no readable data.",
            input_kind="file",
            source_id=source_id,
            adapter_name="xlsx_to_markdown",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="xlsx_to_markdown",
        title=path.stem,
        source_kind="xlsx",
        markdown_body=text,
        plain_text_body=text,
        extra={"file_path": str(path), "sheets": list(sheets.keys())},
    )


def run_epub_file_adapter(*, source_id: str, path: Path) -> AdapterResult:
    """EPUB → Markdown via ebooklib + BeautifulSoup."""
    try:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
    except ImportError:
        return make_error_result(
            status="dependency_missing",
            reason="ebooklib and beautifulsoup4 are not installed. Install with: pip install ebooklib beautifulsoup4",
            input_kind="file",
            source_id=source_id,
            adapter_name="epub_to_markdown",
        )
    try:
        book = epub.read_epub(str(path))
    except Exception as exc:
        return make_error_result(
            status="runtime_failed",
            reason=f"EPUB read failed: {exc}",
            input_kind="file",
            source_id=source_id,
            adapter_name="epub_to_markdown",
        )
    # Extract title from metadata
    title = ""
    try:
        title_meta = book.get_metadata("DC", "title")
        if title_meta:
            title = title_meta[0][0]
    except Exception:
        pass
    # Extract text from all document items
    parts: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        try:
            html_content = item.get_content().decode("utf-8", errors="replace")
            soup = BeautifulSoup(html_content, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if text.strip():
                parts.append(text.strip())
        except Exception:
            continue
    body = "\n\n".join(parts).strip()
    if not body:
        return make_error_result(
            status="empty_result",
            reason="EPUB file contains no readable text.",
            input_kind="file",
            source_id=source_id,
            adapter_name="epub_to_markdown",
        )
    return build_success_result(
        input_kind="file",
        source_id=source_id,
        adapter_name="epub_to_markdown",
        title=title or path.stem,
        source_kind="epub",
        markdown_body=body,
        plain_text_body=body,
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
    if ext == ".docx":
        return run_docx_file_adapter(source_id=source_id, path=path)
    if ext == ".pptx":
        return run_pptx_file_adapter(source_id=source_id, path=path)
    if ext in {".xlsx", ".xls"}:
        return run_xlsx_file_adapter(source_id=source_id, path=path)
    if ext == ".epub":
        return run_epub_file_adapter(source_id=source_id, path=path)
    return make_error_result(
        status="unsupported",
        reason=f"Unsupported local file type: {ext or 'unknown'}",
        input_kind="file",
        source_id=source_id,
        adapter_name="local_file_dispatch",
    )
