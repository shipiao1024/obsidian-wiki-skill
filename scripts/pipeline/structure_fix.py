"""Markdown structure fixing for Obsidian rendering compatibility.

Ensures blank lines around math blocks, list blocks, and table blocks,
and trims inner blank lines in multi-line math blocks. Pure stdlib.
"""

from __future__ import annotations

import re
from .text_utils import FRONTMATTER

# ── line-level helpers ──────────────────────────────────────────────

_LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s")
_TABLE_SEP = re.compile(r"^\|?[\s:]*-+[\s:|]*-+[\s:]*\|?$")
_MATH_OPEN = re.compile(r"^\s*\$\$")
_MATH_CLOSE = re.compile(r"^\s*\$\$(?:\s*)$")
_STANDALONE_MATH = re.compile(r"^\s*\$\$.+\$\$\s*$")
_FENCE_START = re.compile(r"^(\s*)(`{3,}|~{3,})")


def _is_empty(line: str) -> bool:
    return line.strip() == ""


def _is_fence_start(line: str) -> tuple[str, int] | None:
    m = _FENCE_START.match(line)
    if not m:
        return None
    return m.group(2)[0], len(m.group(2))


def _is_fence_end(line: str, marker: str, size: int) -> bool:
    escaped = re.escape(marker)
    return bool(re.match(rf"^\s*{escaped}{{{size},}}\s*$", line))


def _strip_frontmatter(content: str) -> tuple[str, str]:
    m = FRONTMATTER.match(content)
    if not m:
        return "", content
    return content[: m.end()], content[m.end() :]


# ── phase 1: ensure blank lines around block elements ───────────────

def _ensure_blank_around_blocks(body: str, rules: dict) -> tuple[str, dict]:
    lines = body.split("\n")
    need_blank_before: set[int] = set()
    need_blank_after: set[int] = set()
    stats = {"math_blocks": 0, "list_blocks": 0, "table_blocks": 0, "empty_lines_added": 0}

    in_fence = False
    fence_marker = ""
    fence_size = 0

    # scan for block boundaries
    i = 0
    while i < len(lines):
        line = lines[i]

        # fence tracking
        fence = _is_fence_start(line)
        if not in_fence and fence:
            in_fence = True
            fence_marker, fence_size = fence
            i += 1
            continue
        if in_fence:
            if _is_fence_end(line, fence_marker, fence_size):
                in_fence = False
            i += 1
            continue
        if in_fence:
            i += 1
            continue

        # math block (multi-line $$...$$)
        if rules.get("fix_math_blocks", True) and _MATH_OPEN.match(line) and not _STANDALONE_MATH.match(line):
            start = i
            i += 1
            while i < len(lines) and not _MATH_CLOSE.match(lines[i]):
                i += 1
            end = i
            stats["math_blocks"] += 1
            if start > 0 and not _is_empty(lines[start - 1]):
                need_blank_before.add(start)
            if end < len(lines) - 1 and not _is_empty(lines[end + 1]):
                need_blank_after.add(end)
            i += 1
            continue

        # list block
        if rules.get("fix_list_blocks", True) and _LIST_ITEM.match(line):
            start = i
            while i < len(lines) and (_LIST_ITEM.match(lines[i]) or (_is_empty(lines[i]) and i + 1 < len(lines) and _LIST_ITEM.match(lines[i + 1]))):
                i += 1
            end = i - 1
            stats["list_blocks"] += 1
            if start > 0 and not _is_empty(lines[start - 1]):
                need_blank_before.add(start)
            if end < len(lines) - 1 and not _is_empty(lines[end + 1]):
                need_blank_after.add(end)
            continue

        # table block
        if rules.get("fix_table_blocks", True) and _TABLE_SEP.match(line.strip()):
            start = i - 1 if i > 0 and "|" in lines[i - 1] else i
            while i < len(lines) and "|" in lines[i]:
                i += 1
            end = i - 1
            stats["table_blocks"] += 1
            if start > 0 and not _is_empty(lines[start - 1]):
                need_blank_before.add(start)
            if end < len(lines) - 1 and not _is_empty(lines[end + 1]):
                need_blank_after.add(end)
            continue

        i += 1

    # apply blank line insertions
    out: list[str] = []
    for idx, line in enumerate(lines):
        if idx in need_blank_before and out and not _is_empty(out[-1]):
            out.append("")
            stats["empty_lines_added"] += 1
        out.append(line)
        if idx in need_blank_after and idx < len(lines) - 1 and not _is_empty(lines[idx + 1]):
            out.append("")
            stats["empty_lines_added"] += 1

    return "\n".join(out), stats


# ── phase 2: trim inner blank lines in multi-line math blocks ───────

def _trim_math_inner_blank_lines(body: str) -> tuple[str, int]:
    lines = body.split("\n")
    out: list[str] = []
    in_fence = False
    fence_marker = ""
    fence_size = 0
    in_math = False
    math_buf: list[str] = []
    removed = 0

    def _flush_math() -> None:
        nonlocal removed
        if len(math_buf) < 2:
            out.extend(math_buf)
            math_buf.clear()
            return
        open_line = math_buf[0]
        close_line = math_buf[-1]
        middle = math_buf[1:-1]
        while middle and _is_empty(middle[0]):
            middle.pop(0)
            removed += 1
        while middle and _is_empty(middle[-1]):
            middle.pop()
            removed += 1
        out.append(open_line)
        out.extend(middle)
        out.append(close_line)
        math_buf.clear()

    for line in lines:
        fence = _is_fence_start(line)

        if not in_fence and fence:
            in_fence = True
            fence_marker, fence_size = fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            if _is_fence_end(line, fence_marker, fence_size):
                in_fence = False
            continue

        if not in_math and _MATH_OPEN.match(line) and not _STANDALONE_MATH.match(line):
            in_math = True
            math_buf = [line]
            continue
        if in_math:
            math_buf.append(line)
            if _MATH_CLOSE.match(line):
                _flush_math()
                in_math = False
            continue

        out.append(line)

    if math_buf:
        out.extend(math_buf)

    return "\n".join(out), removed


