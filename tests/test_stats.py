"""
學習統計儀表板 API 測試
"""

import uuid
from datetime import datetime, timedelta

from app.database import ReviewRecord, Video, VideoLabel

# ─── 測試輔助 ─────────────────────────────────────────────────────────────────


def _add_review(db_session, video_id: str, confidence: int, days_ago: int = 0):
    db_session.add(
        ReviewRecord(
            id=uuid.uuid4().hex,
            video_id=video_id,
            confidence=confidence,
            reviewed_at=datetime.utcnow() - timedelta(days=days_ago),
        )
    )
    db_session.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/stats/overview
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatsOverview:
    def test_overview_structure(self, client):
        r = client.get("/api/stats/overview")
        assert r.status_code == 200
        data = r.json()
        for key in [
            "total_videos",
            "completed",
            "pending",
            "failed",
            "reviewed",
            "never_reviewed",
            "due_today",
            "reviewed_today",
            "total_review_sessions",
            "category_distribution",
            "label_stats",
        ]:
            assert key in data, f"Missing key: {key}"

    def test_overview_empty_database(self, client):
        r = client.get("/api/stats/overview")
        data = r.json()
        assert data["total_videos"] == 0
        assert data["completed"] == 0
        assert data["never_reviewed"] == 0

    def test_overview_counts_completed(self, client, completed_video):
        r = client.get("/api/stats/overview")
        data = r.json()
        assert data["completed"] >= 1
        assert data["total_videos"] >= 1

    def test_overview_never_reviewed_includes_new_completed(self, client, completed_video):
        r = client.get("/api/stats/overview")
        assert r.json()["never_reviewed"] >= 1

    def test_overview_reviewed_after_mark(self, client, completed_video):
        client.post(f"/api/review/{completed_video.id}/mark", json={"confidence": 4})
        data = client.get("/api/stats/overview").json()
        assert data["reviewed"] >= 1
        assert data["reviewed_today"] >= 1

    def test_overview_category_distribution(self, client, db_session, completed_video):
        # completed_video 已有分類（來自 conftest）
        data = client.get("/api/stats/overview").json()
        assert isinstance(data["category_distribution"], dict)

    def test_overview_label_stats_with_labels(
        self, client, db_session, completed_video, sample_label
    ):
        db_session.add(
            VideoLabel(
                id=uuid.uuid4().hex,
                video_id=completed_video.id,
                label_id=sample_label.id,
            )
        )
        db_session.commit()
        data = client.get("/api/stats/overview").json()
        label_entry = next(
            (entry for entry in data["label_stats"] if entry["id"] == sample_label.id), None
        )
        assert label_entry is not None
        assert label_entry["count"] == 1

    def test_overview_all_counts_non_negative(self, client, completed_video):
        data = client.get("/api/stats/overview").json()
        for key in [
            "total_videos",
            "completed",
            "pending",
            "failed",
            "reviewed",
            "never_reviewed",
            "due_today",
            "reviewed_today",
        ]:
            assert data[key] >= 0, f"{key} is negative"

    def test_overview_reviewed_plus_never_equals_completed(self, client, completed_video):
        data = client.get("/api/stats/overview").json()
        assert data["reviewed"] + data["never_reviewed"] == data["completed"]

    def test_overview_due_today_includes_new_video(self, client, completed_video):
        """新完成的影片（未複習）應計入今日待複習"""
        data = client.get("/api/stats/overview").json()
        assert data["due_today"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/stats/daily
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatsDaily:
    def test_daily_default_30_days(self, client):
        r = client.get("/api/stats/daily")
        assert r.status_code == 200
        data = r.json()
        assert data["days"] == 30
        assert len(data["data"]) == 30

    def test_daily_custom_days(self, client):
        r = client.get("/api/stats/daily?days=7")
        data = r.json()
        assert data["days"] == 7
        assert len(data["data"]) == 7

    def test_daily_date_format(self, client):
        r = client.get("/api/stats/daily?days=3")
        for entry in r.json()["data"]:
            # YYYY-MM-DD 格式
            assert len(entry["date"]) == 10
            assert entry["date"][4] == "-"
            assert entry["date"][7] == "-"

    def test_daily_all_reviews_zero_initially(self, client):
        r = client.get("/api/stats/daily?days=7")
        for entry in r.json()["data"]:
            assert entry["reviews"] == 0

    def test_daily_today_review_counted(self, client, db_session, completed_video):
        _add_review(db_session, completed_video.id, confidence=4, days_ago=0)
        r = client.get("/api/stats/daily?days=7")
        today_entry = r.json()["data"][-1]  # 最後一天是今天
        assert today_entry["reviews"] >= 1

    def test_daily_past_reviews_counted_correctly(self, client, db_session, completed_video):
        _add_review(db_session, completed_video.id, confidence=3, days_ago=2)
        r = client.get("/api/stats/daily?days=7")
        entries = r.json()["data"]
        # 2 天前的 entry（倒數第 3 個）
        entry_2_days_ago = entries[-3]
        assert entry_2_days_ago["reviews"] >= 1

    def test_daily_reviews_non_negative(self, client):
        r = client.get("/api/stats/daily?days=14")
        for entry in r.json()["data"]:
            assert entry["reviews"] >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/stats/confidence
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatsConfidence:
    def test_confidence_structure(self, client):
        r = client.get("/api/stats/confidence")
        assert r.status_code == 200
        data = r.json()["distribution"]
        assert len(data) == 5
        levels = [d["level"] for d in data]
        assert sorted(levels) == [1, 2, 3, 4, 5]

    def test_confidence_has_labels(self, client):
        data = client.get("/api/stats/confidence").json()["distribution"]
        for entry in data:
            assert "label" in entry
            assert len(entry["label"]) > 0

    def test_confidence_zero_when_no_reviews(self, client):
        data = client.get("/api/stats/confidence").json()["distribution"]
        assert all(d["count"] == 0 for d in data)

    def test_confidence_counts_latest_review_only(self, client, db_session, completed_video):
        vid_id = completed_video.id
        # 先給信心 2，再給信心 5 → 只算最新一次 (5)
        _add_review(db_session, vid_id, confidence=2, days_ago=5)
        _add_review(db_session, vid_id, confidence=5, days_ago=0)
        # 更新 Video.review_count 模擬
        v = db_session.query(Video).get(vid_id)
        v.review_count = 2
        db_session.commit()
        data = client.get("/api/stats/confidence").json()["distribution"]
        level5 = next(d for d in data if d["level"] == 5)
        level2 = next(d for d in data if d["level"] == 2)
        assert level5["count"] == 1
        assert level2["count"] == 0

    def test_confidence_counts_non_negative(self, client):
        data = client.get("/api/stats/confidence").json()["distribution"]
        for d in data:
            assert d["count"] >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/stats/top-reviewed
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatsTopReviewed:
    def test_top_reviewed_empty_when_no_reviews(self, client):
        r = client.get("/api/stats/top-reviewed")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_top_reviewed_shows_reviewed_video(self, client, db_session, completed_video):
        completed_video.review_count = 5
        db_session.commit()
        r = client.get("/api/stats/top-reviewed")
        ids = [v["id"] for v in r.json()["items"]]
        assert completed_video.id in ids

    def test_top_reviewed_sorted_descending(self, client, db_session):
        for count in [3, 7, 1]:
            db_session.add(
                Video(
                    id=uuid.uuid4().hex,
                    filename=f"v{count}.mp4",
                    original_filename=f"v{count}.mp4",
                    file_size=100,
                    status="completed",
                    review_count=count,
                )
            )
        db_session.commit()
        r = client.get("/api/stats/top-reviewed")
        items = r.json()["items"]
        counts = [v["review_count"] for v in items]
        assert counts == sorted(counts, reverse=True)

    def test_top_reviewed_limit_respected(self, client, db_session):
        for i in range(15):
            db_session.add(
                Video(
                    id=uuid.uuid4().hex,
                    filename=f"top{i}.mp4",
                    original_filename=f"top{i}.mp4",
                    file_size=100,
                    status="completed",
                    review_count=i + 1,
                )
            )
        db_session.commit()
        r = client.get("/api/stats/top-reviewed?limit=5")
        assert len(r.json()["items"]) <= 5

    def test_top_reviewed_has_required_fields(self, client, db_session, completed_video):
        completed_video.review_count = 2
        db_session.commit()
        r = client.get("/api/stats/top-reviewed")
        if r.json()["items"]:
            item = r.json()["items"][0]
            assert "id" in item
            assert "filename" in item
            assert "review_count" in item
            assert "sr_ease_factor" in item
