"""Implicit deep research trigger detection.

Analyzes ingest results and knowledge base state to detect when a topic
warrants deep research, and generates suggestions for the user.

Trigger conditions (any one is sufficient):
  1. High-value cross-domain collision: insight confidence >= Working with
     bridge_logic that connects two established domains
  2. Accumulated contradictions: 3+ claims with evidence_type == "disputed"
     on the same topic
  3. High-impact open question: question that, if answered, would affect
     multiple existing pages (detected via keyword overlap)
  4. Knowledge gap cluster: 3+ claims with evidence_type == "gap" in the
     same domain
  5. Confidence cliff: a Supported/Stable claim contradicted by new evidence
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .shared import parse_frontmatter, section_excerpt


@dataclass
class DeepResearchTrigger:
    trigger_type: str
    topic: str
    reason: str
    evidence: list[str]
    suggested_hypotheses: list[str]
    priority: str = "medium"  # low, medium, high


def detect_triggers(
    compiled_payload: dict[str, object] | None,
    vault: Path,
    source_slug: str = "",
) -> list[DeepResearchTrigger]:
    """Analyze compile results and vault state for deep research triggers."""
    triggers: list[DeepResearchTrigger] = []
    result = (compiled_payload or {}).get("result", {})
    if not isinstance(result, dict):
        return triggers

    # Trigger 1: High-value cross-domain collision
    triggers.extend(_detect_cross_domain_triggers(result))

    # Trigger 2: Accumulated contradictions
    triggers.extend(_detect_contradiction_triggers(result, vault))

    # Trigger 3: High-impact open questions
    triggers.extend(_detect_question_triggers(result, vault))

    # Trigger 4: Knowledge gap clusters
    triggers.extend(_detect_gap_triggers(result))

    # Trigger 5: Confidence cliff
    triggers.extend(_detect_confidence_cliff_triggers(result, vault))

    # Deduplicate by topic
    seen_topics: set[str] = set()
    deduped: list[DeepResearchTrigger] = []
    for t in triggers:
        key = t.topic.lower().strip()
        if key not in seen_topics:
            seen_topics.add(key)
            deduped.append(t)

    return deduped


def _detect_cross_domain_triggers(result: dict) -> list[DeepResearchTrigger]:
    """Detect high-value cross-domain collisions."""
    triggers: list[DeepResearchTrigger] = []
    insights = result.get("cross_domain_insights", [])
    if not isinstance(insights, list):
        return triggers

    _ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}

    for insight in insights:
        if not isinstance(insight, dict):
            continue
        concept = insight.get("mapped_concept", "")
        domain = insight.get("target_domain", "")
        logic = insight.get("bridge_logic", "")
        confidence = insight.get("confidence", "")
        rank = _ORDINAL_RANK.get(confidence, 0)

        if rank >= 2 and logic:  # Working or above
            triggers.append(DeepResearchTrigger(
                trigger_type="cross_domain_collision",
                topic=f"{concept} ↔ {domain}",
                reason=f"跨域联想置信度达到 {confidence}，值得深入研究",
                evidence=[logic],
                suggested_hypotheses=[
                    f"{concept} 的核心模式是否可以迁移到 {domain}",
                    f"如果迁移成立，{domain} 中有哪些现有理论需要修正",
                ],
                priority="high" if rank >= 3 else "medium",
            ))

    return triggers


def _detect_contradiction_triggers(result: dict, vault: Path) -> list[DeepResearchTrigger]:
    """Detect accumulated contradictions on the same topic."""
    triggers: list[DeepResearchTrigger] = []
    claims = result.get("claim_inventory", [])
    if not isinstance(claims, list):
        return triggers

    disputed: list[dict] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if claim.get("evidence_type") == "disputed":
            disputed.append(claim)

    if len(disputed) >= 3:
        topics = [c.get("claim", "") for c in disputed if c.get("claim")]
        triggers.append(DeepResearchTrigger(
            trigger_type="accumulated_contradictions",
            topic=topics[0][:60] if topics else "未知主题",
            reason=f"发现 {len(disputed)} 条争议性判断，需要深入研究澄清",
            evidence=topics[:5],
            suggested_hypotheses=[
                f"争议的核心分歧点是什么：{topics[0][:40]}...",
                "是否有新的证据可以解决这些争议",
            ],
            priority="high",
        ))

    return triggers


def _detect_question_triggers(result: dict, vault: Path) -> list[DeepResearchTrigger]:
    """Detect high-impact open questions."""
    triggers: list[DeepResearchTrigger] = []
    questions = result.get("open_questions", [])
    if not isinstance(questions, list) or not questions:
        return triggers

    # Check if questions overlap with multiple existing pages
    sources_dir = vault / "wiki" / "sources"
    concepts_dir = vault / "wiki" / "concepts"

    for question in questions[:3]:
        if not isinstance(question, str) or not question.strip():
            continue
        terms = re.findall(r"[一-鿿]{2,6}|[A-Za-z0-9\-+]{3,}", question)
        if len(terms) < 2:
            continue

        overlap_count = 0
        for dir_path in (sources_dir, concepts_dir):
            if not dir_path.exists():
                continue
            for md_path in dir_path.glob("*.md"):
                text = md_path.read_text(encoding="utf-8")[:800]
                if sum(1 for t in terms if t in text) >= 2:
                    overlap_count += 1

        if overlap_count >= 3:
            triggers.append(DeepResearchTrigger(
                trigger_type="high_impact_question",
                topic=question[:60],
                reason=f"此问题与 {overlap_count} 个现有页面相关，回答后可更新知识库",
                evidence=[question],
                suggested_hypotheses=[
                    f"假设：{question}",
                    "如果回答这个问题，哪些现有页面需要更新",
                ],
                priority="medium",
            ))

    return triggers


def _detect_gap_triggers(result: dict) -> list[DeepResearchTrigger]:
    """Detect knowledge gap clusters."""
    triggers: list[DeepResearchTrigger] = []
    claims = result.get("claim_inventory", [])
    if not isinstance(claims, list):
        return triggers

    gaps: list[str] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if claim.get("evidence_type") == "gap":
            text = claim.get("claim", "")
            if text:
                gaps.append(text)

    if len(gaps) >= 3:
        triggers.append(DeepResearchTrigger(
            trigger_type="knowledge_gap_cluster",
            topic=gaps[0][:60],
            reason=f"发现 {len(gaps)} 个信息缺口，需要补充研究",
            evidence=gaps[:5],
            suggested_hypotheses=[
                f"这些缺口是否有共同的信息源可以填补",
                f"缺口的核心：{gaps[0][:40]}...",
            ],
            priority="medium",
        ))

    return triggers


def _detect_confidence_cliff_triggers(result: dict, vault: Path) -> list[DeepResearchTrigger]:
    """Detect when new evidence contradicts a previously stable claim."""
    triggers: list[DeepResearchTrigger] = []
    claims = result.get("claim_inventory", [])
    if not isinstance(claims, list):
        return triggers

    _ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}

    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if claim.get("evidence_type") == "disputed":
            confidence = claim.get("confidence", "")
            rank = _ORDINAL_RANK.get(confidence, 0)
            if rank >= 3:  # Supported or Stable being disputed
                triggers.append(DeepResearchTrigger(
                    trigger_type="confidence_cliff",
                    topic=claim.get("claim", "")[:60],
                    reason=f"一个 {confidence} 级别的判断出现争议，需要验证",
                    evidence=[claim.get("claim", "")],
                    suggested_hypotheses=[
                        f"原判断是否仍然成立：{claim.get('claim', '')[:40]}...",
                        "新的反驳证据是否可靠",
                    ],
                    priority="high",
                ))

    return triggers


def format_trigger_suggestions(triggers: list[DeepResearchTrigger]) -> str:
    """Format trigger suggestions as user-readable text."""
    if not triggers:
        return ""

    lines: list[str] = ["", "深度研究建议："]

    high = [t for t in triggers if t.priority == "high"]
    medium = [t for t in triggers if t.priority == "medium"]

    if high:
        lines.append("")
        lines.append("高优先级：")
        for t in high[:3]:
            lines.append(f"  [{t.trigger_type}] {t.topic}")
            lines.append(f"    原因：{t.reason}")
            if t.suggested_hypotheses:
                lines.append(f"    建议假设：{t.suggested_hypotheses[0]}")

    if medium:
        lines.append("")
        lines.append("中优先级：")
        for t in medium[:3]:
            lines.append(f"  [{t.trigger_type}] {t.topic}")
            lines.append(f"    原因：{t.reason}")

    lines.append("")
    lines.append("如需启动深度研究，请指定主题和初始假设。")
    lines.append("")

    return "\n".join(lines)
