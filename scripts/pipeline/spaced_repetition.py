"""FSRS-6 lite: spaced repetition for knowledge cards.

A simplified FSRS (Free Spaced Repetition Scheduler) implementation
for reviewing atomic cards in the wiki.

Each card has:
  - stability: how long the memory lasts (in days)
  - difficulty: how hard the card is (0-1)
  - elapsed_days: days since last review
  - scheduled_days: days until next review
  - reps: number of reviews
  - lapses: number of times forgotten
  - state: New / Learning / Review / Relearning

Rating scale:
  1 = Again (forgotten)
  2 = Hard
  3 = Good
  4 = Easy

Usage:
    scheduler = SpacedRepetitionScheduler()
    card_state = scheduler.new_card("card-id-1")
    # After review:
    card_state = scheduler.review(card_state, rating=3)  # Good
    # card_state.scheduled_days tells when to review next
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class CardState(str, Enum):
    NEW = "New"
    LEARNING = "Learning"
    REVIEW = "Review"
    RELEARNING = "Relearning"


class Rating(int, Enum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


@dataclass
class SRSCard:
    card_id: str
    state: CardState = CardState.NEW
    stability: float = 0.0
    difficulty: float = 0.3
    elapsed_days: int = 0
    scheduled_days: int = 0
    reps: int = 0
    lapses: int = 0
    last_review: str = ""
    next_review: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SRSCard":
        return cls(
            card_id=data.get("card_id", ""),
            state=CardState(data.get("state", "New")),
            stability=data.get("stability", 0.0),
            difficulty=data.get("difficulty", 0.3),
            elapsed_days=data.get("elapsed_days", 0),
            scheduled_days=data.get("scheduled_days", 0),
            reps=data.get("reps", 0),
            lapses=data.get("lapses", 0),
            last_review=data.get("last_review", ""),
            next_review=data.get("next_review", ""),
        )


# FSRS-6 parameters (default values)
_W = [
    0.40255, 1.18385, 3.12626, 15.4722, 7.2102,
    0.53163, 1.0651, 0.02354, 1.6160, 0.1544,
    1.0824, 1.9813, 0.0953, 0.2975, 2.2042,
    0.2407, 2.9466, 0.5034, 0.6567,
]

DECAY = -0.5
FACTOR = 19.0 / 81.0 + 0.85  # ≈ 1.1346


def _stability_after_success(s: float, r: float, d: float, rating: Rating) -> float:
    """Calculate new stability after a successful review."""
    hard_penalty = _W[15] if rating == Rating.HARD else 1.0
    easy_bonus = _W[16] if rating == Rating.EASY else 1.0
    return s * (1 + math.exp(_W[8]) *
                (11 - d) *
                math.pow(s, -_W[9]) *
                (math.exp(0.05 * (1 - r)) - 1) *
                hard_penalty * easy_bonus)


def _stability_after_failure(s: float, r: float, d: float) -> float:
    """Calculate new stability after forgetting."""
    return min(_W[11] * math.pow(d, -_W[12]) * math.pow(s + 1, _W[13]) * math.exp(_W[14] * (1 - r)) - 1, s * math.exp(_W[17]))


def _difficulty_weight(rating: Rating) -> float:
    return 3.0 - rating.value


def _mean_reversion(init: float, current: float) -> float:
    return _W[7] * init + (1 - _W[7]) * current


class SpacedRepetitionScheduler:
    """FSRS-6 lite scheduler for knowledge cards."""

    def __init__(self, state_path: Path | None = None):
        self.state_path = state_path
        self.cards: dict[str, SRSCard] = {}
        if state_path and state_path.exists():
            self._load()

    def new_card(self, card_id: str) -> SRSCard:
        """Create a new card state."""
        if card_id in self.cards:
            return self.cards[card_id]
        card = SRSCard(card_id=card_id)
        self.cards[card_id] = card
        return card

    def review(self, card: SRSCard, rating: int | Rating) -> SRSCard:
        """Process a review and return updated card state."""
        if isinstance(rating, int):
            rating = Rating(rating)

        now = datetime.now()
        card.last_review = now.isoformat()

        if card.state == CardState.NEW:
            card = self._new_review(card, rating, now)
        elif card.state == CardState.LEARNING:
            card = self._learning_review(card, rating, now)
        elif card.state == CardState.REVIEW:
            card = self._review_review(card, rating, now)
        elif card.state == CardState.RELEARNING:
            card = self._relearning_review(card, rating, now)

        card.next_review = (now + timedelta(days=card.scheduled_days)).isoformat()
        self.cards[card.card_id] = card
        return card

    def get_due_cards(self) -> list[SRSCard]:
        """Get all cards due for review."""
        now = datetime.now()
        due = []
        for card in self.cards.values():
            if card.state == CardState.NEW:
                due.append(card)
            elif card.next_review:
                try:
                    next_dt = datetime.fromisoformat(card.next_review)
                    if next_dt <= now:
                        due.append(card)
                except ValueError:
                    due.append(card)
        return due

    def _new_review(self, card: SRSCard, rating: Rating, now: datetime) -> SRSCard:
        card.reps += 1
        if rating == Rating.AGAIN:
            card.state = CardState.LEARNING
            card.scheduled_days = 0
            card.stability = 0.0
        elif rating == Rating.HARD:
            card.state = CardState.LEARNING
            card.scheduled_days = 1
            card.stability = _W[0]
        elif rating == Rating.GOOD:
            card.state = CardState.LEARNING
            card.scheduled_days = 1
            card.stability = _W[0]
        elif rating == Rating.EASY:
            card.state = CardState.REVIEW
            card.scheduled_days = max(1, round(_W[1]))
            card.stability = _W[1]
        return card

    def _learning_review(self, card: SRSCard, rating: Rating, now: datetime) -> SRSCard:
        card.reps += 1
        if rating == Rating.AGAIN:
            card.scheduled_days = 0
            card.lapses += 1
        elif rating == Rating.HARD:
            card.scheduled_days = 1
        elif rating == Rating.GOOD:
            card.state = CardState.REVIEW
            card.scheduled_days = max(1, round(_W[2]))
            card.stability = _W[2]
        elif rating == Rating.EASY:
            card.state = CardState.REVIEW
            card.scheduled_days = max(1, round(_W[3]))
            card.stability = _W[3]
        return card

    def _review_review(self, card: SRSCard, rating: Rating, now: datetime) -> SRSCard:
        card.reps += 1
        if rating == Rating.AGAIN:
            card.state = CardState.RELEARNING
            card.lapses += 1
            card.stability = _stability_after_failure(card.stability, 0.0, card.difficulty)
            card.scheduled_days = 0
            card.difficulty = _mean_reversion(0.3, card.difficulty + _difficulty_weight(rating) * 0.1)
            return card

        # Successful review
        card.stability = _stability_after_success(card.stability, 0.0, card.difficulty, rating)
        card.difficulty = max(0.0, min(1.0, card.difficulty + _difficulty_weight(rating) * 0.1))
        card.difficulty = _mean_reversion(0.3, card.difficulty)
        card.scheduled_days = max(1, round(FACTOR * card.stability))
        return card

    def _relearning_review(self, card: SRSCard, rating: Rating, now: datetime) -> SRSCard:
        card.reps += 1
        if rating == Rating.AGAIN:
            card.scheduled_days = 0
        elif rating == Rating.HARD:
            card.scheduled_days = 1
        elif rating == Rating.GOOD:
            card.state = CardState.REVIEW
            card.scheduled_days = max(1, round(FACTOR * card.stability))
        elif rating == Rating.EASY:
            card.state = CardState.REVIEW
            card.stability = _stability_after_success(card.stability, 0.0, card.difficulty, rating)
            card.scheduled_days = max(1, round(FACTOR * card.stability))
        return card

    def _load(self) -> None:
        if not self.state_path or not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            for card_data in data.get("cards", []):
                card = SRSCard.from_dict(card_data)
                self.cards[card.card_id] = card
        except (json.JSONDecodeError, OSError):
            pass

    def save(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "cards": [card.to_dict() for card in self.cards.values()],
        }
        self.state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def format_review_session(self, due_cards: list[SRSCard] | None = None) -> str:
        """Format a review session as user-readable text."""
        if due_cards is None:
            due_cards = self.get_due_cards()

        if not due_cards:
            return "没有待复习的卡片。"

        lines: list[str] = [f"待复习卡片：{len(due_cards)} 张", ""]

        new = [c for c in due_cards if c.state == CardState.NEW]
        learning = [c for c in due_cards if c.state in (CardState.LEARNING, CardState.RELEARNING)]
        review = [c for c in due_cards if c.state == CardState.REVIEW]

        if new:
            lines.append(f"新卡片：{len(new)} 张")
            for card in new[:5]:
                lines.append(f"  - {card.card_id}")
            lines.append("")

        if learning:
            lines.append(f"学习中：{len(learning)} 张")
            for card in learning[:5]:
                lines.append(f"  - {card.card_id} (lapses: {card.lapses})")
            lines.append("")

        if review:
            lines.append(f"复习：{len(review)} 张")
            for card in review[:5]:
                lines.append(f"  - {card.card_id} (stability: {card.stability:.1f}d)")
            lines.append("")

        return "\n".join(lines)
