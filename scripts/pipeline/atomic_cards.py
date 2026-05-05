"""Atomic card system for structured knowledge capture.

Unified atomic card type — "one card, one idea". Each card is a self-contained
knowledge atom that can be understood independently and used for spaced repetition.

Design philosophy (from knowledge-mgmt-main):
  - Brief/source pages are the "map" (narrative, context, reasoning chain)
  - Atomic cards are the "stones" (independent, memorizable, reviewable)
  - A card must be understandable when read in isolation
  - A card should contain exactly one idea — if it has two, split it

Usage:
    card = create_atomic_card(
        title="刻意练习需要走出舒适区",
        definition="有效的练习必须超出当前能力边界",
        content="...",
        source="wiki/sources/some-article.md",
        evidence_type="fact",
        grounding_quote="原文明确指出...",
    )
    md = render_atomic_card(card)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class AtomicCard:
    """A single knowledge atom for review and retrieval."""
    title: str                  # 陈述句 ≤ 50 字
    definition: str             # 一句话定义 ≤ 30 字
    content: str                # 展开内容 1-3 段
    source: str = ""            # 回链来源 (wiki/sources/slug.md)
    confidence: str = "Preliminary"  # 五级序数置信度
    evidence_type: str = "inference"  # fact/inference/assumption/hypothesis/disputed/gap
    grounding_quote: str = ""   # 原文锚定引用
    key_markers: list[str] = field(default_factory=list)  # 关键术语标记
    tags: list[str] = field(default_factory=list)         # 领域标签
    created_at: str = ""
    card_id: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d")
        if not self.card_id:
            slug = re.sub(r"[^\w一-鿿]+", "-", self.title).strip("-")[:40]
            self.card_id = slug or f"card-{self.created_at}"


def create_atomic_card(
    title: str,
    definition: str = "",
    content: str = "",
    *,
    source: str = "",
    confidence: str = "Preliminary",
    evidence_type: str = "inference",
    grounding_quote: str = "",
    key_markers: list[str] | None = None,
    tags: list[str] | None = None,
) -> AtomicCard:
    """Create an atomic card with validation."""
    if not title.strip():
        raise ValueError("Card title cannot be empty")

    return AtomicCard(
        title=title.strip(),
        definition=definition.strip(),
        content=content.strip(),
        source=source,
        confidence=confidence,
        evidence_type=evidence_type,
        grounding_quote=grounding_quote,
        key_markers=key_markers or [],
        tags=tags or [],
    )


def validate_card(card: AtomicCard) -> tuple[bool, list[str]]:
    """Validate an atomic card."""
    errors: list[str] = []
    if not card.title:
        errors.append("Title is required")
    if len(card.title) > 80:
        errors.append(f"Title too long ({len(card.title)} chars, recommend ≤ 50)")
    if not card.content and not card.definition:
        errors.append("Card must have at least a definition or content")
    return len(errors) == 0, errors


def render_atomic_card(card: AtomicCard) -> str:
    """Render an atomic card as Obsidian-compatible Markdown.

    Template structure (aligned with knowledge-mgmt-main):
      - Frontmatter with type/atomic + metadata
      - H1: 陈述句标题
      - 一句话定义
      - 展开 (1-3 paragraphs)
      - 关键标记 (供 review 生成题目)
      - 原文锚定 (grounding quote)
      - 来源回链
    """
    lines: list[str] = [
        "---",
        f'title: "{card.title}"',
        "type: atomic",
        f'confidence: "{card.confidence}"',
        f'evidence_type: "{card.evidence_type}"',
        f'source: "{card.source}"',
        f'date: "{card.created_at}"',
    ]
    if card.tags:
        tags_str = ", ".join(f'"{t}"' for t in card.tags)
        lines.append(f"tags: [{tags_str}]")
    lines.extend(["---", ""])
    lines.append(f"# {card.title}")
    lines.append("")

    # 一句话定义
    if card.definition:
        lines.append(f"> {card.definition}")
        lines.append("")

    # 展开内容
    if card.content:
        lines.append(card.content)
        lines.append("")

    # 关键标记
    if card.key_markers:
        lines.append("## 关键标记")
        lines.append("")
        for marker in card.key_markers:
            lines.append(f"- {marker}")
        lines.append("")

    # 原文锚定
    if card.grounding_quote:
        lines.append("## 原文锚定")
        lines.append("")
        lines.append(f"> {card.grounding_quote}")
        lines.append("")

    # 来源
    if card.source:
        lines.append(f"**来源**：[[{card.source.replace('wiki/sources/', '').replace('.md', '')}]]")
        lines.append("")

    return "\n".join(lines)


def render_cards_for_obsidian(cards: list[AtomicCard], output_dir: Path) -> list[Path]:
    """Render multiple cards to individual Markdown files in an Obsidian vault."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for card in cards:
        md = render_atomic_card(card)
        path = output_dir / f"{card.card_id}.md"
        path.write_text(md, encoding="utf-8")
        paths.append(path)
    return paths


# --- Smart extraction from compile results ---

