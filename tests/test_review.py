"""
複習系統測試 — SM-2 間隔重複算法 + Review API
"""
import json
import uuid
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.database import Video, ReviewRecord, Summary, Classification
from app.routers.review import _sm2_update


# ═══════════════════════════════════════════════════════════════════════════════
# SM-2 算法單元測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestSM2Algorithm:
    """測試 SM-2 間隔重複算法邏輯"""

    def _make_video(self) -> Video:
        v = Video()
        v.sr_interval = 1
        v.sr_ease_factor = 2.5
        v.sr_repetitions = 0
        v.review_count = 0
        v.last_reviewed_at = None
        v.sr_next_review_at = None
        return v

    def test_first_review_confidence_5_sets_interval_1(self):
        v = self._make_video()
        _sm2_update(v, confidence=5)
        assert v.sr_repetitions == 1
        assert v.sr_interval == 1
        assert v.sr_ease_factor >= 2.5
        assert v.review_count == 1

    def test_second_review_confidence_5_sets_interval_6(self):
        v = self._make_video()
        _sm2_update(v, confidence=5)  # rep=1, interval=1
        _sm2_update(v, confidence=5)  # rep=2, interval=6
        assert v.sr_repetitions == 2
        assert v.sr_interval == 6

    def test_third_review_interval_multiplied_by_ease_factor(self):
        v = self._make_video()
        _sm2_update(v, confidence=5)
        _sm2_update(v, confidence=5)
        ef = v.sr_ease_factor
        _sm2_update(v, confidence=5)
        assert v.sr_interval == round(6 * ef)
        assert v.sr_repetitions == 3

    def test_low_confidence_resets_repetitions(self):
        v = self._make_video()
        _sm2_update(v, confidence=5)
        _sm2_update(v, confidence=5)
        # 回答錯誤
        _sm2_update(v, confidence=1)
        assert v.sr_repetitions == 0
        assert v.sr_interval == 1

    def test_confidence_2_also_resets(self):
        v = self._make_video()
        _sm2_update(v, confidence=5)
        _sm2_update(v, confidence=2)
        assert v.sr_repetitions == 0
        assert v.sr_interval == 1

    def test_ease_factor_minimum_is_1_3(self):
        v = self._make_video()
        v.sr_ease_factor = 1.4
        # 連續低分
        for _ in range(10):
            _sm2_update(v, confidence=1)
        assert v.sr_ease_factor >= 1.3

    def test_high_confidence_maintains_or_keeps_ease_factor(self):
        # SM-2 在此實作中 confidence=5 → quality=4，EF 維持不變（+0.1-0.1=0）
        v = self._make_video()
        initial_ef = v.sr_ease_factor
        _sm2_update(v, confidence=5)
        # EF 不應低於初始值（高信心不懲罰）
        assert v.sr_ease_factor >= initial_ef

    def test_confidence_3_decreases_ease_factor(self):
        # confidence=3 → quality=2; EF=2.5 → 2.18 (下降約 0.32)
        v = self._make_video()
        initial_ef = v.sr_ease_factor
        _sm2_update(v, confidence=3)
        assert v.sr_ease_factor < initial_ef
        assert v.sr_ease_factor >= 1.3

    def test_next_review_at_is_in_future(self):
        v = self._make_video()
        before = datetime.utcnow()
        _sm2_update(v, confidence=4)
        assert v.sr_next_review_at > before

    def test_last_reviewed_at_is_updated(self):
        v = self._make_video()
        before = datetime.utcnow()
        _sm2_update(v, confidence=3)
        assert v.last_reviewed_at >= before

    def test_review_count_increments(self):
        v = self._make_video()
        _sm2_update(v, confidence=4)
        assert v.review_count == 1
        _sm2_update(v, confidence=4)
        assert v.review_count == 2

    def test_none_fields_handled_gracefully(self):
        v = self._make_video()
        v.sr_interval = None
        v.sr_ease_factor = None
        v.sr_repetitions = None
        v.review_count = None
        # 不應拋出例外
        _sm2_update(v, confidence=4)
        assert v.sr_next_review_at is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Review API 端點測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarkReviewed:
    def test_mark_reviewed_success(self, client, completed_video):
        vid_id = completed_video.id
        r = client.post(f"/api/review/{vid_id}/mark", json={"confidence": 4})
        assert r.status_code == 200
        data = r.json()
        assert data["video_id"] == vid_id
        assert data["confidence"] == 4
        assert "sr_next_review_at" in data
        assert data["review_count"] == 1

    def test_mark_reviewed_updates_sm2_fields(self, client, completed_video):
        vid_id = completed_video.id
        client.post(f"/api/review/{vid_id}/mark", json={"confidence": 5})
        r = client.get(f"/api/videos/{vid_id}")
        v = r.json()
        assert v["review_count"] == 1
        assert v["last_reviewed_at"] is not None
        assert v["sr_next_review_at"] is not None

    def test_mark_reviewed_persists_record(self, client, db_session, completed_video):
        vid_id = completed_video.id
        client.post(f"/api/review/{vid_id}/mark", json={"confidence": 3})
        records = db_session.query(ReviewRecord).filter(ReviewRecord.video_id == vid_id).all()
        assert len(records) == 1
        assert records[0].confidence == 3

    def test_mark_reviewed_multiple_times(self, client, completed_video):
        vid_id = completed_video.id
        client.post(f"/api/review/{vid_id}/mark", json={"confidence": 5})
        client.post(f"/api/review/{vid_id}/mark", json={"confidence": 5})
        r = client.post(f"/api/review/{vid_id}/mark", json={"confidence": 4})
        assert r.json()["review_count"] == 3

    def test_mark_reviewed_video_not_found(self, client):
        r = client.post("/api/review/nonexistent/mark", json={"confidence": 3})
        assert r.status_code == 404

    def test_mark_reviewed_confidence_too_low(self, client, completed_video):
        r = client.post(f"/api/review/{completed_video.id}/mark", json={"confidence": 0})
        assert r.status_code == 422

    def test_mark_reviewed_confidence_too_high(self, client, completed_video):
        r = client.post(f"/api/review/{completed_video.id}/mark", json={"confidence": 6})
        assert r.status_code == 422

    def test_confidence_1_resets_interval(self, client, reviewed_video):
        vid_id = reviewed_video.id
        r = client.post(f"/api/review/{vid_id}/mark", json={"confidence": 1})
        assert r.json()["sr_interval"] == 1


