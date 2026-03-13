"""API 端點整合測試"""

import uuid
from pathlib import Path

import pytest

from app.config import settings
from app.database import TaskQueue, Video

# ─────────────────────── Videos API ───────────────────────


class TestVideosAPI:
    def test_list_videos_empty(self, client):
        r = client.get("/api/videos/")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_videos_returns_data(self, client, sample_video):
        r = client.get("/api/videos/")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == sample_video.id

    def test_list_videos_filter_by_status(self, client, sample_video, completed_video):
        r = client.get("/api/videos/?status=completed")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(v["status"] == "completed" for v in items)
        assert any(v["id"] == completed_video.id for v in items)

    def test_list_videos_filter_by_source(self, client, sample_video):
        r = client.get("/api/videos/?source=local_scan")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(v["source"] == "local_scan" for v in items)

    def test_list_videos_pagination(self, client, db_session):
        for i in range(5):
            db_session.add(
                Video(
                    id=uuid.uuid4().hex,
                    filename=f"vid{i}.mp4",
                    original_filename=f"vid{i}.mp4",
                    file_path=f"/p/vid{i}.mp4",
                    source="local_scan",
                    file_size=100,
                )
            )
        db_session.commit()

        r = client.get("/api/videos/?limit=3&skip=0")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 5
        assert len(body["items"]) == 3

        r2 = client.get("/api/videos/?limit=3&skip=3")
        assert len(r2.json()["items"]) == 2

    def test_get_video_by_id(self, client, sample_video):
        r = client.get(f"/api/videos/{sample_video.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == sample_video.id
        assert body["filename"] == sample_video.filename
        assert body["source"] == "local_scan"

    def test_get_video_not_found(self, client):
        r = client.get("/api/videos/nonexistent_id")
        assert r.status_code == 404

    def test_delete_video(self, client, sample_video):
        r = client.delete(f"/api/videos/{sample_video.id}")
        assert r.status_code == 200
        # 確認已刪除
        r2 = client.get(f"/api/videos/{sample_video.id}")
        assert r2.status_code == 404

    def test_delete_video_not_found(self, client):
        r = client.delete("/api/videos/nonexistent_id")
        assert r.status_code == 404

    def test_upload_video_invalid_extension(self, client, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("not a video")
        with open(f, "rb") as fh:
            r = client.post("/api/videos/upload", files={"file": ("test.txt", fh, "text/plain")})
        assert r.status_code == 400
        assert "不支援" in r.json()["detail"]

    def test_upload_sanitizes_traversal_filename(self, client, tmp_path):
        src = tmp_path / "video.mp4"
        payload = b"dummy video content"
        src.write_bytes(payload)

        with open(src, "rb") as fh:
            response = client.post(
                "/api/videos/upload", files={"file": ("../../evil.mp4", fh, "video/mp4")}
            )

        assert response.status_code == 200
        body = response.json()

        # Original filename is preserved, but stored filename must be randomized and path-safe
        assert body["original_filename"] == "../../evil.mp4"
        assert body["filename"].endswith(".mp4")
        assert ".." not in body["filename"]

        dest = Path(body["file_path"])
        try:
            assert dest.exists()
            assert dest.parent.resolve() == settings.UPLOAD_DIR.resolve()
            assert dest.read_bytes() == payload
        finally:
            dest.unlink(missing_ok=True)


# ─────────────────────── Analysis API ───────────────────────


class TestAnalysisAPI:
    def test_queue_video(self, client, sample_video):
        r = client.post(f"/api/analysis/{sample_video.id}/queue")
        assert r.status_code == 200
        body = r.json()
        assert "task_id" in body
        assert body["message"] == "已加入佇列"

    def test_queue_video_not_found(self, client):
        r = client.post("/api/analysis/nonexistent/queue")
        assert r.status_code == 404

    def test_queue_video_already_queued(self, client, sample_video):
        """重複加入佇列應回傳已存在的任務"""
        r1 = client.post(f"/api/analysis/{sample_video.id}/queue")
        r2 = client.post(f"/api/analysis/{sample_video.id}/queue")
        assert r2.status_code == 200
        assert "已在佇列中" in r2.json()["message"]
        assert r1.json()["task_id"] == r2.json()["task_id"]

    def test_get_status_no_task(self, client, sample_video):
        r = client.get(f"/api/analysis/{sample_video.id}/status")
        assert r.status_code == 200
        body = r.json()
        assert body["video_status"] == "pending"
        assert body["task"] is None

    def test_get_status_with_task(self, client, sample_video):
        client.post(f"/api/analysis/{sample_video.id}/queue")
        r = client.get(f"/api/analysis/{sample_video.id}/status")
        assert r.status_code == 200
        body = r.json()
        assert body["task"]["status"] == "pending"

    def test_get_results_not_completed(self, client, sample_video):
        r = client.get(f"/api/analysis/{sample_video.id}/results")
        assert r.status_code == 409

    def test_get_results_completed(self, client, completed_video):
        r = client.get(f"/api/analysis/{completed_video.id}/results")
        assert r.status_code == 200
        body = r.json()
        assert body["transcript"] is not None
        assert body["summary"] is not None
        assert isinstance(body["key_points"], list)
        assert len(body["key_points"]) == 3
        assert body["category"] == "占星學 (Astrology)"
        assert body["confidence"] == pytest.approx(0.92, abs=0.01)

    def test_get_results_video_not_found(self, client):
        r = client.get("/api/analysis/nonexistent/results")
        assert r.status_code == 404


# ─────────────────────── Batch API ───────────────────────


class TestBatchAPI:
    def test_batch_status_empty(self, client):
        r = client.get("/api/batch/status")
        assert r.status_code == 200
        body = r.json()
        assert "videos" in body
        assert "tasks" in body
        assert body["videos"]["pending"] == 0
        assert body["currently_processing"] == []

    def test_batch_status_with_videos(self, client, sample_video, completed_video):
        r = client.get("/api/batch/status")
        assert r.status_code == 200
        body = r.json()
        assert body["videos"]["pending"] == 1
        assert body["videos"]["completed"] == 1

    def test_scan_nonexistent_directory(self, client):
        r = client.post("/api/batch/scan?path=/nonexistent/path/xyz")
        assert r.status_code == 400

    def test_scan_not_a_directory(self, client, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("test")
        r = client.post(f"/api/batch/scan?path={f}")
        assert r.status_code == 400

    def test_scan_empty_directory(self, client, tmp_path):
        r = client.post(f"/api/batch/scan?path={tmp_path}")
        assert r.status_code == 200
        body = r.json()
        assert body["found"] == 0
        assert body["registered"] == 0

    def test_scan_directory_with_videos(self, client, tmp_path):
        """掃描包含假影片的目錄"""
        for name in ["a.mp4", "b.mp4", "sub/c.mp4"]:
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\x00" * 100)

        with pytest.MonkeyPatch.context() as mp:
            # mock get_video_duration 避免呼叫真實 ffprobe
            mp.setattr("app.routers.batch.get_video_duration", lambda p: 60.0)
            r = client.post(f"/api/batch/scan?path={tmp_path}")

        assert r.status_code == 200
        body = r.json()
        assert body["found"] == 3
        assert body["registered"] == 3
        assert body["skipped"] == 0

    def test_scan_skips_already_registered(self, client, tmp_path, db_session):
        """已登錄的影片不重複登錄"""
        f = tmp_path / "existing.mp4"
        f.write_bytes(b"\x00" * 100)

        # 先登錄一次
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routers.batch.get_video_duration", lambda p: 60.0)
            r1 = client.post(f"/api/batch/scan?path={tmp_path}")
        assert r1.json()["registered"] == 1

        # 再掃描一次
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routers.batch.get_video_duration", lambda p: 60.0)
            r2 = client.post(f"/api/batch/scan?path={tmp_path}")
        assert r2.json()["registered"] == 0
        assert r2.json()["skipped"] == 1

    def test_queue_all_pending(self, client, db_session):
        """queue-all 將所有 pending 影片加入佇列"""
        for i in range(3):
            db_session.add(
                Video(
                    id=uuid.uuid4().hex,
                    filename=f"v{i}.mp4",
                    original_filename=f"v{i}.mp4",
                    file_path=f"/p/v{i}.mp4",
                    source="local_scan",
                    file_size=100,
                    status="pending",
                )
            )
        db_session.commit()

        r = client.post("/api/batch/queue-all")
        assert r.status_code == 200
        body = r.json()
        assert body["queued"] == 3

        # 再次呼叫，不應重複加入
        r2 = client.post("/api/batch/queue-all")
        assert r2.json()["queued"] == 0

    def test_cancel_all(self, client, db_session):
        """cancel-all 取消所有 pending 任務"""
        vid = Video(
            id=uuid.uuid4().hex,
            filename="x.mp4",
            original_filename="x.mp4",
            file_path="/p/x.mp4",
            source="local_scan",
            file_size=100,
            status="queued",
        )
        db_session.add(vid)
        db_session.commit()
        task = TaskQueue(id=uuid.uuid4().hex, video_id=vid.id, status="pending")
        db_session.add(task)
        db_session.commit()

        r = client.post("/api/batch/cancel-all")
        assert r.status_code == 200
        assert r.json()["cancelled"] == 1

    def test_retry_failed(self, client, db_session):
        """retry-failed 重設失敗任務"""
        vid = Video(
            id=uuid.uuid4().hex,
            filename="fail.mp4",
            original_filename="fail.mp4",
            file_path="/p/fail.mp4",
            source="local_scan",
            file_size=100,
            status="failed",
            error_message="some error",
        )
        db_session.add(vid)
        db_session.commit()
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=vid.id,
            status="failed",
            retry_count=3,
            error_message="some error",
        )
        db_session.add(task)
        db_session.commit()

        r = client.post("/api/batch/retry-failed")
        assert r.status_code == 200
        assert r.json()["retried"] == 1

        db_session.refresh(task)
        db_session.refresh(vid)
        assert task.status == "pending"
        assert task.retry_count == 0
        assert vid.status == "queued"
        assert vid.error_message is None


# ─────────────────────── Pages ───────────────────────


class TestPages:
    def test_index_page(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Video Analyzer" in r.text

    def test_detail_page(self, client, sample_video):
        r = client.get(f"/video/{sample_video.id}")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert sample_video.id in r.text


# ─────────────────────── Version API ───────────────────────


class TestVersionAPI:
    def test_version_returns_200(self, client):
        r = client.get("/api/version")
        assert r.status_code == 200

    def test_version_has_required_fields(self, client):
        body = client.get("/api/version").json()
        assert "version" in body
        assert "build_date" in body
        assert "app_name" in body

    def test_version_default_values(self, client):
        body = client.get("/api/version").json()
        assert body["app_name"] == "Video Analyzer"
        # 測試環境未注入 build-arg，應為預設值
        assert body["version"] == "dev"
        assert body["build_date"] == "unknown"
