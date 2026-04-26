from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .types import AdapterStatus, AdapterResult, make_error_result, build_success_result
from .utils import parse_configured_command, parse_frontmatter
from .quality import assess_web_quality
from env_compat import resolve_env


_BAOYU_SKILL_ENTRY = Path.home() / ".claude" / "skills" / "baoyu-url-to-markdown" / "scripts" / "main.ts"


def resolve_web_adapter_command() -> list[str] | None:
    configured = resolve_env("KWIKI_WEB_ADAPTER_BIN")
    if configured:
        return parse_configured_command(configured)
    discovered = shutil.which("baoyu-url-to-markdown")
    if discovered:
        return [discovered]
    if _BAOYU_SKILL_ENTRY.exists() and shutil.which("bun") is not None:
        return ["bun", str(_BAOYU_SKILL_ENTRY)]
    return None


def classify_web_adapter_failure(exc: subprocess.CalledProcessError) -> tuple[AdapterStatus, str]:
    parts = [
        str(getattr(exc, "stdout", "") or ""),
        str(getattr(exc, "stderr", "") or ""),
        str(exc),
    ]
    message = " ".join(part for part in parts if part).strip()
    lowered = message.lower()

    if "chrome debug port not ready" in lowered:
        return "browser_not_ready", f"Web adapter browser is not ready: {message}"
    if "unable to connect" in lowered or "defuddle.md fallback failed" in lowered:
        return "network_failed", f"Web adapter network access failed: {message}"
    return "runtime_failed", f"Web adapter failed: {message or exc}"


def run_web_adapter(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
    options: dict[str, object] | None = None,
) -> AdapterResult:
    del options
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path = work_dir / "article.md"
    base_cmd = resolve_web_adapter_command()
    if not base_cmd:
        return make_error_result(
            status="dependency_missing",
            reason="Web adapter not found. Install baoyu-url-to-markdown (npm) or set KWIKI_WEB_ADAPTER_BIN, or install the baoyu skill + bun.",
            input_kind="url",
            source_id=source_id,
            adapter_name="baoyu-url-to-markdown",
        )
    cmd = [*base_cmd, input_value, "-o", str(output_path)]
    # Windows .cmd wrappers require shell=True for subprocess.run
    use_shell = sys.platform == "win32" and any(
        arg.lower().endswith(".cmd") for arg in cmd
    )
    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=use_shell,
        )
    except FileNotFoundError as exc:
        return make_error_result(
            status="dependency_missing",
            reason=f"Web adapter executable not found: {exc}",
            input_kind="url",
            source_id=source_id,
            adapter_name="baoyu-url-to-markdown",
        )
    except subprocess.CalledProcessError as exc:
        status, reason = classify_web_adapter_failure(exc)
        return make_error_result(
            status=status,
            reason=reason,
            input_kind="url",
            source_id=source_id,
            adapter_name="baoyu-url-to-markdown",
        )

    if not output_path.exists():
        return make_error_result(
            status="empty_result",
            reason="Web adapter produced no markdown output.",
            input_kind="url",
            source_id=source_id,
            adapter_name="baoyu-url-to-markdown",
        )

    text = output_path.read_text(encoding="utf-8")
    if not text.strip():
        return make_error_result(
            status="empty_result",
            reason="Web adapter produced empty markdown.",
            input_kind="url",
            source_id=source_id,
            adapter_name="baoyu-url-to-markdown",
        )

    meta, body = parse_frontmatter(text)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    title = str(meta.get("title", "")).strip() or (lines[0].lstrip("# ").strip() if lines else output_path.stem)
    return build_success_result(
        input_kind="url",
        source_id=source_id,
        adapter_name="baoyu-url-to-markdown",
        title=title or output_path.stem,
        source_kind="web",
        markdown_body=text,
        plain_text_body=text,
        source_url=input_value,
        quality=assess_web_quality(title=title or output_path.stem, markdown_body=text, plain_text_body=text),
        extra={"fetched_markdown_path": str(output_path)},
    )