class TestGetDueReviews:
    def test_due_returns_completed_videos(self, client, completed_video):
        r = client.get("/api/review/due")
        assert r.status_code == 200
        data = r.json()
        # completed_video is new (sr_next_review_at=None) → should be due
        ids = [item["id"] for item in data["items"]]
        assert completed_video.id in ids

    def test_due_excludes_future_reviews(self, client, db_session, completed_video):
        # 設定下次複習在未來
        completed_video.sr_next_review_at = datetime.utcnow() + timedelta(days=7)
        db_session.commit()
        r = client.get("/api/review/due")
        ids = [item["id"] for item in r.json()["items"]]
        assert completed_video.id not in ids

    def test_due_excludes_pending_videos(self, client, sample_video):
        r = client.get("/api/review/due")
        ids = [item["id"] for item in r.json()["items"]]
        assert sample_video.id not in ids

    def test_due_respects_limit(self, client, db_session):
        for i in range(5):
            db_session.add(Video(
                id=uuid.uuid4().hex, filename=f"v{i}.mp4",
                original_filename=f"v{i}.mp4", file_size=100,
                status="completed", sr_next_review_at=None,
            ))
        db_session.commit()
        r = client.get("/api/review/due?limit=3")
        assert len(r.json()["items"]) <= 3

    def test_due_items_contain_review_fields(self, client, completed_video):
        r = client.get("/api/review/due")
        item = next((i for i in r.json()["items"] if i["id"] == completed_video.id), None)
        assert item is not None
        assert "review_count" in item
        assert "sr_interval" in item
        assert "sr_ease_factor" in item

    def test_due_overdue_video_included(self, client, reviewed_video):
        """過期的影片（sr_next_review_at 在過去）應被包含"""
        r = client.get("/api/review/due")
        ids = [item["id"] for item in r.json()["items"]]
        assert reviewed_video.id in ids


