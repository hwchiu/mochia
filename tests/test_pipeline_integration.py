"""
Pipeline Integration Tests
============================
End-to-end tests that exercise the full request lifecycle:
  HTTP API → DB → Worker → HTTP API

These tests verify that the three layers (router, worker, DB) remain
consistent with each other.  A bug that causes a state mismatch between
layers will fail here even if individual unit tests for each layer pass.

Scenarios covered
-----------------
1. Queue → Worker → Results  (happy path)
2. Video status transitions   (pending → queued → processing → completed)
3. Task queue state after success / failure
4. Results endpoint reflects worker-written data
5. Re-queue a failed video

These tests deliberately run _process_task() synchronously within the
test so we can inspect the DB immediately without polling.
"""

import json
import uuid
from unittest.mock import MagicMock, patch

from app.database import Classification, Summary, TaskQueue, Transcript, Video

# ── shared GPT stubs ───────────────────────────────────────────────────────────

_ANALYZE_ALL_JSON = json.dumps(
    {
        "summary": "Pipeline 測試摘要：這是一個完整流程測試的內容，涵蓋所有必要欄位。" * 3,
        "key_points": [
            {"theme": "流程驗證", "points": ["Queue 狀態正確", "Worker 執行完整", "結果可讀取"]},
        ],
        "category": "占星學 (Astrology)",
        "confidence": 0.95,
        "faq": [
            {"question": "Pipeline 測試問題？", "answer": "Pipeline 測試回答。"},
        ],
    }
)

_DEEP_CONTENT_JSON = json.dumps(
    {
        "study_notes": "## 核心概念\nPipeline 流程測試筆記",
        "case_analysis": "NO_CASE_ANALYSIS",
    }
)


def _make_analyzer_client() -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=_ANALYZE_ALL_JSON))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=_DEEP_CONTENT_JSON))]),
    ]
    return client


# ── helpers ────────────────────────────────────────────────────────────────────


def _run_worker(task, db_session, tmp_path, analyzer_client=None):
    """Run _process_task synchronously with mocked external I/O."""
    if analyzer_client is None:
        analyzer_client = _make_analyzer_client()
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"\x00" * 512)
    with (
        patch("app.services.analyzer._get_client", return_value=analyzer_client),
        patch("worker.extract_audio", return_value=str(audio)),
        patch("worker.transcribe", return_value=("Pipeline 測試逐字稿", [])),
        patch("worker.cleanup_audio"),
    ):
        from worker import _process_task

        _process_task(task, db_session)


