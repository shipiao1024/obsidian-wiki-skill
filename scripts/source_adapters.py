"""Backward-compatibility shim. All source adapter logic moved to adapters/ package.

Explicit re-exports replace the previous wildcard import (from adapters import *)
to avoid namespace pollution and make the public API contract clear.
"""

from adapters import run_adapter_for_source  # noqa: F401
from adapters.types import AdapterResult, make_error_result, build_success_result  # noqa: F401
from adapters.collection import expand_video_collection_urls, normalize_collection_entry_url  # noqa: F401
from adapters.quality import assess_web_quality, assess_video_quality, assess_pdf_quality  # noqa: F401
from adapters.text import run_plain_text_adapter  # noqa: F401
from adapters.local import run_local_file_adapter  # noqa: F401
from adapters.wechat import run_wechat_adapter  # noqa: F401
from adapters.web import run_web_adapter, resolve_web_adapter_command  # noqa: F401
from adapters.video import (
    run_video_adapter,
    resolve_video_cookie_arg_variants,
    normalize_video_fetch_url,
)  # noqa: F401

__all__ = [
    "run_adapter_for_source",
    "AdapterResult",
    "make_error_result",
    "build_success_result",
    "expand_video_collection_urls",
    "normalize_collection_entry_url",
    "assess_web_quality",
    "assess_video_quality",
    "assess_pdf_quality",
    "run_plain_text_adapter",
    "run_local_file_adapter",
    "run_wechat_adapter",
    "run_web_adapter",
    "resolve_web_adapter_command",
    "run_video_adapter",
    "resolve_video_cookie_arg_variants",
    "normalize_video_fetch_url",
]
