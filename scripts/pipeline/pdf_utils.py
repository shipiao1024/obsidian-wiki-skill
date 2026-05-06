"""PDF generation utilities for brief and deep research reports.

Wraps md-to-pdf (Playwright + Chrome) to generate PDF from Markdown content.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Default path to md-to-pdf script — try multiple locations
_SCRIPT_DIR = Path(__file__).resolve().parent
_MD_TO_PDF_CANDIDATES = [
    _SCRIPT_DIR.parent.parent.parent.parent / "Skill" / "md-to-pdf-v1.1" / "scripts" / "md_to_pdf.py",
    _SCRIPT_DIR.parent.parent.parent.parent.parent / "Skill" / "md-to-pdf-v1.1" / "scripts" / "md_to_pdf.py",
    _SCRIPT_DIR.parent.parent.parent.parent / "Skill" / "md-to-pdf-v1.0" / "scripts" / "md_to_pdf.py",
    _SCRIPT_DIR.parent.parent.parent.parent.parent / "Skill" / "md-to-pdf-v1.0" / "scripts" / "md_to_pdf.py",
]


def _find_md_to_pdf_script() -> Path | None:
    """Locate the md_to_pdf.py script. Check candidate paths, then PATH."""
    for candidate in _MD_TO_PDF_CANDIDATES:
        if candidate.exists():
            return candidate
    # Fallback: check if md_to_pdf is on PATH
    try:
        result = subprocess.run(
            ["python", "-c", "import importlib; importlib.import_module('md_to_pdf')"],
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            return None  # Module importable, use python -m
    except Exception:
        pass
    return None


def clean_wikilinks(md_text: str) -> str:
    """Convert Obsidian [[wikilinks]] to plain text for PDF rendering.

    [[page]] -> page
    [[page|alias]] -> alias
    [[sources/slug]] -> slug
    """
    def _replace(match: re.Match) -> str:
        content = match.group(1)
        if "|" in content:
            return content.split("|", 1)[1]
        # Strip path prefix: sources/slug -> slug
        if "/" in content:
            return content.rsplit("/", 1)[1]
        return content

    return re.sub(r"\[\[([^\]]+)\]\]", _replace, md_text)


def clean_obsidian_syntax(md_text: str) -> str:
    """Clean Obsidian-specific syntax for PDF rendering.

    Strips YAML frontmatter, removes the first h1 (cover page replaces it),
    moves early metadata blocks to an appendix at the end of the document,
    removes callouts and Mermaid, cleans wikilinks.
    """
    # 1. Strip YAML frontmatter (--- ... ---)
    md_text = re.sub(r"\A---\s*\n.*?\n---\s*\n?", "", md_text, flags=re.S)

    # 2. Remove first h1 (cover page title replaces it)
    md_text = re.sub(r"\A\s*#\s+[^\n]+\n*", "", md_text)

    # 3. Extract early metadata blocks and move to appendix
    #    After h1 removal, metadata blocks (callouts, wikilink lists, blank lines)
    #    are at the start of the document.
    _metadata_pattern = re.compile(
        r"\A("
        r"(?:"
        r">\s*\[!\w+\]\s*[^\n]*\n(?:>\s*[^\n]*\n)*"  # callout blocks
        r"|-\s*\[\[[^\]]+\]\]\s*\n"  # wikilink list items (raw_source, source_page, etc.)
        r"|\s*\n"  # blank lines
        r")+)"
    )
    meta_match = _metadata_pattern.match(md_text)
    if meta_match:
        metadata_block = meta_match.group(1).strip()
        md_text = md_text[meta_match.end():]
        if metadata_block:
            md_text = md_text.rstrip() + "\n\n---\n\n## 附录：页面元数据\n\n" + metadata_block + "\n"

    # 4. Remove callout syntax: > [!warning] ... -> > ...
    md_text = re.sub(r">\s*\[!\w+\]\s*", "> ", md_text)
    # 5. Remove Mermaid blocks (not renderable in PDF)
    md_text = re.sub(r"```mermaid\n.*?```", "（图谱见 Obsidian 渲染）", md_text, flags=re.S)
    # 6. Clean wikilinks
    md_text = clean_wikilinks(md_text)
    return md_text


def generate_pdf(
    md_path: Path,
    pdf_path: Path,
    title: str = "",
    theme: str = "academic",
    no_cover: bool = False,
) -> Path | None:
    """Generate PDF from a Markdown file using md-to-pdf.

    Args:
        md_path: Input Markdown file path.
        pdf_path: Output PDF file path.
        title: Report title (auto-extracted from h1 if empty).
        theme: CSS theme (academic/tech/warm).
        no_cover: Skip cover page generation.

    Returns:
        Path to generated PDF, or None if generation failed.
    """
    script = _find_md_to_pdf_script()
    if script is None:
        return None

    cmd = [
        sys.executable, str(script),
        str(md_path), str(pdf_path),
        "--theme", theme,
    ]
    if title:
        cmd.extend(["--title", title])
    if no_cover:
        cmd.append("--no-cover")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and pdf_path.exists():
            return pdf_path
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


def brief_to_pdf(md_path: Path, title: str = "") -> Path | None:
    """Generate PDF for a brief page.

    Reads the brief markdown, cleans Obsidian syntax (including frontmatter),
    writes a temp cleaned version, then calls md-to-pdf with cover page.
    Title format: "{原题目} - 简报"
    """
    if not md_path.exists():
        return None

    md_text = md_path.read_text(encoding="utf-8")
    cleaned = clean_obsidian_syntax(md_text)

    # Write cleaned markdown to temp file alongside the original
    temp_md = md_path.with_suffix(".pdf-ready.md")
    temp_md.write_text(cleaned, encoding="utf-8")

    pdf_path = md_path.with_suffix(".pdf")
    try:
        result = generate_pdf(temp_md, pdf_path, title=title, no_cover=False)
        return result
    finally:
        # Clean up temp file
        if temp_md.exists():
            temp_md.unlink()


def report_to_pdf(md_path: Path, title: str = "") -> Path | None:
    """Generate PDF for a deep research report.

    Reads the report markdown, cleans Obsidian syntax, writes a temp
    cleaned version, then calls md-to-pdf with cover page.
    """
    if not md_path.exists():
        return None

    md_text = md_path.read_text(encoding="utf-8")
    cleaned = clean_obsidian_syntax(md_text)

    temp_md = md_path.with_suffix(".pdf-ready.md")
    temp_md.write_text(cleaned, encoding="utf-8")

    pdf_path = md_path.with_suffix(".pdf")
    try:
        result = generate_pdf(temp_md, pdf_path, title=title, no_cover=False)
        return result
    finally:
        if temp_md.exists():
            temp_md.unlink()