# ── phase 3: standalone single-line math blocks ────────────────────

def _fix_standalone_math(body: str, enabled: bool) -> tuple[str, int]:
    if not enabled:
        return body, 0

    lines = body.split("\n")
    out: list[str] = []
    in_fence = False
    fence_marker = ""
    fence_size = 0
    added = 0

    for i, line in enumerate(lines):
        fence = _is_fence_start(line)
        if not in_fence and fence:
            in_fence = True
            fence_marker, fence_size = fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            if _is_fence_end(line, fence_marker, fence_size):
                in_fence = False
            continue

        if _STANDALONE_MATH.match(line):
            if out and not _is_empty(out[-1]):
                out.append("")
                added += 1
            out.append(line)
            if i < len(lines) - 1 and not _is_empty(lines[i + 1]):
                out.append("")
                added += 1
            continue

        out.append(line)

    return "\n".join(out), added


# ── main entry ──────────────────────────────────────────────────────

_DEFAULT_RULES = {
    "fix_math_blocks": True,
    "fix_list_blocks": True,
    "fix_table_blocks": True,
    "trim_math_inner_blank_lines": True,
}


def fix_structure(content: str, rules: dict | None = None) -> tuple[str, dict]:
    """Fix markdown structure for Obsidian rendering.

    Returns (fixed_content, stats_dict).
    """
    if not content or not content.strip():
        return content, {}

    effective = {**_DEFAULT_RULES, **(rules or {})}

    # strip frontmatter, fix body, reattach
    fm, body = _strip_frontmatter(content)

    # phase 1
    body, phase1_stats = _ensure_blank_around_blocks(body, effective)

    # phase 2
    phase2_removed = 0
    if effective.get("trim_math_inner_blank_lines", True):
        body, phase2_removed = _trim_math_inner_blank_lines(body)

    # phase 3
    body, phase3_added = _fix_standalone_math(body, effective.get("fix_math_blocks", True))

    stats = {
        "math_blocks": phase1_stats["math_blocks"],
        "list_blocks": phase1_stats["list_blocks"],
        "table_blocks": phase1_stats["table_blocks"],
        "empty_lines_added": phase1_stats["empty_lines_added"] + phase3_added,
        "math_inner_blank_lines_removed": phase2_removed,
    }

    return fm + body, stats


def detect_structure_violations(content: str) -> list[dict]:
    """Detect (but don't fix) structure violations. For lint reporting."""
    if not content or not content.strip():
        return []

    _, body = _strip_frontmatter(content)
    lines = body.split("\n")
    violations: list[dict] = []
    in_fence = False
    fence_marker = ""
    fence_size = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        fence = _is_fence_start(line)
        if not in_fence and fence:
            in_fence = True
            fence_marker, fence_size = fence
            i += 1
            continue
        if in_fence:
            if _is_fence_end(line, fence_marker, fence_size):
                in_fence = False
            i += 1
            continue

        # math block
        if _MATH_OPEN.match(line) and not _STANDALONE_MATH.match(line):
            start = i
            i += 1
            while i < len(lines) and not _MATH_CLOSE.match(lines[i]):
                i += 1
            end = i
            if start > 0 and not _is_empty(lines[start - 1]):
                violations.append({"line": start + 1, "type": "math", "issue": "missing blank line before math block"})
            if end < len(lines) - 1 and not _is_empty(lines[end + 1]):
                violations.append({"line": end + 1, "type": "math", "issue": "missing blank line after math block"})
            i += 1
            continue

        # list block
        if _LIST_ITEM.match(line):
            start = i
            while i < len(lines) and (_LIST_ITEM.match(lines[i]) or (_is_empty(lines[i]) and i + 1 < len(lines) and _LIST_ITEM.match(lines[i + 1]))):
                i += 1
            end = i - 1
            if start > 0 and not _is_empty(lines[start - 1]):
                violations.append({"line": start + 1, "type": "list", "issue": "missing blank line before list block"})
            if end < len(lines) - 1 and not _is_empty(lines[end + 1]):
                violations.append({"line": end + 1, "type": "list", "issue": "missing blank line after list block"})
            continue

        # table block
        if _TABLE_SEP.match(line.strip()):
            start = i - 1 if i > 0 and "|" in lines[i - 1] else i
            while i < len(lines) and "|" in lines[i]:
                i += 1
            end = i - 1
            if start > 0 and not _is_empty(lines[start - 1]):
                violations.append({"line": start + 1, "type": "table", "issue": "missing blank line before table"})
            if end < len(lines) - 1 and not _is_empty(lines[end + 1]):
                violations.append({"line": end + 1, "type": "table", "issue": "missing blank line after table"})
            continue

        i += 1

    return violations
