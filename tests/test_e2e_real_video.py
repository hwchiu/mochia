"""
E2E Tests with Real MP4 File
=============================
These tests simulate the complete user flow using a genuine FFmpeg-generated
MP4 file. Unlike unit/integration tests that use fake binary blobs, here:

  • FFmpeg runs for real  (audio extraction, duration detection)
  • The file is uploaded via the real HTTP endpoint (multipart POST)
  • Only external network calls are mocked:
      - Whisper transcription  → patched at _transcribe_single
      - Azure OpenAI chat      → patched at _get_client

Why this matters
----------------
The blob-file tests cannot catch FFmpeg failures, malformed audio paths,
file-size/duration detection bugs, or upload handler regressions.
This suite catches all of those.

Prerequisites
-------------
  • ffmpeg must be installed and on PATH (CI: already required by the app)
  • uploads/ directory must be writable (created by app/config.py)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, TaskQueue, get_db

# ── Fake GPT responses (same as integration tests) ────────────────────────────

_TRANSCRIPT_TEXT = (
    "占星學是研究天體位置與人類事務關係的古老學問。"
    "十二星座各有其特性，行星運行影響著我們的生活。"
    "今天我們將深入探討牡羊座、金牛座和雙子座的基本特質。"
)
_TRANSCRIPT_SEGMENTS = [
    {"start": 0.0, "end": 1.0, "text": "占星學是研究天體位置與人類事務關係的古老學問。"},
    {"start": 1.0, "end": 2.0, "text": "十二星座各有其特性，行星運行影響著我們的生活。"},
]

_ANALYZE_ALL_JSON = json.dumps(
    {
        "summary": (
            "本影片介紹占星學基礎知識，涵蓋十二星座的基本特質，"
            "以及行星對人類命運的影響方式。主要探討火象星座的特性。"
        ),
        "key_points": [
            {
                "theme": "星座基礎",
                "points": ["牡羊座代表火元素", "金牛座代表土元素"],
            },
            {
                "theme": "行星影響",
                "points": ["太陽代表自我意識", "月亮代表情感需求"],
            },
        ],
        "category": "占星學 (Astrology)",
        "confidence": 0.92,
        "faq": [
            {"question": "什麼是占星學？", "answer": "研究天體位置對人類事務影響的古老學問。"},
            {"question": "有幾個星座？", "answer": "黃道帶共有十二個主要星座。"},
        ],
    }
)

_DEEP_CONTENT_JSON = json.dumps(
    {
        "study_notes": (
            "## 核心概念\n占星學是古老的學問。\n\n"
            "## 重要術語\n星座、行星、上升點\n\n"
            "## 學習重點\n- 十二星座的特性\n\n"
            "## 實踐建議\n每日觀察行星位置\n\n"
            "## 延伸思考\n天體如何影響人格發展？"
        ),
        "case_analysis": "NO_CASE_ANALYSIS",
    }
)


def _make_analyzer_client() -> MagicMock:
    """Fake AzureOpenAI client: returns analyze_all JSON then deep_content JSON."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=_ANALYZE_ALL_JSON))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=_DEEP_CONTENT_JSON))]),
    ]
    return client


# ── Session-scoped real MP4 fixture ───────────────────────────────────────────


