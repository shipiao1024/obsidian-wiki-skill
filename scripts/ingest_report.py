"""Stub: forwards to pipeline.ingest_report for backward compatibility.

Usage: python scripts/ingest_report.py [args...]
Delegates to: python -m pipeline.ingest_report [args...]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PIPELINE_MODULE = Path(__file__).resolve().parent / "pipeline" / "ingest_report.py"


def main() -> int:
    if _PIPELINE_MODULE.exists():
        return subprocess.call([sys.executable, str(_PIPELINE_MODULE), *sys.argv[1:]])
    # Fallback: try module import
    return subprocess.call([sys.executable, "-m", "pipeline.ingest_report", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
