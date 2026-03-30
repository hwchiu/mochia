"""
Router Integration Tests
=========================
These tests call the HTTP endpoints with the REAL analyze_all(),
generate_faq(), and generate_deep_content() service functions.

Only _get_client() (the AzureOpenAI HTTP client factory) is mocked.
Every service-layer function runs for real, meaning:

- Any mismatch between a router's unpack code and analyze_all's return
  type will raise an exception here.
- Any JSON parsing bug in the service will be caught here.
- Any new field added to analyze_all's return value must be handled by
  the router or this test will fail.

Endpoints under test
--------------------
  POST /{video_id}/reanalyze     — calls analyze_all() + generate_deep_content()
  POST /{video_id}/regenerate/faq — calls generate_faq()
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.database import Classification, Summary, Transcript, Video

# ── shared GPT stubs ───────────────────────────────────────────────────────────

_ANALYZE_ALL_JSON = json.dumps(
    {
        "summary": "重新分析後的完整摘要，涵蓋占星學重要概念與實際應用方式。" * 3,
        "key_points": [
            {"theme": "星盤解讀", "points": ["太陽星座決定核心性格", "月亮星座反映情緒模式"]},
            {"theme": "行運分析", "points": ["行星過境影響人生事件", "大限小限預測重要時期"]},
        ],
        "category": "占星學 (Astrology)",
        "confidence": 0.88,
        "faq": [
            {"question": "星盤如何計算？", "answer": "根據出生時間地點計算。"},
            {"question": "行運如何預測？", "answer": "觀察行星與本命盤的相位關係。"},
        ],
    }
)

_DEEP_CONTENT_JSON = json.dumps(
    {
        "study_notes": "## 核心概念\n占星學的精髓在於宇宙與個人的對應關係。\n\n## 重要術語\n星盤、相位、宮位\n\n## 學習重點\n- 十二宮位代表不同人生領域\n\n## 實踐建議\n定期研究個人行運\n\n## 延伸思考\n命運是否真的被星盤所決定？",
        "case_analysis": "NO_CASE_ANALYSIS",
    }
)

_FAQ_JSON = json.dumps(
    [
        {"question": "重新生成的問題一？", "answer": "重新生成的回答一。"},
        {"question": "重新生成的問題二？", "answer": "重新生成的回答二。"},
    ]
)


def _make_reanalyze_client() -> MagicMock:
    """2 responses: analyze_all → deep_content."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=_ANALYZE_ALL_JSON))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=_DEEP_CONTENT_JSON))]),
    ]
    return client


def _make_faq_client() -> MagicMock:
    """1 response: generate_faq."""
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=_FAQ_JSON))]
    )
    return client


# ── fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def video_with_transcript(db_session) -> Video:
    """Completed video with transcript and summary — ready for regeneration."""
    vid_id = uuid.uuid4().hex
    video = Video(
        id=vid_id,
        filename="regen_test.mp4",
        original_filename="regen_test.mp4",
        file_path="/fake/path/regen_test.mp4",
        source="local_scan",
        file_size=1024,
        duration=120.0,
        status="completed",
    )
    transcript = Transcript(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        content="原始逐字稿，討論占星學基礎知識。" * 10,
    )
    summary = Summary(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        summary="原始摘要",
        key_points=json.dumps(["原始重點"], ensure_ascii=False),
        faq=json.dumps([{"question": "舊問題", "answer": "舊回答"}], ensure_ascii=False),
    )
    classification = Classification(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        category="未分類 (Uncategorized)",
        confidence=0.5,
    )
    for obj in [video, transcript, summary, classification]:
        db_session.add(obj)
    db_session.commit()
    db_session.refresh(video)
    return video


# ── reanalyze endpoint ─────────────────────────────────────────────────────────


