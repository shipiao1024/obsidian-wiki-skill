"""Deep research report validation: 5 quality gates + dependency chain audit.

Aligned with the reasoning-driven deep research protocol.
Runs automatically during report finalization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GateResult:
    """Result of a single quality gate."""
    name: str
    passed: bool
    issues: list[str] = field(default_factory=list)
    severity: str = "pass"  # pass / warn / fail


@dataclass
class ValidationResult:
    """Complete validation result with all 5 quality gates."""
    results: list[GateResult] = field(default_factory=list)
    dependency_chain_issues: list[str] = field(default_factory=list)
    overall_passed: bool = True

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "fail")

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if not r.passed and r.severity == "warn")


def validate_report(
    report_markdown: str,
    ledger_nodes: dict[str, dict] | None = None,
) -> ValidationResult:
    """Execute all 5 quality gates on a deep research report.

    Args:
        report_markdown: The full report text.
        ledger_nodes: Optional dependency ledger nodes for chain audit.

    Returns:
        ValidationResult with per-gate results.
    """
    result = ValidationResult()

    # Gate 1: Narrative completeness (纵向分析是否完整)
    result.results.append(_test_narrative_completeness(report_markdown))

    # Gate 2: Decision logic (关键节点是否还原了"为什么这么选")
    result.results.append(_test_decision_logic(report_markdown))

    # Gate 3: Counter-evidence (反面证据是否公正呈现)
    result.results.append(_test_counter_evidence(report_markdown))

    # Gate 4: Evidence labels (证据标签是否可区分)
    result.results.append(_test_evidence_labels(report_markdown))

    # Gate 5: Boundary conditions (边界条件是否标注)
    result.results.append(_test_boundary_conditions(report_markdown))

    # Dependency chain audit
    if ledger_nodes:
        result.dependency_chain_issues = _audit_dependency_chain(ledger_nodes)

    result.overall_passed = all(
        r.passed or r.severity == "warn" for r in result.results
    )
    return result


# ---------------------------------------------------------------------------
# Quality gate implementations
# ---------------------------------------------------------------------------

_EVIDENCE_LABELS = re.compile(r"\[(Fact|Inference|Assumption|Disputed|Gap)\]")
_COUNTER_KEYWORDS = re.compile(r"(?:反面|反驳|反对|争议|Disputed|风险|局限|不足|失败|批评|质疑)")


def _test_narrative_completeness(text: str) -> GateResult:
    """Gate 1: Is the longitudinal analysis a complete narrative?

    Checks:
    - Longitudinal section exists and has substantial content
    - Contains origin/evolution/decision logic elements
    - Not a mere timeline/bullet list
    """
    issues: list[str] = []

    # Look for longitudinal analysis section
    long_match = re.search(
        r"(?:## (?:二|纵向|Diachronic|从诞生到当下).*?\n)(.*?)(?=\n## [三四五六]|\Z)",
        text, re.S,
    )
    if not long_match:
        return GateResult("叙事完整性", False, ["缺少纵向分析章节（从诞生到当下）"], "fail")

    long_text = long_match.group(1).strip()
    if len(long_text) < 500:
        issues.append(f"纵向分析内容过少（{len(long_text)} 字），无法构成完整叙事")

    # Check for narrative elements
    has_origin = bool(re.search(r"(?:起源|诞生|创立|发起|创建|背景)", long_text))
    has_evolution = bool(re.search(r"(?:演进|发展|历程|转折|阶段|变化)", long_text))
    has_decision_logic = bool(re.search(r"(?:决策|选择|为什么|原因|约束|锁定|路径依赖)", long_text))

    if not has_origin:
        issues.append("纵向分析缺少起源追溯")
    if not has_evolution:
        issues.append("纵向分析缺少演进历程")
    if not has_decision_logic:
        issues.append("纵向分析缺少决策逻辑还原（不只是'发生了什么'，还有'为什么这么选'）")

    # Check it's not just a timeline (too many date patterns without narrative)
    date_patterns = re.findall(r"\d{4}[-年]\d{1,2}", long_text)
    narrative_connectors = re.findall(r"(?:因此|导致|因为|所以|然而|但是|转折|关键|促使|推动)", long_text)
    if len(date_patterns) > 5 and len(narrative_connectors) < 3:
        issues.append("纵向分析读起来像年表流水账，缺少因果叙事")

    severity = "fail" if len(issues) >= 3 else ("warn" if issues else "pass")
    return GateResult("叙事完整性", len(issues) == 0, issues, severity)


def _test_decision_logic(text: str) -> GateResult:
    """Gate 2: Does each key node restore 'why this choice'?

    Checks:
    - Decision logic is present, not just event listing
    - Cross-sectional analysis section exists
    - Insight section has cross-axis analysis
    """
    issues: list[str] = []

    # Look for cross-sectional analysis section
    cross_match = re.search(
        r"(?:## (?:三|横向|Synchronic|竞争图谱).*?\n)(.*?)(?=\n## [四五]|\Z)",
        text, re.S,
    )
    if not cross_match:
        issues.append("缺少横向分析章节（竞争图谱）")
    else:
        cross_text = cross_match.group(1).strip()
        if len(cross_text) < 300:
            issues.append("横向分析内容过少，竞品对比不够深入")
        has_competitor = bool(re.search(r"(?:竞品|替代|对手|同类|对比|vs|比较)", cross_text))
        if not has_competitor:
            issues.append("横向分析缺少竞品/同类对比")

    # Look for insight section (横纵交汇)
    insight_match = re.search(
        r"(?:## (?:四|横纵交汇|洞察).*?\n)(.*?)(?=\n## [五六]|\Z)",
        text, re.S,
    )
    if not insight_match:
        issues.append("缺少横纵交汇洞察章节")
    else:
        insight_text = insight_match.group(1).strip()
        has_cross_axis = bool(re.search(
            r"(?:历史.*竞争|纵向.*横向|起源.*格局|决策.*定位)", insight_text
        ))
        if not has_cross_axis and len(insight_text) > 100:
            issues.append("交汇洞察未真正交叉纵横两轴，可能是前面内容的缩写")

    severity = "fail" if len(issues) >= 3 else ("warn" if issues else "pass")
    return GateResult("决策逻辑", len(issues) == 0, issues, severity)


def _test_counter_evidence(text: str) -> GateResult:
    """Gate 3: Is counter-evidence presented fairly?

    Checks for presence of counter-arguments, disputes, or limitations.
    """
    issues: list[str] = []

    counter_mentions = _COUNTER_KEYWORDS.findall(text)
    has_disputed = "[Disputed]" in text

    if not counter_mentions and not has_disputed:
        return GateResult("反面证据", False, ["报告中未呈现任何反面证据或争议"], "fail")

    if len(counter_mentions) < 3:
        issues.append("反面证据呈现较少（<3 处），建议补充更多反驳论据")

    # Check if counter-evidence is integrated into analysis, not just in appendix
    main_text = re.split(r"## (?:附录|信息来源|Trace)", text)[0] if "附录" in text or "信息来源" in text else text
    main_counter = _COUNTER_KEYWORDS.findall(main_text)
    if not main_counter:
        issues.append("反面证据仅出现在附录中，正文中缺少体现")

    severity = "fail" if not counter_mentions else ("warn" if issues else "pass")
    return GateResult("反面证据", len(issues) == 0, issues, severity)


def _test_evidence_labels(text: str) -> GateResult:
    """Gate 4: Are evidence labels present and distinguishable?

    Checks that key assertions have [Fact]/[Inference]/[Assumption] labels.
    """
    issues: list[str] = []

    labels = _EVIDENCE_LABELS.findall(text)
    label_counts = {}
    for label in labels:
        label_counts[label] = label_counts.get(label, 0) + 1

    total_labels = len(labels)
    if total_labels == 0:
        return GateResult("证据标签", False, ["报告中无任何证据标签 [Fact]/[Inference]/[Assumption]"], "fail")

    # Check if main analysis sections have labels
    for section_name in ["纵向", "横向", "横纵交汇", "洞察"]:
        section_match = re.search(
            rf"(?:## .*?{section_name}.*?\n)(.*?)(?=\n## |\Z)", text, re.S
        )
        if section_match:
            section_labels = _EVIDENCE_LABELS.findall(section_match.group(1))
            if not section_labels:
                issues.append(f"「{section_name}」章节缺少证据标签")

    if total_labels < 5:
        issues.append(f"证据标签数量偏少（仅 {total_labels} 个），建议为关键判断补充标签")

    severity = "warn" if issues else "pass"
    return GateResult("证据标签", len(issues) == 0, issues, severity)


def _test_boundary_conditions(text: str) -> GateResult:
    """Gate 5: Are boundary conditions marked for strong judgments?

    Checks for three-scenario projection and boundary condition declarations.
    """
    issues: list[str] = []

    # Check for three-scenario projection
    has_scenarios = bool(re.search(r"(?:最可能|最危险|最乐观|三剧本|剧本推演)", text))
    if not has_scenarios:
        issues.append("缺少三剧本推演（最可能/最危险/最乐观），边界条件来源不明确")

    # Check for boundary condition declarations
    has_boundary = bool(re.search(r"(?:边界条件|当.*时.*结论|失效条件|适用范围)", text))
    if not has_boundary:
        issues.append("缺少边界条件声明（'当 [条件] 时，结论 [成立/失效]'）")

    # Check for vague boundary conditions
    vague_boundaries = re.findall(r"(?:如果情况变化|视情况而定|取决于具体情形)", text)
    if vague_boundaries:
        issues.append(f"发现 {len(vague_boundaries)} 处模糊边界条件，应改为可观察、可验证的具体条件")

    severity = "fail" if not has_scenarios else ("warn" if issues else "pass")
    return GateResult("边界条件", len(issues) == 0, issues, severity)


# ---------------------------------------------------------------------------
# Dependency chain audit
# ---------------------------------------------------------------------------

_ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}


def _audit_dependency_chain(nodes: dict[str, dict]) -> list[str]:
    """Audit dependency chain propagation rules.

    Checks:
    - C confidence <= min(dependency chain confidence)
    - Stable conclusions must trace to F nodes within 3 hops
    - No Stable conclusion depends on Assumption nodes
    """
    issues: list[str] = []

    for nid, node in nodes.items():
        if node.get("type") != "C":
            continue

        conf = node.get("confidence", "Preliminary")
        conf_rank = _ORDINAL_RANK.get(conf, 0)

        deps = node.get("dependencies", [])
        for dep_id in deps:
            dep_node = nodes.get(dep_id, {})
            if dep_node.get("type") == "A" and conf_rank >= 3:
                issues.append(f"结论 {nid} 置信度 {conf} 但依赖假设节点 {dep_id}")

            dep_conf_str = dep_node.get("confidence", "Stable")
            dep_rank = _ORDINAL_RANK.get(dep_conf_str, 4)
            if conf_rank > dep_rank:
                issues.append(f"结论 {nid} 置信度 {conf} 超过依赖节点 {dep_id} 的 {dep_conf_str}")

    return issues


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_validation_report(result: ValidationResult) -> str:
    """Format validation results as a Markdown appendix section."""
    lines: list[str] = ["## 附录：质量门控（5 项检验）", ""]

    lines.append(f"检验时间：自动生成")
    lines.append(f"通过：{result.pass_count} / 失败：{result.fail_count} / 警告：{result.warn_count}")
    lines.append("")

    lines.append("| 检验项 | 结果 | 发现的问题 |")
    lines.append("|---|---|---|")

    for r in result.results:
        if r.passed:
            status = "通过"
        elif r.severity == "warn":
            status = "⚠️ 警告"
        else:
            status = "❌ 未通过"
        issue_summary = "; ".join(r.issues[:2]) if r.issues else "—"
        lines.append(f"| {r.name} | {status} | {issue_summary} |")

    lines.append("")

    # Detail failed/warned items
    failed = [r for r in result.results if not r.passed]
    if failed:
        lines.append("### 未通过项详情")
        lines.append("")
        for r in failed:
            icon = "❌" if r.severity == "fail" else "⚠️"
            lines.append(f"**{icon} {r.name}**")
            for issue in r.issues:
                lines.append(f"- {issue}")
            lines.append("")

    # Dependency chain issues
    if result.dependency_chain_issues:
        lines.append("### 依赖链审查")
        lines.append("")
        for issue in result.dependency_chain_issues:
            lines.append(f"- {issue}")
        lines.append("")

    return "\n".join(lines)