class TestGetUpcomingReviews:
    def test_upcoming_excludes_already_due(self, client, completed_video):
        r = client.get("/api/review/upcoming?days=7")
        assert r.status_code == 200
        ids = [item["id"] for item in r.json()["items"]]
        # completed_video has no sr_next_review_at → it's due NOW, not upcoming
        assert completed_video.id not in ids

    def test_upcoming_includes_scheduled_future(self, client, db_session, completed_video):
        completed_video.sr_next_review_at = datetime.utcnow() + timedelta(days=3)
        db_session.commit()
        r = client.get("/api/review/upcoming?days=7")
        ids = [item["id"] for item in r.json()["items"]]
        assert completed_video.id in ids

    def test_upcoming_excludes_beyond_range(self, client, db_session, completed_video):
        completed_video.sr_next_review_at = datetime.utcnow() + timedelta(days=14)
        db_session.commit()
        r = client.get("/api/review/upcoming?days=7")
        ids = [item["id"] for item in r.json()["items"]]
        assert completed_video.id not in ids

    def test_upcoming_days_parameter(self, client):
        r = client.get("/api/review/upcoming?days=30")
        assert r.status_code == 200
        assert r.json()["days"] == 30


class TestReviewHistory:
    def test_history_empty_initially(self, client, completed_video):
        r = client.get(f"/api/review/history/{completed_video.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["review_count"] == 0
        assert data["records"] == []

    def test_history_after_review(self, client, completed_video):
        vid_id = completed_video.id
        client.post(f"/api/review/{vid_id}/mark", json={"confidence": 4})
        client.post(f"/api/review/{vid_id}/mark", json={"confidence": 5})
        r = client.get(f"/api/review/history/{vid_id}")
        data = r.json()
        assert data["review_count"] == 2
        assert len(data["records"]) == 2
        # 最新的排最前
        assert data["records"][0]["confidence"] in [4, 5]

    def test_history_video_not_found(self, client):
        r = client.get("/api/review/history/nonexistent")
        assert r.status_code == 404

    def test_history_records_have_required_fields(self, client, completed_video):
        vid_id = completed_video.id
        client.post(f"/api/review/{vid_id}/mark", json={"confidence": 3})
        r = client.get(f"/api/review/history/{vid_id}")
        rec = r.json()["records"][0]
        assert "id" in rec
        assert "confidence" in rec
        assert "reviewed_at" in rec


class TestReviewStats:
    def test_stats_structure(self, client):
        r = client.get("/api/review/stats")
        assert r.status_code == 200
        data = r.json()
        for key in ["total_completed", "reviewed_at_least_once", "never_reviewed",
                    "due_today", "reviewed_today", "daily_review_counts"]:
            assert key in data

    def test_stats_counts_never_reviewed(self, client, completed_video):
        r = client.get("/api/review/stats")
        data = r.json()
        assert data["never_reviewed"] >= 1

    def test_stats_daily_has_7_days(self, client):
        r = client.get("/api/review/stats")
        daily = r.json()["daily_review_counts"]
        assert len(daily) == 7

    def test_stats_reviewed_today_increments(self, client, completed_video):
        before = client.get("/api/review/stats").json()["reviewed_today"]
        client.post(f"/api/review/{completed_video.id}/mark", json={"confidence": 4})
        after = client.get("/api/review/stats").json()["reviewed_today"]
        assert after == before + 1

    def test_stats_all_counts_non_negative(self, client):
        data = client.get("/api/review/stats").json()
        for key in ["total_completed", "reviewed_at_least_once", "never_reviewed",
                    "due_today", "reviewed_today"]:
            assert data[key] >= 0