class TestReanalyzeEndpoint:
    """POST /{video_id}/reanalyze — calls real analyze_all() + generate_deep_content()."""

    def test_returns_200(self, client, video_with_transcript):
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            resp = client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        assert resp.status_code == 200

    def test_response_contains_summary(self, client, video_with_transcript):
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            resp = client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        data = resp.json()
        assert "summary" in data
        assert "重新分析後" in data["summary"]

    def test_response_contains_category(self, client, video_with_transcript):
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            resp = client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        assert resp.json()["category"] == "占星學 (Astrology)"

    def test_db_summary_updated(self, client, db_session, video_with_transcript):
        """DB summary must reflect GPT output after reanalyze."""
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        summary = db_session.query(Summary).filter_by(video_id=video_with_transcript.id).first()
        assert "重新分析後" in summary.summary

    def test_db_faq_updated(self, client, db_session, video_with_transcript):
        """FAQ in DB must be overwritten with new GPT output."""
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        summary = db_session.query(Summary).filter_by(video_id=video_with_transcript.id).first()
        faq = json.loads(summary.faq)
        assert faq[0]["question"] == "星盤如何計算？"

    def test_db_key_points_updated(self, client, db_session, video_with_transcript):
        """key_points in DB must contain the new GPT-returned themes."""
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        summary = db_session.query(Summary).filter_by(video_id=video_with_transcript.id).first()
        kp = json.loads(summary.key_points)
        themes = [item["theme"] for item in kp]
        assert "星盤解讀" in themes

    def test_db_classification_updated(self, client, db_session, video_with_transcript):
        """Classification record must be updated with new category and confidence."""
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        cls = db_session.query(Classification).filter_by(video_id=video_with_transcript.id).first()
        assert cls.category == "占星學 (Astrology)"
        assert abs(float(cls.confidence) - 0.88) < 0.001

    def test_db_study_notes_updated(self, client, db_session, video_with_transcript):
        """study_notes must be written by generate_deep_content() via real call."""
        with patch("app.services.analyzer._get_client", return_value=_make_reanalyze_client()):
            client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        summary = db_session.query(Summary).filter_by(video_id=video_with_transcript.id).first()
        assert summary.study_notes is not None
        assert "核心概念" in summary.study_notes

    def test_gpt_called_twice(self, client, video_with_transcript):
        """Reanalyze must make exactly 2 GPT calls."""
        mock_client = _make_reanalyze_client()
        with patch("app.services.analyzer._get_client", return_value=mock_client):
            client.post(f"/api/analysis/{video_with_transcript.id}/reanalyze")
        assert mock_client.chat.completions.create.call_count == 2

    def test_nonexistent_video_returns_404(self, client):
        resp = client.post("/api/analysis/nonexistent_id/reanalyze")
        assert resp.status_code == 404

    def test_video_without_transcript_returns_409(self, client, db_session):
        vid_id = uuid.uuid4().hex
        video = Video(
            id=vid_id,
            filename="no_transcript.mp4",
            original_filename="no_transcript.mp4",
            file_path="/fake/path/no_transcript.mp4",
            source="local_scan",
            file_size=1024,
            status="completed",
        )
        db_session.add(video)
        db_session.commit()
        resp = client.post(f"/api/analysis/{vid_id}/reanalyze")
        assert resp.status_code == 409


# ── regenerate/faq endpoint ────────────────────────────────────────────────────


class TestRegenerateFaqEndpoint:
    """POST /{video_id}/regenerate/faq — calls real generate_faq()."""

    def test_returns_200(self, client, video_with_transcript):
        with patch("app.services.analyzer._get_client", return_value=_make_faq_client()):
            resp = client.post(f"/api/analysis/{video_with_transcript.id}/regenerate/faq")
        assert resp.status_code == 200

    def test_response_contains_faq_list(self, client, video_with_transcript):
        with patch("app.services.analyzer._get_client", return_value=_make_faq_client()):
            resp = client.post(f"/api/analysis/{video_with_transcript.id}/regenerate/faq")
        data = resp.json()
        assert "faq" in data
        assert isinstance(data["faq"], list)

    def test_db_faq_overwritten(self, client, db_session, video_with_transcript):
        """Old FAQ must be replaced with new GPT output."""
        with patch("app.services.analyzer._get_client", return_value=_make_faq_client()):
            client.post(f"/api/analysis/{video_with_transcript.id}/regenerate/faq")
        summary = db_session.query(Summary).filter_by(video_id=video_with_transcript.id).first()
        faq = json.loads(summary.faq)
        questions = [item["question"] for item in faq]
        assert "重新生成的問題一？" in questions

    def test_only_faq_is_updated(self, client, db_session, video_with_transcript):
        """regenerate/faq must not overwrite summary or key_points."""
        original_summary = (
            db_session.query(Summary).filter_by(video_id=video_with_transcript.id).first().summary
        )
        with patch("app.services.analyzer._get_client", return_value=_make_faq_client()):
            client.post(f"/api/analysis/{video_with_transcript.id}/regenerate/faq")
        summary = db_session.query(Summary).filter_by(video_id=video_with_transcript.id).first()
        assert summary.summary == original_summary

    def test_invalid_content_type_returns_400(self, client, video_with_transcript):
        resp = client.post(f"/api/analysis/{video_with_transcript.id}/regenerate/summary")
        assert resp.status_code == 400

    def test_nonexistent_video_returns_404(self, client):
        resp = client.post("/api/analysis/nonexistent/regenerate/faq")
        assert resp.status_code == 404
