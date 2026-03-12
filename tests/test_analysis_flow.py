"""Integration tests for analysis status and results flow."""

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Summary, Video


class TestAnalysisStatusFlow:
    def _make_video(self, db: Session, status: str = "pending") -> Video:
        v = Video(
            id=uuid.uuid4().hex,
            filename=f"analysis_{uuid.uuid4().hex}.mp4",
            original_filename="analysis.mp4",
            file_path="/fake/analysis.mp4",
            source="local_scan",
            file_size=1024,
            status=status,
            progress_step=0,
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        return v

    def test_queue_nonexistent_video_returns_404(self, client: TestClient):
        resp = client.post("/api/analysis/nonexistent_id/queue")
        assert resp.status_code == 404

    def test_status_nonexistent_video_returns_404(self, client: TestClient):
        resp = client.get("/api/analysis/nonexistent_id/status")
        assert resp.status_code == 404

    def test_results_nonexistent_video_returns_404(self, client: TestClient):
        resp = client.get("/api/analysis/nonexistent_id/results")
        assert resp.status_code == 404

    def test_status_returns_step_names(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session, status="processing")
        video.progress_step = 2  # type: ignore[assignment]
        db_session.commit()

        resp = client.get(f"/api/analysis/{video.id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["video_id"] == video.id
        assert body["progress"]["step"] == 2
        assert body["progress"]["step_name"] == "語音轉文字"
        assert body["progress"]["total_steps"] == 4

    def test_status_step_0_shows_waiting(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session)
        resp = client.get(f"/api/analysis/{video.id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["progress"]["step_name"] == "等待中"

    def test_results_returns_409_when_not_completed(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session, status="processing")
        resp = client.get(f"/api/analysis/{video.id}/results")
        assert resp.status_code == 409

    def test_results_returns_proper_structure(self, client: TestClient, completed_video):
        resp = client.get(f"/api/analysis/{completed_video.id}/results")
        assert resp.status_code == 200
        body = resp.json()
        assert "video_id" in body
        assert "transcript" in body
        assert "summary" in body
        assert "key_points" in body
        assert isinstance(body["key_points"], list)
        assert "category" in body

    def test_results_key_points_parsed_from_json(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session, status="completed")
        summary = Summary(
            id=uuid.uuid4().hex,
            video_id=video.id,
            summary="測試摘要",
            key_points=json.dumps(["重點A", "重點B", "重點C"], ensure_ascii=False),
        )
        db_session.add(summary)
        db_session.commit()

        resp = client.get(f"/api/analysis/{video.id}/results")
        assert resp.status_code == 200
        body = resp.json()
        assert body["key_points"] == ["重點A", "重點B", "重點C"]

    def test_results_malformed_key_points_returns_empty_list(
        self, client: TestClient, db_session: Session
    ):
        video = self._make_video(db_session, status="completed")
        summary = Summary(
            id=uuid.uuid4().hex,
            video_id=video.id,
            summary="測試摘要",
            key_points="not valid json {{{",
        )
        db_session.add(summary)
        db_session.commit()

        resp = client.get(f"/api/analysis/{video.id}/results")
        assert resp.status_code == 200
        body = resp.json()
        assert body["key_points"] == []

    def test_queue_adds_task_and_sets_status_queued(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session)
        resp = client.post(f"/api/analysis/{video.id}/queue")
        assert resp.status_code == 200
        body = resp.json()
        assert "task_id" in body

        db_session.expire_all()
        updated = db_session.query(Video).filter(Video.id == video.id).first()
        assert updated.status == "queued"

    def test_queue_same_video_twice_returns_existing_task(
        self, client: TestClient, db_session: Session
    ):
        video = self._make_video(db_session)
        resp1 = client.post(f"/api/analysis/{video.id}/queue")
        assert resp1.status_code == 200
        task_id_1 = resp1.json()["task_id"]

        resp2 = client.post(f"/api/analysis/{video.id}/queue")
        assert resp2.status_code == 200
        task_id_2 = resp2.json()["task_id"]

        assert task_id_1 == task_id_2
