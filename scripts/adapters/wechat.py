from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .types import AdapterResult, AssetItem, make_error_result, build_success_result
from .utils import parse_frontmatter


def _camoufox_is_installed() -> bool:
    """Check if Camoufox browser binary is present without triggering auto-download.

    camoufox.pkgman.camoufox_path() calls CamoufoxFetcher().install() when the
    binary is missing — which FIRST deletes Cache, THEN tries downloading from
    GitHub (fails in China), leaving the installation destroyed. We check directly.
    """
    try:
        from camoufox.pkgman import INSTALL_DIR
    except ImportError:
        return False
    exe = INSTALL_DIR / "camoufox.exe"
    vj = INSTALL_DIR / "version.json"
    return exe.exists() and vj.exists()


def run_wechat_adapter(
    *,
    source_id: str,
    input_value: str,
    work_dir: Path,
    tool_dir: Path | None = None,
    deps_dir: Path | None = None,
    options: dict[str, object] | None = None,
) -> AdapterResult:
    del options
    resolved_tool_dir = tool_dir.resolve() if tool_dir else None
    if not resolved_tool_dir or not (resolved_tool_dir / "main.py").exists():
        return make_error_result(
            status="invalid_input",
            reason=f"wechat tool dir not found: {resolved_tool_dir or tool_dir}",
            input_kind="url",
            source_id=source_id,
            adapter_name="wechat-article-to-markdown",
        )

    # Pre-check Camoufox binary before launching the subprocess.
    # Without this, camoufox's camoufox_path() will auto-download from GitHub,
    # which first deletes Cache then fails in China, destroying the install.
    if not _camoufox_is_installed():
        return make_error_result(
            status="runtime_failed",
            reason=(
                "Camoufox browser binary not found. "
                "Run: python scripts/check_deps.py --install-camoufox --china"
            ),
            input_kind="url",
            source_id=source_id,
            adapter_name="wechat-article-to-markdown",
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(Path(os.environ.get("PYTHON", "python"))), str(resolved_tool_dir / "main.py"), input_value, "-o", str(work_dir), "--force"]
    env = os.environ.copy()
    if deps_dir:
        env["PYTHONPATH"] = os.pathsep.join([str(deps_dir), env.get("PYTHONPATH", "")]).strip(os.pathsep)

    try:
        subprocess.run(cmd, cwd=resolved_tool_dir, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        return make_error_result(
            status="runtime_failed",
            reason=f"WeChat adapter failed: {exc}",
            input_kind="url",
            source_id=source_id,
            adapter_name="wechat-article-to-markdown",
        )

    md_files = sorted(path for path in work_dir.glob("*/*.md") if path.parent.name != "debug")
    if not md_files:
        return make_error_result(
            status="empty_result",
            reason="WeChat adapter produced no markdown files.",
            input_kind="url",
            source_id=source_id,
            adapter_name="wechat-article-to-markdown",
        )

    md_path = md_files[0]
    text = md_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    title = meta.get("title") or md_path.stem
    assets: list[AssetItem] = []
    images_dir = md_path.parent / "images"
    if images_dir.exists():
        for image_path in sorted(images_dir.iterdir()):
            if image_path.is_file():
                assets.append({"local_path": str(image_path), "media_type": "image"})

    return build_success_result(
        input_kind="url",
        source_id=source_id,
        adapter_name="wechat-article-to-markdown",
        title=title,
        source_kind="wechat",
        markdown_body=body.strip(),
        plain_text_body=body.strip(),
        source_url=meta.get("source") or input_value,
        author=meta.get("author"),
        date=meta.get("date"),
        assets=assets,
        extra={"fetched_markdown_path": str(md_path)},
    )
