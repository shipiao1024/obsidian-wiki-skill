from __future__ import annotations

from .types import QualityLevel
from .utils import normalized_text_length, looks_placeholder_title


def assess_web_quality(*, title: str, markdown_body: str, plain_text_body: str) -> QualityLevel:
    length = max(normalized_text_length(markdown_body), normalized_text_length(plain_text_body))
    if looks_placeholder_title(title) or length < 200:
        return "low"
    if length >= 1200:
        return "high"
    return "acceptable"


def assess_video_quality(
    *, title: str, plain_text_body: str, transcript_source: str = ""
) -> QualityLevel:
    length = normalized_text_length(plain_text_body)
    if looks_placeholder_title(title) or length < 300:
        return "low"
    if transcript_source == "asr":
        return "acceptable"
    if length >= 1500:
        return "high"
    return "acceptable"


def assess_pdf_quality(*, title: str, plain_text_body: str) -> QualityLevel:
    del title
    length = normalized_text_length(plain_text_body)
    if length < 300:
        return "low"
    if length >= 1500:
        return "high"
    return "acceptable"