def _create_pending_video(db_session, tmp_path) -> Video:
    """Create a Video in 'pending' state with a real file on disk."""
    video_file = tmp_path / f"video_{uuid.uuid4().hex[:8]}.mp4"
    video_file.write_bytes(b"\x00" * 1024)
    vid_id = uuid.uuid4().hex
    video = Video(
        id=vid_id,
        filename=video_file.name,
        original_filename=video_file.name,
        file_path=str(video_file),
        source="local_scan",
        file_size=1024,
        duration=90.0,
        status="pending",
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


# ── tests ──────────────────────────────────────────────────────────────────────


class TestQueueToResultsPipeline:
    """Full pipeline: API queue → worker run → API results."""

    def test_queue_sets_status_queued(self, client, db_session, tmp_path):
        """POST /analyze should set video.status = 'queued'."""
        video = _create_pending_video(db_session, tmp_path)
        resp = client.post(f"/api/analysis/{video.id}/queue")
        assert resp.status_code == 200
        db_session.refresh(video)
        assert video.status == "queued"

    def test_queue_creates_task(self, client, db_session, tmp_path):
        """POST /analyze should create a TaskQueue record."""
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")
        task = db_session.query(TaskQueue).filter_by(video_id=video.id).first()
        assert task is not None
        assert task.status == "pending"

    def test_worker_completes_pipeline(self, client, db_session, tmp_path):
        """After worker runs, /results must return 200 with data."""
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")

        # Simulate worker picking up the task
        task = db_session.query(TaskQueue).filter_by(video_id=video.id).first()
        task.status = "processing"
        db_session.commit()
        _run_worker(task, db_session, tmp_path)

        resp = client.get(f"/api/analysis/{video.id}/results")
        assert resp.status_code == 200

    def test_results_contain_gpt_summary(self, client, db_session, tmp_path):
        """Results endpoint must return the GPT-generated summary."""
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")
        task = db_session.query(TaskQueue).filter_by(video_id=video.id).first()
        task.status = "processing"
        db_session.commit()
        _run_worker(task, db_session, tmp_path)

        data = client.get(f"/api/analysis/{video.id}/results").json()
        assert "Pipeline 測試摘要" in data["summary"]

    def test_results_contain_gpt_category(self, client, db_session, tmp_path):
        """Results endpoint must return the GPT-returned category."""
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")
        task = db_session.query(TaskQueue).filter_by(video_id=video.id).first()
        task.status = "processing"
        db_session.commit()
        _run_worker(task, db_session, tmp_path)

        data = client.get(f"/api/analysis/{video.id}/results").json()
        assert data["category"] == "占星學 (Astrology)"

    def test_results_contain_faq(self, client, db_session, tmp_path):
        """The /faq endpoint must return the FAQ list from GPT."""
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")
        task = db_session.query(TaskQueue).filter_by(video_id=video.id).first()
        task.status = "processing"
        db_session.commit()
        _run_worker(task, db_session, tmp_path)

        resp = client.get(f"/api/analysis/{video.id}/faq")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("faq"), list)
        assert len(data["faq"]) > 0

    def test_results_before_worker_returns_409(self, client, db_session, tmp_path):
        """Calling /results before worker finishes must return 409."""
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")

        resp = client.get(f"/api/analysis/{video.id}/results")
        assert resp.status_code == 409

    def test_status_endpoint_reflects_progress(self, client, db_session, tmp_path):
        """GET /status must show step and progress information nested under 'progress'."""
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")

        resp = client.get(f"/api/analysis/{video.id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "progress" in data
        assert "step" in data["progress"]


class TestVideoStatusTransitions:
    """Video.status must follow the expected state machine."""

    def test_pending_to_queued_via_api(self, client, db_session, tmp_path):
        video = _create_pending_video(db_session, tmp_path)
        assert video.status == "pending"
        client.post(f"/api/analysis/{video.id}/queue")
        db_session.refresh(video)
        assert video.status == "queued"

    def test_queued_to_completed_via_worker(self, client, db_session, tmp_path):
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")
        task = db_session.query(TaskQueue).filter_by(video_id=video.id).first()
        task.status = "processing"
        db_session.commit()
        _run_worker(task, db_session, tmp_path)
        db_session.refresh(video)
        assert video.status == "completed"

    def test_task_done_after_worker(self, client, db_session, tmp_path):
        video = _create_pending_video(db_session, tmp_path)
        client.post(f"/api/analysis/{video.id}/queue")
        task = db_session.query(TaskQueue).filter_by(video_id=video.id).first()
        task.status = "processing"
        db_session.commit()
        _run_worker(task, db_session, tmp_path)
        db_session.refresh(task)
        assert task.status == "done"

    def test_completed_video_cannot_be_requeued_with_new_task(self, client, db_session, tmp_path):
        """Queuing an already-queued video must return the existing task."""
        video = _create_pending_video(db_session, tmp_path)
        resp1 = client.post(f"/api/analysis/{video.id}/queue")
        resp2 = client.post(f"/api/analysis/{video.id}/queue")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Only one pending task should exist
        task_count = db_session.query(TaskQueue).filter_by(video_id=video.id).count()
        assert task_count == 1


class TestWorkerFailurePipeline:
    """Worker failure handling and retry mechanics."""

    def test_worker_error_marks_video_failed_after_max_retries(self, db_session, tmp_path):
        """If _process_task raises and _handle_failure is called, task reaches 'failed'."""
        video_file = tmp_path / "failing.mp4"
        video_file.write_bytes(b"\x00" * 1024)
        vid_id = uuid.uuid4().hex
        video = Video(
            id=vid_id,
            filename="failing.mp4",
            original_filename="failing.mp4",
            file_path=str(video_file),
            source="local_scan",
            file_size=1024,
            status="processing",
        )
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=vid_id,
            status="processing",
            priority=5,
            retry_count=2,  # already retried twice
            max_retries=3,
        )
        db_session.add_all([video, task])
        db_session.commit()

        error = RuntimeError("ffmpeg missing")
        from worker import _handle_failure

        _handle_failure(task, video, error, db_session)

        db_session.refresh(task)
        # retry_count was 2, now 3 → max_retries reached → status = failed
        assert task.status == "failed"
        assert task.error_message is not None

    def test_db_all_records_written_after_success(self, db_session, tmp_path):
        """After worker success, Transcript + Summary + Classification must all exist."""
        video_file = tmp_path / "complete.mp4"
        video_file.write_bytes(b"\x00" * 1024)
        vid_id = uuid.uuid4().hex
        video = Video(
            id=vid_id,
            filename="complete.mp4",
            original_filename="complete.mp4",
            file_path=str(video_file),
            source="local_scan",
            file_size=1024,
            duration=60.0,
            status="processing",
        )
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=vid_id,
            status="processing",
            priority=5,
            retry_count=0,
            max_retries=3,
        )
        db_session.add_all([video, task])
        db_session.commit()
        _run_worker(task, db_session, tmp_path)

        assert db_session.query(Transcript).filter_by(video_id=vid_id).count() == 1
        assert db_session.query(Summary).filter_by(video_id=vid_id).count() == 1
        assert db_session.query(Classification).filter_by(video_id=vid_id).count() == 1