# Confidence thresholds for card-worthiness
_ORDINAL_RANK = {"Seeded": 0, "Preliminary": 1, "Working": 2, "Supported": 3, "Stable": 4}
_MIN_CONFIDENCE_FOR_CARD = 2  # Working or above


def _confidence_rank(conf: str) -> int:
    return _ORDINAL_RANK.get(str(conf).strip(), -1)


def extract_cards_from_compile(
    compiled_payload: dict[str, object],
    source_slug: str = "",
    max_cards: int = 10,
) -> list[AtomicCard]:
    """Extract the most valuable knowledge atoms from a compile result.

    Philosophy: not everything needs a card. We select the top N most
    valuable items — cross-domain insights first, then high-confidence
    claims, then key concepts. This avoids knowledge graph pollution
    and respects "one card, one idea".

    Priority order:
      1. Cross-domain insights (highest signal — bridge between domains)
      2. High-confidence claims (Supported/Stable — established facts)
      3. Key concepts with ≥ Working confidence
      4. Core mechanisms (generators from skeleton)
    """
    cards: list[AtomicCard] = []
    result = compiled_payload.get("result") if isinstance(compiled_payload, dict) else {}
    if not isinstance(result, dict):
        return cards

    source_ref = f"wiki/sources/{source_slug}.md" if source_slug else ""

    # --- Priority 1: Cross-domain insights (always extract, highest signal) ---
    for insight in result.get("cross_domain_insights", []):
        if not isinstance(insight, dict):
            continue
        concept = insight.get("mapped_concept", "")
        domain = insight.get("target_domain", "")
        logic = insight.get("bridge_logic", "")
        if not concept or not logic:
            continue
        cards.append(create_atomic_card(
            title=f"{concept} → {domain}",
            definition=logic[:60] if len(logic) > 60 else logic,
            content=logic,
            source=source_ref,
            confidence=insight.get("confidence", "Preliminary"),
            evidence_type="inference",
            key_markers=[f"**{concept}** ↔ {domain}"],
            tags=["cross-domain"],
        ))

    # --- Priority 2: High-confidence claims (Working+) ---
    claim_inventory = result.get("claim_inventory", [])
    if isinstance(claim_inventory, list):
        ranked_claims = [
            c for c in claim_inventory
            if isinstance(c, dict) and _confidence_rank(c.get("confidence", "")) >= _MIN_CONFIDENCE_FOR_CARD
        ]
        # Sort by confidence descending, take top 5
        ranked_claims.sort(key=lambda c: _confidence_rank(c.get("confidence", "")), reverse=True)
        for claim in ranked_claims[:5]:
            text = str(claim.get("claim", "")).strip()
            if not text:
                continue
            title = text[:50] + ("..." if len(text) > 50 else "")
            cards.append(create_atomic_card(
                title=title,
                definition=text[:30] + ("..." if len(text) > 30 else ""),
                content=text,
                source=source_ref,
                confidence=claim.get("confidence", "Preliminary"),
                evidence_type=claim.get("evidence_type", "inference"),
                grounding_quote=claim.get("grounding_quote", ""),
            ))

    # --- Priority 3: Key concepts (Working+) ---
    proposals = result.get("knowledge_proposals", {})
    if isinstance(proposals, dict):
        for p in proposals.get("concepts", []):
            if not isinstance(p, dict):
                continue
            name = p.get("name", "")
            action = p.get("action", "")
            conf = p.get("confidence", "")
            if not name or action == "no_page" or _confidence_rank(conf) < _MIN_CONFIDENCE_FOR_CARD:
                continue
            cards.append(create_atomic_card(
                title=name,
                definition=str(p.get("reason", ""))[:60],
                content=str(p.get("reason", "")),
                source=source_ref,
                confidence=conf,
                evidence_type=p.get("evidence_type", "inference"),
                grounding_quote=p.get("grounding_quote", ""),
                key_markers=[f"**{name}**"],
                tags=["concept"],
            ))

    # --- Priority 4: Core mechanisms (generators) ---
    brief = result.get("document_outputs", {})
    if isinstance(brief, dict):
        skeleton = brief.get("brief", {})
        if isinstance(skeleton, dict):
            skeleton_data = skeleton.get("skeleton", {})
            if isinstance(skeleton_data, dict):
                for gen in skeleton_data.get("generators", [])[:3]:
                    if not isinstance(gen, dict):
                        continue
                    name = gen.get("name", "")
                    narrative = gen.get("narrative", "")
                    if not name:
                        continue
                    cards.append(create_atomic_card(
                        title=name,
                        definition=narrative[:60] if narrative else "",
                        content=narrative,
                        source=source_ref,
                        key_markers=[f"**{name}**"],
                        tags=["mechanism"],
                    ))

    # Deduplicate by title, keep first occurrence (highest priority)
    seen_titles: set[str] = set()
    unique_cards: list[AtomicCard] = []
    for card in cards:
        normalized = card.title.strip().lower()
        if normalized not in seen_titles:
            seen_titles.add(normalized)
            unique_cards.append(card)

    return unique_cards[:max_cards]
