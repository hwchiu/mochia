"""
Worker Integration Tests
========================
These tests call _process_task() with the REAL analyze_all() and
generate_deep_content() service functions.  Only the HTTP client
(_get_client) and filesystem operations (extract_audio / cleanup_audio)
are mocked — every line of business logic in analyzer.py runs for real.

Why this matters
----------------
PR #36 changed analyze_all() from a 6-tuple to a 5-tuple but left
worker.py unpacking 6 values.  The existing test_worker.py tests missed
this because they patched "worker.analyze_all" entirely, cutting the
link between caller and callee.

These integration tests are immune to that class of bug: if analyze_all's
return type ever changes again and worker.py is not updated, the unpack
line in worker.py will raise ValueError here first.
"""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.database import Classification, Summary, TaskQueue, Transcript, Video

# ── shared GPT fixtures ────────────────────────────────────────────────────────

_ANALYZE_ALL_JSON = json.dumps(
    {
        "summary": "這是測試摘要，描述占星學的基礎知識，包含十二星座與行星的關係，以及它們對人類命運的影響方式。"
        * 3,
        "key_points": [
            {
                "theme": "星座基礎",
                "points": ["牡羊座代表火元素", "金牛座代表土元素", "雙子座代表風元素"],
            },
            {
                "theme": "行星影響",
                "points": ["太陽代表自我意識", "月亮代表情感需求", "上升星座代表外在形象"],
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
        "study_notes": "## 核心概念\n占星學是古老的學問。\n\n## 重要術語\n星座、行星、上升點\n\n## 學習重點\n- 十二星座的特性\n\n## 實踐建議\n每日觀察行星位置\n\n## 延伸思考\n天體如何影響人格發展？",
        "case_analysis": "NO_CASE_ANALYSIS",
    }
)


def _make_analyzer_client() -> MagicMock:
    """Return a fake AzureOpenAI client whose chat.completions.create yields:
    call 1 → analyze_all JSON
    call 2 → generate_deep_content JSON
    """
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content=_ANALYZE_ALL_JSON))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content=_DEEP_CONTENT_JSON))]),
    ]
    return client


# ── fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def video_and_task(db_session, tmp_path):
    """Video + matching TaskQueue, with a real (empty) file on disk."""
    video_file = tmp_path / "test_video.mp4"
    video_file.write_bytes(b"\x00" * 1024)

    vid_id = uuid.uuid4().hex
    video = Video(
        id=vid_id,
        filename="test_video.mp4",
        original_filename="test_video.mp4",
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
    db_session.refresh(video)
    db_session.refresh(task)
    return video, task


# ── tests ──────────────────────────────────────────────────────────────────────


class TestWorkerRealAnalyzeAll:
    """Integration: _process_task uses the real analyze_all() function."""

    def _run_task(self, task, db_session, tmp_path, analyzer_client):
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_bytes(b"\x00" * 512)
        with (
            patch("app.services.analyzer._get_client", return_value=analyzer_client),
            patch("worker.extract_audio", return_value=str(audio_file)),
            patch("worker.transcribe", return_value=("占星學測試逐字稿", [])),
            patch("worker.cleanup_audio"),
        ):
            from worker import _process_task

            _process_task(task, db_session)

    def test_video_status_becomes_completed(self, db_session, tmp_path, video_and_task):
        """After _process_task, video.status must be 'completed'."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        db_session.refresh(video)
        assert video.status == "completed"

    def test_transcript_written(self, db_session, tmp_path, video_and_task):
        """Transcript record must be created with the transcription text."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        transcript = db_session.query(Transcript).filter_by(video_id=video.id).first()
        assert transcript is not None
        assert "逐字稿" in transcript.content

    def test_summary_written_by_real_analyze_all(self, db_session, tmp_path, video_and_task):
        """Summary record must contain the GPT-returned summary text.

        Because we mock at _get_client level (not analyze_all level),
        any change in analyze_all's return tuple will surface here.
        """
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        assert summary is not None
        assert "測試摘要" in summary.summary

    def test_faq_written_by_real_analyze_all(self, db_session, tmp_path, video_and_task):
        """FAQ field must be valid JSON list from the GPT response."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        faq = json.loads(summary.faq)
        assert isinstance(faq, list)
        assert faq[0]["question"] == "什麼是占星學？"

    def test_key_points_written_as_json(self, db_session, tmp_path, video_and_task):
        """key_points must be valid JSON list of dicts with 'theme' and 'points' keys."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        kp = json.loads(summary.key_points)
        assert isinstance(kp, list)
        assert "theme" in kp[0]
        assert "points" in kp[0]

    def test_classification_written_by_real_analyze_all(self, db_session, tmp_path, video_and_task):
        """Classification record must reflect GPT-returned category and confidence."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        cls = db_session.query(Classification).filter_by(video_id=video.id).first()
        assert cls is not None
        assert cls.category == "占星學 (Astrology)"
        assert abs(float(cls.confidence) - 0.92) < 0.001

    def test_study_notes_written_by_real_generate_deep_content(
        self, db_session, tmp_path, video_and_task
    ):
        """study_notes field must be populated by real generate_deep_content()."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        assert summary.study_notes is not None
        assert "核心概念" in summary.study_notes

    def test_case_analysis_empty_when_no_case(self, db_session, tmp_path, video_and_task):
        """case_analysis must be None when GPT returns NO_CASE_ANALYSIS."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        assert summary.case_analysis is None

    def test_task_status_done_after_completion(self, db_session, tmp_path, video_and_task):
        """TaskQueue.status must be 'done' after successful processing."""
        video, task = video_and_task
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())
        db_session.refresh(task)
        assert task.status == "done"

    def test_gpt_called_exactly_twice(self, db_session, tmp_path, video_and_task):
        """Worker must make exactly 2 GPT calls: analyze_all + generate_deep_content."""
        video, task = video_and_task
        analyzer_client = _make_analyzer_client()
        self._run_task(task, db_session, tmp_path, analyzer_client)
        assert analyzer_client.chat.completions.create.call_count == 2

    def test_rerun_overwrites_existing_records(self, db_session, tmp_path, video_and_task):
        """Running _process_task twice must update records, not duplicate them."""
        video, task = video_and_task
        # First run
        task.status = "processing"
        db_session.commit()
        self._run_task(task, db_session, tmp_path, _make_analyzer_client())

        # Second run: reset task and use a different summary
        second_json = json.dumps(
            {
                "summary": "第二次分析的摘要，內容不同",
                "key_points": [{"theme": "新主題", "points": ["新說明"]}],
                "category": "風水 (Feng Shui)",
                "confidence": 0.85,
                "faq": [{"question": "問題A", "answer": "回答A"}],
            }
        )
        second_deep = json.dumps(
            {"study_notes": "## 新筆記\n新內容", "case_analysis": "NO_CASE_ANALYSIS"}
        )
        second_client = MagicMock()
        second_client.chat.completions.create.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=second_json))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=second_deep))]),
        ]
        task2 = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=video.id,
            status="processing",
            priority=5,
            retry_count=0,
            max_retries=3,
        )
        db_session.add(task2)
        db_session.commit()
        db_session.refresh(task2)
        self._run_task(task2, db_session, tmp_path, second_client)

        # Only one Summary record should exist
        assert db_session.query(Summary).filter_by(video_id=video.id).count() == 1
        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        assert "第二次分析" in summary.summary

        # Only one Classification record
        assert db_session.query(Classification).filter_by(video_id=video.id).count() == 1
        cls = db_session.query(Classification).filter_by(video_id=video.id).first()
        assert cls.category == "風水 (Feng Shui)"
