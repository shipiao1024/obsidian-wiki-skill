"""Intent-based auto-routing for wiki_query.

Analyzes the user's natural-language question and selects the most appropriate
output mode + digest_type without requiring explicit --mode flags.

Three entry layers:
  ask    — quick Q&A, meeting prep, counter-arguments (brief / briefing / contradict / talk-track)
  digest — deep synthesis, comparisons, timelines, essays, reading paths
  context — material pack for feeding into another LLM (draft-context)

Deep-research is triggered when the question signals strategic importance,
external verification needs, or framing risk (follows 9-phase protocol).

Usage:
  from pipeline.output.intent_router import resolve_intent
  mode, digest_type, entry = resolve_intent(question)
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Keyword patterns (Chinese + English)
# ---------------------------------------------------------------------------

# --- Context patterns (highest priority — explicit "feed to LLM" intent) ---
CONTEXT_PATTERNS = [
    r"素材",
    r"上下文",
    r"喂给",
    r"喂给.*LLM",
    r"二次分析",
    r"整理.*给",
    r"准备.*材料.*给",
    r"copy.?paste",
    r"draft.?context",
    r"pack.*context",
]

# --- Deep-research patterns (strategic / external / risk) ---
DEEP_RESEARCH_PATTERNS = [
    r"深入研究",
    r"深度研究",
    r"系统分析",
    r"deep\s*research",
    r"全面调研",
    r"可行性分析",
    r"量产.*可行",
    r"风险.*分析",
    r"战略.*判断",
    r"投资.*决策",
    r"要不要.*投入",
    r"值得.*投入",
    r"should\s+we\s+invest",
    r"market\s+sizing",
]

# --- Digest sub-type patterns ---
COMPARE_PATTERNS = [
    r"对比",
    r"比较",
    r"vs",
    r"versus",
    r"区别",
    r"差异",
    r"优劣",
    r"优缺点",
    r"哪个.*好",
    r"哪.*更好",
    r"compare",
    r"comparison",
    r"A\s*vs\s*B",
]

TIMELINE_PATTERNS = [
    r"时间线",
    r"发展.*脉络",
    r"演变",
    r"演进",
    r"历史.*沿革",
    r"按时间",
    r"timeline",
    r"evolution",
    r"history\s+of",
]

ESSAY_PATTERNS = [
    r"写.*文章",
    r"帮我写",
    r"草稿",
    r"draft.*essay",
    r"write.*article",
    r"帮我.*撰",
    r"输出.*文",
]

READING_LIST_PATTERNS = [
    r"学习路径",
    r"系统学习",
    r"推荐阅读",
    r"reading\s*list",
    r"学习.*顺序",
    r"应该.*读",
    r"从.*学起",
    r"入门.*路径",
    r"先.*再",
]

# --- Contradict patterns ---
CONTRADICT_PATTERNS = [
    r"反驳",
    r"反方",
    r"挑战.*观点",
    r"质疑",
    r"counter",
    r"rebut",
    r"反驳.*论据",
    r"steel.?man",
    r"对立面",
    r"反对.*理由",
    r"argue\s+against",
]

# --- Briefing patterns (meeting prep / structured overview) ---
BRIEFING_PATTERNS = [
    r"准备.*会议",
    r"准备.*开会",
    r"会议.*准备",
    r"汇报",
    r"简报",
    r"briefing",
    r"meeting\s+prep",
    r"帮我.*准备",
    r"talk\s*track",
    r"讨论.*材料",
    r"开会.*讨论",
    r"讨论.*准备",
]

# --- Simple fact-lookup patterns (default brief) ---
BRIEF_PATTERNS = [
    r"^.{0,8}是什么",
    r"^.{0,8}是啥",
    r"^.{0,8}什么意思",
    r"what\s+is\b",
    r"who\s+is\b",
    r"定义",
    r"explain",
    r"summarize",
    r"总结一下",
    r"简要",
    r"快速了解",
    r"概述",
]


def _match_any(text: str, patterns: list[str]) -> bool:
    """Return True if text matches any regex pattern (case-insensitive)."""
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def resolve_intent(question: str) -> tuple[str, str, str]:
    """Analyze *question* and return (mode, digest_type, entry_layer).

    entry_layer is one of "ask", "digest", "context".
    mode is one of the VALID_MODES values.
    digest_type is "deep", "compare", or "timeline" (only meaningful for digest mode).
    """
    q = question.strip()

    # --- Layer 1: Context (explicit "material pack" intent) ---
    if _match_any(q, CONTEXT_PATTERNS):
        return "draft-context", "deep", "context"

    # --- Layer 2: Deep research (strategic / high-stakes) ---
    if _match_any(q, DEEP_RESEARCH_PATTERNS):
        return "deep-research", "deep", "ask"

    # --- Layer 3: Digest sub-types ---
    if _match_any(q, COMPARE_PATTERNS):
        return "digest", "compare", "digest"

    if _match_any(q, TIMELINE_PATTERNS):
        return "digest", "timeline", "digest"

    if _match_any(q, ESSAY_PATTERNS):
        return "essay", "deep", "digest"

    if _match_any(q, READING_LIST_PATTERNS):
        return "reading-list", "deep", "digest"

    # --- Layer 4: Contradict ---
    if _match_any(q, CONTRADICT_PATTERNS):
        return "contradict", "deep", "ask"

    # --- Layer 5: Briefing (meeting prep) ---
    if _match_any(q, BRIEFING_PATTERNS):
        return "briefing", "deep", "ask"

    # --- Layer 6: Simple brief (explicit short-answer signals) ---
    if _match_any(q, BRIEF_PATTERNS):
        return "brief", "deep", "ask"

    # --- Default: brief (most natural for a question) ---
    return "brief", "deep", "ask"
