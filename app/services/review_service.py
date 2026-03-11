"""Spaced Repetition Service using SM-2 algorithm."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class ReviewMetrics:
    interval: int
    ease_factor: float
    repetitions: int
    next_review_at: datetime


def calculate_next_review(
    confidence: int,
    current_interval: int = 1,
    current_ease_factor: float = 2.5,
    current_repetitions: int = 0,
) -> ReviewMetrics:
    """
    Calculate next review schedule using SM-2 algorithm.

    Args:
        confidence: User rating 1-5 (1=complete blackout, 5=perfect recall)
        current_interval: Current review interval in days
        current_ease_factor: Current ease factor (min 1.3)
        current_repetitions: Number of successful reviews so far

    Returns:
        ReviewMetrics with updated schedule
    """
    # SM-2 uses 0-5 quality scale; our UI uses 1-5
    quality = confidence - 1  # Map 1-5 → 0-4

    if quality < 2:
        # Failed recall: reset repetitions, short interval
        new_repetitions = 0
        new_interval = 1
    else:
        # Successful recall: advance schedule
        if current_repetitions == 0:
            new_interval = 1
        elif current_repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(current_interval * current_ease_factor)
        new_repetitions = current_repetitions + 1

    # Update ease factor: formula from SM-2
    ef = current_ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease_factor = max(1.3, round(ef, 4))

    next_review_at = datetime.utcnow() + timedelta(days=new_interval)

    return ReviewMetrics(
        interval=new_interval,
        ease_factor=new_ease_factor,
        repetitions=new_repetitions,
        next_review_at=next_review_at,
    )
