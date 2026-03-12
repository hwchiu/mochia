"""Integration tests for video cascade delete behavior."""

import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import Classification, Summary, Transcript, Video, VideoNote


class TestVideoCascadeDelete:
    """Verify that deleting a video removes all related records (FK CASCADE)."""

    def _make_video(self, db: Session, status: str = "pending") -> Video:
        v = Video(
            id=uuid.uuid4().hex,
            filename=f"cascade_{uuid.uuid4().hex}.mp4",
            original_filename="cascade.mp4",
            file_path="/fake/cascade.mp4",
            source="local_scan",
            file_size=1024,
            status=status,
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        return v

    def test_delete_video_removes_transcript(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session)
        transcript = Transcript(
            id=uuid.uuid4().hex,
            video_id=video.id,
            content="逐字稿內容",
        )
        db_session.add(transcript)
        db_session.commit()

        resp = client.delete(f"/api/videos/{video.id}")
        assert resp.status_code == 200

        remaining = db_session.query(Transcript).filter(Transcript.video_id == video.id).all()
        assert len(remaining) == 0

    def test_delete_video_removes_summary(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session)
        summary = Summary(
            id=uuid.uuid4().hex,
            video_id=video.id,
            summary="摘要文字",
            key_points=json.dumps(["重點1", "重點2"], ensure_ascii=False),
        )
        db_session.add(summary)
        db_session.commit()

        resp = client.delete(f"/api/videos/{video.id}")
        assert resp.status_code == 200

        remaining = db_session.query(Summary).filter(Summary.video_id == video.id).all()
        assert len(remaining) == 0

    def test_delete_video_removes_classification(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session)
        cls = Classification(
            id=uuid.uuid4().hex,
            video_id=video.id,
            category="占星學 (Astrology)",
            confidence=0.9,
        )
        db_session.add(cls)
        db_session.commit()

        resp = client.delete(f"/api/videos/{video.id}")
        assert resp.status_code == 200

        remaining = (
            db_session.query(Classification).filter(Classification.video_id == video.id).all()
        )
        assert len(remaining) == 0

    def test_delete_video_removes_note(self, client: TestClient, db_session: Session):
        video = self._make_video(db_session)
        note = VideoNote(
            id=uuid.uuid4().hex,
            video_id=video.id,
            content="個人筆記",
        )
        db_session.add(note)
        db_session.commit()

        resp = client.delete(f"/api/videos/{video.id}")
        assert resp.status_code == 200

        remaining = db_session.query(VideoNote).filter(VideoNote.video_id == video.id).all()
        assert len(remaining) == 0

    def test_delete_video_removes_all_related_records(
        self, client: TestClient, db_session: Session
    ):
        """Full cascade: transcript + summary + classification all removed together."""
        video = self._make_video(db_session, status="completed")
        vid_id = video.id

        db_session.add(Transcript(id=uuid.uuid4().hex, video_id=vid_id, content="text"))
        db_session.add(
            Summary(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                summary="summary",
                key_points="[]",
            )
        )
        db_session.add(
            Classification(id=uuid.uuid4().hex, video_id=vid_id, category="Test", confidence=0.8)
        )
        db_session.commit()

        resp = client.delete(f"/api/videos/{vid_id}")
        assert resp.status_code == 200

        assert db_session.query(Transcript).filter(Transcript.video_id == vid_id).count() == 0
        assert db_session.query(Summary).filter(Summary.video_id == vid_id).count() == 0
        assert (
            db_session.query(Classification).filter(Classification.video_id == vid_id).count() == 0
        )

    def test_delete_nonexistent_video_returns_404(self, client: TestClient):
        resp = client.delete("/api/videos/does_not_exist")
        assert resp.status_code == 404
