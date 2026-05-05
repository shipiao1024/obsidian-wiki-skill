"""Risk-graded approval model for wiki operations.

Classifies write operations into three risk tiers:
  - Low:   AI autonomous (create candidates, link existing, add to graph)
  - Medium: Show don't block (promote pages, update synthesis, modify stances)
  - High:  Must confirm before write (delete/merge, modify stable, change domains)

Usage:
    risk = classify_operation("create_candidate", target_lifecycle="candidate")
    # risk.tier == "low" → auto-execute
    # risk.tier == "medium" → execute + show diff
    # risk.tier == "high" → block until user confirms
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RiskAssessment:
    tier: RiskTier
    reason: str
    auto_execute: bool = False
    show_diff: bool = False
    requires_confirmation: bool = False
    suggested_action: str = ""

    def __post_init__(self) -> None:
        if self.tier == RiskTier.LOW:
            self.auto_execute = True
            self.show_diff = False
            self.requires_confirmation = False
        elif self.tier == RiskTier.MEDIUM:
            self.auto_execute = False
            self.show_diff = True
            self.requires_confirmation = False
        else:  # HIGH
            self.auto_execute = False
            self.show_diff = True
            self.requires_confirmation = True


# --- Operation classification rules ---

# Low risk: creating new things that don't affect existing content
_LOW_OPERATIONS = {
    "create_candidate",
    "create_candidate_domain",
    "create_candidate_concept",
    "create_candidate_entity",
    "link_existing",
    "add_to_graph",
    "create_question",
    "create_delta_proposal",
    "create_synthesis_stub",
}

# Medium risk: modifying existing content but with recoverable changes
_MEDIUM_OPERATIONS = {
    "promote_to_official",
    "update_synthesis",
    "update_brief",
    "update_source",
    "modify_stance",
    "add_evidence_to_claim",
    "update_confidence",
    "merge_into_synthesis",
    "append_links_section",
}

# High risk: destructive or high-commitment changes
_HIGH_OPERATIONS = {
    "delete_page",
    "merge_pages",
    "modify_stable_page",
    "change_domain_assignment",
    "demote_lifecycle",
    "overwrite_brief",
    "overwrite_source",
    "bulk_update",
}


def classify_operation(
    operation: str,
    *,
    target_lifecycle: str = "",
    target_confidence: str = "",
    affects_stable: bool = False,
) -> RiskAssessment:
    """Classify a write operation by risk tier.

    Args:
        operation: The operation name (e.g., "create_candidate", "promote_to_official")
        target_lifecycle: Lifecycle of the target page (candidate, official, stable)
        target_confidence: Confidence level of the target content
        affects_stable: Whether this operation modifies a stable page

    Returns:
        RiskAssessment with tier and recommended behavior
    """
    # Check high-risk first
    if operation in _HIGH_OPERATIONS or affects_stable:
        return RiskAssessment(
            tier=RiskTier.HIGH,
            reason=_high_risk_reason(operation, target_lifecycle, affects_stable),
            suggested_action="请确认是否执行此操作。",
        )

    # Promotion from candidate to official is medium risk
    if operation in _MEDIUM_OPERATIONS:
        return RiskAssessment(
            tier=RiskTier.MEDIUM,
            reason=_medium_risk_reason(operation, target_lifecycle),
            suggested_action="已展示变更预览，确认后自动应用。",
        )

    # Low risk: new content creation
    if operation in _LOW_OPERATIONS:
        return RiskAssessment(
            tier=RiskTier.LOW,
            reason="创建新内容，不影响已有页面。",
        )

    # Unknown operations default to medium risk
    return RiskAssessment(
        tier=RiskTier.MEDIUM,
        reason=f"未识别的操作类型 '{operation}'，默认中等风险。",
        suggested_action="请确认操作。",
    )


def _high_risk_reason(operation: str, lifecycle: str, affects_stable: bool) -> str:
    if affects_stable:
        return "此操作将修改 stable 状态的页面，需要人工确认。"
    reasons = {
        "delete_page": "删除页面是不可逆操作。",
        "merge_pages": "合并页面会修改多个已有页面。",
        "modify_stable_page": "stable 页面已验证，修改需要确认。",
        "change_domain_assignment": "修改域归属会影响知识图谱结构。",
        "demote_lifecycle": "降低生命周期状态需要确认。",
        "overwrite_brief": "覆盖 brief 页面会丢失已有内容。",
        "overwrite_source": "覆盖 source 页面会丢失已有内容。",
        "bulk_update": "批量更新影响范围大。",
    }
    return reasons.get(operation, "高风险操作需要人工确认。")


def _medium_risk_reason(operation: str, lifecycle: str) -> str:
    reasons = {
        "promote_to_official": "将候选页提升为正式页。",
        "update_synthesis": "更新综合分析页面。",
        "update_brief": "更新 brief 页面内容。",
        "update_source": "更新 source 页面内容。",
        "modify_stance": "修改立场页面。",
        "add_evidence_to_claim": "为已有判断添加新证据。",
        "update_confidence": "更新置信度等级。",
        "merge_into_synthesis": "将内容合并到综合分析。",
        "append_links_section": "向链接区追加新链接。",
    }
    return reasons.get(operation, "中等风险操作，展示变更供确认。")


def classify_compile_proposals(compiled_payload: dict[str, object]) -> list[dict[str, object]]:
    """Classify all proposals from a compile result by risk tier.

    Returns a list of classified operations:
    [
        {
            "operation": "create_candidate",
            "target": "概念名称",
            "kind": "concept",
            "action": "create_candidate",
            "risk": RiskAssessment(...),
        },
        ...
    ]
    """
    result = compiled_payload.get("result") if isinstance(compiled_payload, dict) else {}
    if not isinstance(result, dict):
        return []

    classified: list[dict[str, object]] = []

    # Knowledge proposals
    proposals = result.get("knowledge_proposals", {})
    if isinstance(proposals, dict):
        for kind in ("domains", "concepts", "entities"):
            items = proposals.get(kind, [])
            if not isinstance(items, list):
                continue
            for p in items:
                if not isinstance(p, dict):
                    continue
                name = p.get("name", "")
                action = p.get("action", "")
                confidence = p.get("confidence", "")
                if not name or not action:
                    continue
                risk = classify_operation(
                    action,
                    target_confidence=confidence,
                )
                classified.append({
                    "operation": action,
                    "target": name,
                    "kind": kind.rstrip("s") if kind.endswith("s") else kind,
                    "action": action,
                    "confidence": confidence,
                    "risk": risk,
                })

    # Update proposals
    update_proposals = result.get("update_proposals", [])
    if isinstance(update_proposals, list):
        for up in update_proposals:
            if not isinstance(up, dict):
                continue
            target_page = up.get("target_page", "")
            target_type = up.get("target_type", "")
            action = up.get("action", "draft_delta")
            confidence = up.get("confidence", "")
            if not target_page:
                continue
            # Check if target is stable
            affects_stable = "stable" in str(target_type).lower()
            risk = classify_operation(
                action,
                target_lifecycle=target_type,
                target_confidence=confidence,
                affects_stable=affects_stable,
            )
            classified.append({
                "operation": action,
                "target": target_page,
                "kind": target_type,
                "action": action,
                "confidence": confidence,
                "risk": risk,
            })

    return classified


def filter_auto_executable(classified_ops: list[dict[str, object]]) -> list[dict[str, object]]:
    """Filter operations that can be auto-executed (low risk)."""
    return [op for op in classified_ops if isinstance(op.get("risk"), RiskAssessment) and op["risk"].auto_execute]


def filter_needs_review(classified_ops: list[dict[str, object]]) -> list[dict[str, object]]:
    """Filter operations that need user review (medium + high risk)."""
    return [
        op for op in classified_ops
        if isinstance(op.get("risk"), RiskAssessment) and (op["risk"].show_diff or op["risk"].requires_confirmation)
    ]


def filter_requires_confirmation(classified_ops: list[dict[str, object]]) -> list[dict[str, object]]:
    """Filter operations that require explicit user confirmation (high risk only)."""
    return [
        op for op in classified_ops
        if isinstance(op.get("risk"), RiskAssessment) and op["risk"].requires_confirmation
    ]


def format_risk_summary(classified_ops: list[dict[str, object]]) -> str:
    """Format a human-readable risk summary for all classified operations."""
    low = filter_auto_executable(classified_ops)
    review = filter_needs_review(classified_ops)
    confirm = filter_requires_confirmation(classified_ops)

    lines: list[str] = []

    if low:
        lines.append(f"自动执行（{len(low)} 项）：")
        for op in low[:5]:
            lines.append(f"  [{op.get('kind', '?')}] {op.get('target', '?')} — {op.get('action', '?')}")
        if len(low) > 5:
            lines.append(f"  ... 还有 {len(low) - 5} 项")
        lines.append("")

    if review:
        lines.append(f"待审核（{len(review)} 项）：")
        for op in review[:5]:
            risk = op.get("risk")
            reason = risk.reason if isinstance(risk, RiskAssessment) else ""
            lines.append(f"  [{op.get('kind', '?')}] {op.get('target', '?')} — {reason}")
        lines.append("")

    if confirm:
        lines.append(f"需要确认（{len(confirm)} 项）：")
        for op in confirm[:5]:
            risk = op.get("risk")
            reason = risk.reason if isinstance(risk, RiskAssessment) else ""
            lines.append(f"  [{op.get('kind', '?')}] {op.get('target', '?')} — {reason}")
        lines.append("")

    if not lines:
        lines.append("无需审核的操作。")

    return "\n".join(lines)
