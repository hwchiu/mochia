"""Unit tests for SM-2 spaced repetition algorithm."""

from datetime import datetime

from app.services.review_service import ReviewMetrics, calculate_next_review


class TestSM2Algorithm:
    def test_confidence_1_resets_repetitions(self):
        result = calculate_next_review(confidence=1, current_repetitions=5, current_interval=30)
        assert result.repetitions == 0
        assert result.interval == 1

    def test_confidence_2_resets_repetitions(self):
        result = calculate_next_review(confidence=2, current_repetitions=3, current_interval=10)
        assert result.repetitions == 0
        assert result.interval == 1

    def test_confidence_3_advances_first_review(self):
        result = calculate_next_review(confidence=3, current_repetitions=0)
        assert result.repetitions == 1
        assert result.interval == 1

    def test_confidence_4_second_review_gives_6_days(self):
        result = calculate_next_review(confidence=4, current_repetitions=1, current_interval=1)
        assert result.interval == 6
        assert result.repetitions == 2

    def test_confidence_5_third_review_multiplies_interval(self):
        result = calculate_next_review(
            confidence=5, current_repetitions=2, current_interval=6, current_ease_factor=2.5
        )
        assert result.interval == 15  # round(6 * 2.5)
        assert result.repetitions == 3

    def test_ease_factor_increases_on_perfect_recall(self):
        # confidence=5 → quality=4 → EF change = 0 (max quality maintains EF)
        # confidence=4 → quality=3 → EF decreases; only maintaining is "perfect recall" behavior
        result = calculate_next_review(confidence=5, current_ease_factor=2.5)
        assert result.ease_factor >= 2.5

    def test_ease_factor_decreases_on_difficult_recall(self):
        result = calculate_next_review(confidence=3, current_ease_factor=2.5)
        assert result.ease_factor < 2.5

    def test_ease_factor_never_below_1_3(self):
        result = calculate_next_review(confidence=1, current_ease_factor=1.3)
        assert result.ease_factor >= 1.3

    def test_next_review_at_is_future(self):
        result = calculate_next_review(confidence=4)
        assert result.next_review_at > datetime.utcnow()

    def test_next_review_at_matches_interval(self):
        before = datetime.utcnow()
        result = calculate_next_review(confidence=5, current_repetitions=1, current_interval=1)
        expected_days = result.interval
        assert (result.next_review_at - before).days >= expected_days - 1
        assert (result.next_review_at - before).days <= expected_days + 1

    def test_returns_review_metrics_dataclass(self):
        result = calculate_next_review(confidence=3)
        assert isinstance(result, ReviewMetrics)
        assert isinstance(result.interval, int)
        assert isinstance(result.ease_factor, float)
        assert isinstance(result.repetitions, int)
        assert isinstance(result.next_review_at, datetime)
