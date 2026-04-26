"""Entry point for wechat_to_md CLI."""

# ── Prevent camoufox from auto-downloading and destroying Cache ──────────────
# camoufox.pkgman.camoufox_path() calls CamoufoxFetcher().install() when the
# browser binary is missing. That call FIRST cleans Cache, THEN tries to
# download from GitHub — which fails in China, leaving Cache empty.
# We monkey-patch it to raise immediately instead of nuking the installation.
import os

try:
    import camoufox.pkgman as _cpm

    _original_camoufox_path = _cpm.camoufox_path

    def _safe_camoufox_path(download_if_missing: bool = True):
        if not os.path.exists(_cpm.INSTALL_DIR) or not os.listdir(_cpm.INSTALL_DIR):
            raise FileNotFoundError(
                f"Camoufox binary not found at {_cpm.INSTALL_DIR}. "
                "Run: python scripts/check_deps.py --install-camoufox --china"
            )
        return _original_camoufox_path(download_if_missing=False)

    _cpm.camoufox_path = _safe_camoufox_path
except ImportError:
    pass

from wechat_to_md.cli import main

if __name__ == "__main__":
    main()
