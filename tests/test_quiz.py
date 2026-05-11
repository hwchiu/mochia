"""
Tests for the Quiz API system:
  GET  /api/quiz/{video_id}
  POST /api/quiz/{video_id}/generate
  POST /api/quiz/attempt
  GET  /api/quiz/wrong-answers/list
  GET  /api/quiz/stats/overview
  GET  /api/stats/heatmap
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from app.database import Quiz, QuizAttempt, QuizItem, Transcript, Video

# ─── Local helper fixtures ────────────────────────────────────────────────────


@pytest.fixture
def video_with_transcript(db_session) -> Video:
    """Completed video that has a transcript (needed for quiz generation)."""
    vid_id = uuid.uuid4().hex
    video = Video(
        id=vid_id,
        filename="quiz_test.mp4",
        original_filename="quiz_test.mp4",
        file_path=f"/fake/path/quiz_test_{vid_id}.mp4",
        source="local_scan",
        file_size=5 * 1024 * 1024,
        duration=120.0,
        status="completed",
    )
    transcript = Transcript(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        content="占星學的基礎知識包含十二星座和行星運行。牡羊座是火象星座之首。",
    )
    db_session.add(video)
    db_session.add(transcript)
    db_session.commit()
    db_session.refresh(video)
    return video


@pytest.fixture
def video_without_transcript(db_session) -> Video:
    """Completed video with NO transcript."""
    vid_id = uuid.uuid4().hex
    video = Video(
        id=vid_id,
        filename="no_transcript.mp4",
        original_filename="no_transcript.mp4",
        file_path=f"/fake/path/no_transcript_{vid_id}.mp4",
        source="local_scan",
        file_size=2 * 1024 * 1024,
        duration=60.0,
        status="completed",
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


def _make_quiz_with_items(
    db_session, video_id: str, num_items: int = 3
) -> tuple[Quiz, list[QuizItem]]:
    """Create a Quiz and QuizItems directly in the test DB."""
    quiz_id = uuid.uuid4().hex
    now = datetime.utcnow()
    quiz = Quiz(
        id=quiz_id,
        video_id=video_id,
        total_items=num_items,
        created_at=now,
        updated_at=now,
    )
    db_session.add(quiz)
    db_session.flush()

    all_items: list[QuizItem] = [
        # MCQ
        QuizItem(
            id=uuid.uuid4().hex,
            quiz_id=quiz_id,
            video_id=video_id,
            question_type="mcq",
            question="哪個星座是火象星座？",
            options=json.dumps(
                ["A. 牡羊座", "B. 金牛座", "C. 雙子座", "D. 巨蟹座"],
                ensure_ascii=False,
            ),
            answer="A. 牡羊座",
            explanation="牡羊座是第一個火象星座",
            concept_name="星座分類",
            source_seg_idx=0,
            source_start_sec=10.0,
            source_end_sec=30.0,
            created_at=now,
        ),
        # True/False
        QuizItem(
            id=uuid.uuid4().hex,
            quiz_id=quiz_id,
            video_id=video_id,
            question_type="truefalse",
            question="太陽是行星嗎？",
            options=None,
            answer="False",
            explanation="太陽是恆星，不是行星",
            created_at=now,
        ),
        # Fill blank
        QuizItem(
            id=uuid.uuid4().hex,
            quiz_id=quiz_id,
            video_id=video_id,
            question_type="fillblank",
            question="占星學共有___個星座",
            options=None,
            answer="十二",
            explanation=None,
            created_at=now,
        ),
    ]

    items = all_items[:num_items]
    for item in items:
        db_session.add(item)

    db_session.commit()
    return quiz, items


@pytest.fixture
def quiz_with_items(db_session, video_with_transcript) -> tuple[Video, Quiz, list[QuizItem]]:
    """A Video with transcript + its Quiz + 3 QuizItems."""
    quiz, items = _make_quiz_with_items(db_session, video_with_transcript.id)
    return video_with_transcript, quiz, items


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/quiz/{video_id}
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetQuiz:
    def test_empty_when_no_quiz_exists(self, client, video_with_transcript):
        r = client.get(f"/api/quiz/{video_with_transcript.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["video_id"] == video_with_transcript.id
        assert data["total_items"] == 0
        assert data["items"] == []

    def test_graceful_empty_for_nonexistent_video(self, client):
        r = client.get("/api/quiz/nonexistent_video_id_xyz")
        assert r.status_code == 200
        data = r.json()
        assert data["total_items"] == 0
        assert data["items"] == []

    def test_returns_items_when_quiz_exists(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        r = client.get(f"/api/quiz/{video.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["video_id"] == video.id
        assert data["total_items"] == quiz.total_items
        assert len(data["items"]) == len(items)

    def test_item_has_required_fields(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        r = client.get(f"/api/quiz/{video.id}")
        item = r.json()["items"][0]
        for field in ["id", "question_type", "question", "answer"]:
            assert field in item, f"Missing field: {field}"

    def test_mcq_item_options_is_list(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        r = client.get(f"/api/quiz/{video.id}")
        mcq_items = [i for i in r.json()["items"] if i["question_type"] == "mcq"]
        assert len(mcq_items) > 0
        assert isinstance(mcq_items[0]["options"], list)
        assert len(mcq_items[0]["options"]) == 4

    def test_truefalse_item_options_is_null(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        r = client.get(f"/api/quiz/{video.id}")
        tf_items = [i for i in r.json()["items"] if i["question_type"] == "truefalse"]
        assert len(tf_items) > 0
        assert tf_items[0]["options"] is None

    def test_item_source_timing_fields_present(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        r = client.get(f"/api/quiz/{video.id}")
        mcq = next(i for i in r.json()["items"] if i["question_type"] == "mcq")
        assert mcq["source_seg_idx"] == 0
        assert mcq["source_start_sec"] == 10.0
        assert mcq["source_end_sec"] == 30.0

    def test_item_explanation_and_concept_name(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        r = client.get(f"/api/quiz/{video.id}")
        mcq = next(i for i in r.json()["items"] if i["question_type"] == "mcq")
        assert mcq["explanation"] == "牡羊座是第一個火象星座"
        assert mcq["concept_name"] == "星座分類"


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/quiz/{video_id}/generate
# ═══════════════════════════════════════════════════════════════════════════════


class TestGenerateQuiz:
    def test_404_for_nonexistent_video(self, client):
        r = client.post("/api/quiz/nonexistent_video_xyz/generate")
        assert r.status_code == 404

    def test_400_when_video_has_no_transcript(self, client, video_without_transcript):
        r = client.post(f"/api/quiz/{video_without_transcript.id}/generate")
        assert r.status_code == 400

    def test_200_with_generating_status(self, client, video_with_transcript):
        r = client.post(f"/api/quiz/{video_with_transcript.id}/generate")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "generating"
        assert data["video_id"] == video_with_transcript.id
        assert "message" in data

    def test_generate_returns_video_id_in_response(self, client, video_with_transcript):
        r = client.post(f"/api/quiz/{video_with_transcript.id}/generate")
        assert r.json()["video_id"] == video_with_transcript.id


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/quiz/attempt
# ═══════════════════════════════════════════════════════════════════════════════


class TestSubmitAttempt:
    def test_404_for_nonexistent_item(self, client):
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": "does_not_exist", "user_answer": "A"},
        )
        assert r.status_code == 404

    def test_exact_correct_answer(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        tf = next(i for i in items if i.question_type == "truefalse")
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": tf.id, "user_answer": tf.answer},
        )
        assert r.status_code == 200
        assert r.json()["is_correct"] is True

    def test_wrong_answer_is_false(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        tf = next(i for i in items if i.question_type == "truefalse")
        wrong = "True" if tf.answer == "False" else "False"
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": tf.id, "user_answer": wrong},
        )
        assert r.status_code == 200
        assert r.json()["is_correct"] is False

    def test_mcq_case_insensitive_full_match(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        mcq = next(i for i in items if i.question_type == "mcq")
        # answer is "A. 牡羊座" — lowercase full match
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": mcq.id, "user_answer": mcq.answer.lower()},
        )
        assert r.status_code == 200
        assert r.json()["is_correct"] is True

    def test_mcq_first_char_match(self, client, quiz_with_items):
        """Submitting just 'a' should match an MCQ answer starting with 'A'."""
        video, quiz, items = quiz_with_items
        mcq = next(i for i in items if i.question_type == "mcq")
        # answer is "A. 牡羊座" → just 'a' should be accepted
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": mcq.id, "user_answer": "a"},
        )
        assert r.status_code == 200
        assert r.json()["is_correct"] is True

    def test_mcq_uppercase_first_char_match(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        mcq = next(i for i in items if i.question_type == "mcq")
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": mcq.id, "user_answer": "A"},
        )
        assert r.status_code == 200
        assert r.json()["is_correct"] is True

    def test_response_has_all_required_fields(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        item = items[0]
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": item.id, "user_answer": "test"},
        )
        assert r.status_code == 200
        data = r.json()
        for field in ["id", "quiz_item_id", "is_correct", "correct_answer", "explanation"]:
            assert field in data, f"Missing field: {field}"

    def test_response_correct_answer_matches_item(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        item = items[0]
        r = client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": item.id, "user_answer": "anything"},
        )
        assert r.json()["correct_answer"] == item.answer

    def test_attempt_recorded_in_db(self, client, db_session, quiz_with_items):
        video, quiz, items = quiz_with_items
        item = items[0]
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": item.id, "user_answer": "test_value"},
        )
        attempts = db_session.query(QuizAttempt).filter(QuizAttempt.quiz_item_id == item.id).all()
        assert len(attempts) == 1
        assert attempts[0].user_answer == "test_value"

    def test_multiple_attempts_all_recorded(self, client, db_session, quiz_with_items):
        video, quiz, items = quiz_with_items
        item = items[0]
        for _ in range(3):
            client.post(
                "/api/quiz/attempt",
                json={"quiz_item_id": item.id, "user_answer": "repeated"},
            )
        count = db_session.query(QuizAttempt).filter(QuizAttempt.quiz_item_id == item.id).count()
        assert count == 3


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/quiz/wrong-answers/list
# ═══════════════════════════════════════════════════════════════════════════════


class TestWrongAnswersList:
    def test_empty_when_no_attempts(self, client):
        r = client.get("/api/quiz/wrong-answers/list")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_empty_when_only_correct_attempts(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        item = items[0]
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": item.id, "user_answer": item.answer},
        )
        r = client.get("/api/quiz/wrong-answers/list")
        assert r.json()["total"] == 0

    def test_returns_wrong_attempts(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        tf = next(i for i in items if i.question_type == "truefalse")
        wrong = "True" if tf.answer == "False" else "False"
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": tf.id, "user_answer": wrong},
        )
        r = client.get("/api/quiz/wrong-answers/list")
        assert r.json()["total"] >= 1

    def test_wrong_answer_item_has_context_fields(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        tf = next(i for i in items if i.question_type == "truefalse")
        wrong = "True" if tf.answer == "False" else "False"
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": tf.id, "user_answer": wrong},
        )
        r = client.get("/api/quiz/wrong-answers/list")
        entry = r.json()["items"][0]
        for field in [
            "attempt_id",
            "quiz_item_id",
            "video_id",
            "question_type",
            "question",
            "correct_answer",
            "user_answer",
            "attempted_at",
        ]:
            assert field in entry, f"Missing field: {field}"

    def test_user_answer_preserved_in_wrong_list(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        tf = next(i for i in items if i.question_type == "truefalse")
        wrong = "True" if tf.answer == "False" else "False"
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": tf.id, "user_answer": wrong},
        )
        r = client.get("/api/quiz/wrong-answers/list")
        entry = r.json()["items"][0]
        assert entry["user_answer"] == wrong
        assert entry["correct_answer"] == tf.answer

    def test_limit_parameter_respected(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        for item in items:
            client.post(
                "/api/quiz/attempt",
                json={"quiz_item_id": item.id, "user_answer": "WRONG_XYZ"},
            )
        r = client.get("/api/quiz/wrong-answers/list?limit=1")
        assert len(r.json()["items"]) <= 1

    def test_total_reflects_wrong_count(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        for item in items:
            client.post(
                "/api/quiz/attempt",
                json={"quiz_item_id": item.id, "user_answer": "WRONG_XYZ"},
            )
        r = client.get("/api/quiz/wrong-answers/list")
        data = r.json()
        assert data["total"] == len(data["items"])


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/quiz/stats/overview
# ═══════════════════════════════════════════════════════════════════════════════


class TestQuizStatsOverview:
    def test_all_zeros_when_no_data(self, client):
        r = client.get("/api/quiz/stats/overview")
        assert r.status_code == 200
        data = r.json()
        assert data["total_items"] == 0
        assert data["total_attempts"] == 0
        assert data["correct_attempts"] == 0
        assert data["wrong_attempts"] == 0
        assert data["accuracy_percent"] == 0.0

    def test_has_all_required_fields(self, client):
        r = client.get("/api/quiz/stats/overview")
        data = r.json()
        for field in [
            "total_items",
            "total_attempts",
            "correct_attempts",
            "wrong_attempts",
            "accuracy_percent",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_total_items_counts_quiz_items(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        r = client.get("/api/quiz/stats/overview")
        assert r.json()["total_items"] == len(items)

    def test_attempt_counts_after_submissions(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        mcq = next(i for i in items if i.question_type == "mcq")
        tf = next(i for i in items if i.question_type == "truefalse")
        # One correct (full answer), one wrong
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": mcq.id, "user_answer": mcq.answer},
        )
        wrong = "True" if tf.answer == "False" else "False"
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": tf.id, "user_answer": wrong},
        )
        data = client.get("/api/quiz/stats/overview").json()
        assert data["total_attempts"] == 2
        assert data["correct_attempts"] == 1
        assert data["wrong_attempts"] == 1

    def test_accuracy_percent_calculated_correctly(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        item = items[0]
        # 3 correct, 1 wrong → 75%
        for _ in range(3):
            client.post(
                "/api/quiz/attempt",
                json={"quiz_item_id": item.id, "user_answer": item.answer},
            )
        client.post(
            "/api/quiz/attempt",
            json={"quiz_item_id": item.id, "user_answer": "definitely_wrong"},
        )
        data = client.get("/api/quiz/stats/overview").json()
        assert data["accuracy_percent"] == 75.0

    def test_accuracy_zero_when_no_attempts(self, client, quiz_with_items):
        r = client.get("/api/quiz/stats/overview")
        assert r.json()["accuracy_percent"] == 0.0

    def test_correct_plus_wrong_equals_total(self, client, quiz_with_items):
        video, quiz, items = quiz_with_items
        for item in items:
            client.post(
                "/api/quiz/attempt",
                json={"quiz_item_id": item.id, "user_answer": "some_answer"},
            )
        data = client.get("/api/quiz/stats/overview").json()
        assert data["correct_attempts"] + data["wrong_attempts"] == data["total_attempts"]


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/stats/heatmap
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatsHeatmap:
    def test_heatmap_returns_200(self, client):
        r = client.get("/api/stats/heatmap")
        assert r.status_code == 200

    def test_heatmap_has_data_key(self, client):
        r = client.get("/api/stats/heatmap")
        assert "data" in r.json()

    def test_heatmap_default_365_entries(self, client):
        r = client.get("/api/stats/heatmap")
        assert len(r.json()["data"]) == 365

    def test_heatmap_custom_days_param(self, client):
        r = client.get("/api/stats/heatmap?days=30")
        assert len(r.json()["data"]) == 30

    def test_heatmap_zero_counts_when_no_reviews(self, client):
        r = client.get("/api/stats/heatmap")
        for entry in r.json()["data"]:
            assert entry["count"] == 0

    def test_heatmap_entry_has_date_and_count(self, client):
        r = client.get("/api/stats/heatmap")
        entry = r.json()["data"][0]
        assert "date" in entry
        assert "count" in entry

    def test_heatmap_date_format_yyyy_mm_dd(self, client):
        r = client.get("/api/stats/heatmap")
        for entry in r.json()["data"]:
            d = entry["date"]
            assert len(d) == 10
            assert d[4] == "-" and d[7] == "-"