@pytest.fixture(scope="module")
def real_mp4(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a real 2-second silent black MP4 using FFmpeg (once per module)."""
    out = tmp_path_factory.mktemp("e2e_mp4") / "test_e2e.mp4"
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=black:size=320x240:rate=1",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-t",
                "2",
                "-shortest",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                str(out),
            ],
            capture_output=True,
        )
    except FileNotFoundError:
        pytest.skip("FFmpeg not found on PATH — skipping E2E real-video tests")
    if result.returncode != 0:
        pytest.skip(f"FFmpeg not available or failed: {result.stderr.decode()[:200]}")
    assert out.exists() and out.stat().st_size > 0, "FFmpeg produced empty file"
    return out


# ── Module-scoped E2E environment (run once, verify many) ─────────────────────


@pytest.fixture(scope="module")
def e2e(real_mp4: Path) -> dict[str, Any]:
    """
    Full E2E run (module-scoped, executed once):
      1. Upload real MP4 via API
      2. Queue for analysis
      3. Run _process_task (real FFmpeg, mocked Whisper + Azure)
      4. Collect all endpoint responses into a state dict

    Returns a dict with keys: video_id, upload, queue, results, faq,
    status, video, search, db_session.
    """
    # Isolated in-memory DB
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    import app.routers.batch as batch_module
    from app import app

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    original_factory = batch_module._scan_session_factory
    batch_module._scan_session_factory = Session
    app.dependency_overrides[get_db] = override_get_db

    state: dict[str, Any] = {}
    uploaded_file_path: Path | None = None

    with TestClient(app, raise_server_exceptions=True) as client:
        # ── Step 1: Upload real MP4 ──────────────────────────────────────
        with open(real_mp4, "rb") as f:
            resp = client.post(
                "/api/videos/upload",
                files={"file": ("test_e2e.mp4", f, "video/mp4")},
            )
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        upload_data = resp.json()
        video_id: str = upload_data["id"]
        state["video_id"] = video_id
        state["upload"] = upload_data

        # Track uploaded file for cleanup
        if upload_data.get("file_path"):
            uploaded_file_path = Path(upload_data["file_path"])

        # ── Step 2: Queue for analysis ───────────────────────────────────
        resp = client.post(f"/api/analysis/{video_id}/queue")
        assert resp.status_code == 200, f"Queue failed: {resp.text}"
        state["queue"] = resp.json()

        # ── Step 3: Run _process_task (real FFmpeg, mock external APIs) ──
        db = Session()
        task = db.query(TaskQueue).filter_by(video_id=video_id).first()
        assert task is not None, "TaskQueue record not created"
        task.status = "processing"
        db.commit()

        with (
            patch(
                "app.services.transcriber._transcribe_single",
                return_value=(_TRANSCRIPT_TEXT, _TRANSCRIPT_SEGMENTS),
            ),
            patch(
                "app.services.analyzer._get_client",
                return_value=_make_analyzer_client(),
            ),
        ):
            from worker import _process_task

            _process_task(task, db)

        db.close()

        # ── Step 4: Collect all API responses ────────────────────────────
        state["results"] = client.get(f"/api/analysis/{video_id}/results").json()
        state["faq"] = client.get(f"/api/analysis/{video_id}/faq").json()
        state["status"] = client.get(f"/api/analysis/{video_id}/status").json()
        state["video"] = client.get(f"/api/videos/{video_id}").json()
        state["study_notes"] = client.get(f"/api/analysis/{video_id}/study-notes").json()
        # Use /api/videos/?search= (SQLAlchemy ilike) — works with in-memory DB.
        # FTS5 search connects to the real DB file and cannot be tested here.
        state["search"] = client.get("/api/videos/?search=test_e2e").json()
        state["search_status"] = client.get("/api/videos/?status=completed").json()

    # Cleanup
    app.dependency_overrides.clear()
    batch_module._scan_session_factory = original_factory

    if uploaded_file_path and uploaded_file_path.exists():
        uploaded_file_path.unlink(missing_ok=True)

    Base.metadata.drop_all(bind=engine)
    engine.dispose()

    return state


# ── Test class ────────────────────────────────────────────────────────────────


class TestE2ERealVideo:
    """All tests share a single E2E run via the `e2e` fixture."""

    # ── Upload ────────────────────────────────────────────────────────────────

    def test_upload_returns_video_id(self, e2e: dict[str, Any]) -> None:
        """Upload must return a video record with a non-empty id."""
        assert "id" in e2e["upload"]
        assert len(e2e["upload"]["id"]) > 0

    def test_upload_detects_duration(self, e2e: dict[str, Any]) -> None:
        """FFmpeg duration detection must return ~2 seconds for the test MP4."""
        duration = e2e["upload"].get("duration")
        assert duration is not None, "duration field missing"
        assert 1.0 <= float(duration) <= 4.0, f"Unexpected duration: {duration}"

    def test_upload_detects_file_size(self, e2e: dict[str, Any]) -> None:
        """Uploaded file size must be positive (real file, not empty blob)."""
        size = e2e["upload"].get("file_size", 0)
        assert size > 0, "file_size is 0 — real file not written"

    def test_upload_sets_status_pending(self, e2e: dict[str, Any]) -> None:
        """Freshly uploaded video must have 'pending' status."""
        assert e2e["upload"].get("status") == "pending"

    def test_upload_records_original_filename(self, e2e: dict[str, Any]) -> None:
        """Original filename must be preserved in the DB record."""
        assert e2e["upload"].get("original_filename") == "test_e2e.mp4"

    # ── Queue ─────────────────────────────────────────────────────────────────

    def test_queue_returns_task_id(self, e2e: dict[str, Any]) -> None:
        """Queuing a video must return a task_id."""
        assert (
            "task_id" in e2e["queue"] or "id" in e2e["queue"]
        ), f"No task_id in queue response: {e2e['queue']}"

    # ── Transcript (FFmpeg ran for real → audio extracted → mock Whisper) ────

    def test_transcript_written_to_db(self, e2e: dict[str, Any]) -> None:
        """After analysis, transcript must be present in /results."""
        assert e2e["results"].get("transcript"), "transcript missing from results"

    def test_transcript_contains_fake_text(self, e2e: dict[str, Any]) -> None:
        """Transcript must contain the text returned by our mock Whisper."""
        transcript = e2e["results"].get("transcript", "")
        assert "占星學" in transcript, f"Expected mock transcript text, got: {transcript[:100]}"

    # ── Summary & Key Points ──────────────────────────────────────────────────

    def test_summary_written(self, e2e: dict[str, Any]) -> None:
        """Summary must be non-empty."""
        assert e2e["results"].get("summary"), "summary missing from results"

    def test_key_points_written(self, e2e: dict[str, Any]) -> None:
        """Key points must be a non-empty list."""
        kp = e2e["results"].get("key_points")
        assert isinstance(kp, list) and len(kp) > 0, f"key_points missing or empty: {kp}"

    # ── Classification ────────────────────────────────────────────────────────

    def test_classification_category(self, e2e: dict[str, Any]) -> None:
        """Category must match the mock GPT response."""
        assert e2e["results"].get("category") == "占星學 (Astrology)"

    def test_classification_confidence(self, e2e: dict[str, Any]) -> None:
        """Confidence must be a float between 0 and 1."""
        conf = e2e["results"].get("confidence")
        assert conf is not None, "confidence missing"
        assert 0.0 <= float(conf) <= 1.0, f"confidence out of range: {conf}"

    # ── FAQ (separate endpoint) ───────────────────────────────────────────────

    def test_faq_endpoint_returns_list(self, e2e: dict[str, Any]) -> None:
        """GET /faq must return a list."""
        faq = e2e["faq"].get("faq")
        assert isinstance(faq, list), f"faq not a list: {e2e['faq']}"

    def test_faq_has_question_and_answer_fields(self, e2e: dict[str, Any]) -> None:
        """Each FAQ item must have 'question' and 'answer' fields."""
        faq = e2e["faq"].get("faq", [])
        assert len(faq) > 0, "FAQ list is empty"
        for item in faq:
            assert "question" in item and "answer" in item, f"FAQ item malformed: {item}"

    # ── Study Notes (deep content) ────────────────────────────────────────────

    def test_study_notes_written(self, e2e: dict[str, Any]) -> None:
        """study_notes must be non-empty after analysis (at /study_notes endpoint)."""
        notes = e2e["study_notes"].get("study_notes")
        assert notes, f"study_notes missing or empty: {e2e['study_notes']}"

    # ── Video Status ──────────────────────────────────────────────────────────

    def test_video_status_completed(self, e2e: dict[str, Any]) -> None:
        """Video status must be 'completed' after successful analysis."""
        assert (
            e2e["video"].get("status") == "completed"
        ), f"Video status: {e2e['video'].get('status')}"

    def test_status_endpoint_has_progress(self, e2e: dict[str, Any]) -> None:
        """GET /status must include a 'progress' block."""
        assert "progress" in e2e["status"], f"'progress' missing: {e2e['status']}"

    # ── List / Filter (SQLAlchemy ilike — works with in-memory DB) ────────────

    def test_search_by_filename(self, e2e: dict[str, Any]) -> None:
        """GET /api/videos/?search= must find the uploaded video by filename."""
        items = e2e["search"].get("items", [])
        ids = [v.get("id") for v in items]
        assert (
            e2e["video_id"] in ids
        ), f"Video {e2e['video_id']} not found in filename search. ids={ids}"

    def test_list_completed_videos(self, e2e: dict[str, Any]) -> None:
        """GET /api/videos/?status=completed must include the analyzed video."""
        items = e2e["search_status"].get("items", [])
        ids = [v.get("id") for v in items]
        assert e2e["video_id"] in ids, f"Completed video not in status=completed list. ids={ids}"


# ── Delete flow (separate function-scoped test) ───────────────────────────────


class TestE2EDeleteFlow:
    """Upload a video then delete it — verifies file + DB cleanup."""

    def test_delete_removes_video_and_returns_404(self, real_mp4: Path, db_engine, client) -> None:
        """After DELETE, subsequent GET must return 404."""
        # Upload
        with open(real_mp4, "rb") as f:
            resp = client.post(
                "/api/videos/upload",
                files={"file": ("to_delete.mp4", f, "video/mp4")},
            )
        assert resp.status_code == 200
        video_id = resp.json()["id"]
        uploaded_path = Path(resp.json()["file_path"])

        # Delete
        del_resp = client.delete(f"/api/videos/{video_id}")
        assert del_resp.status_code in (200, 204), f"DELETE failed: {del_resp.text}"

        # Verify 404
        get_resp = client.get(f"/api/videos/{video_id}")
        assert get_resp.status_code == 404

        # Verify file cleaned up
        assert not uploaded_path.exists(), f"Uploaded file still exists: {uploaded_path}"
