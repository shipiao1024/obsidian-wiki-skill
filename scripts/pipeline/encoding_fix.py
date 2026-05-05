"""Windows console encoding fix for Chinese output.

Import this module early (or call fix_windows_encoding()) to ensure
stdout/stderr use UTF-8 on Windows terminals that default to GBK.

Usage:
    from pipeline.encoding_fix import fix_windows_encoding
    fix_windows_encoding()
"""

from __future__ import annotations

import sys


def fix_windows_encoding() -> None:
    """Reconfigure stdout/stderr to UTF-8 on Windows.

    On Windows, the default console encoding is often GBK (code page 936),
    which cannot represent all Unicode characters. This function reconfigures
    sys.stdout and sys.stderr to use UTF-8 with surrogateescape error handling,
    preventing UnicodeEncodeError when printing Chinese text.

    No-op on non-Windows platforms or when stdout is not a TTY (piped output
    already uses the correct encoding or PYTHONIOENCODING).
    """
    if sys.platform != "win32":
        return

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        # Only reconfigure if encoding is not already UTF-8
        current = getattr(stream, "encoding", "") or ""
        if current.lower().replace("-", "") in ("utf8", "utf_8"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            # reconfigure not available (Python < 3.7) or stream closed
            pass
