"""Worker 邏輯測試"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from app.database import Classification, Summary, TaskQueue, Transcript, Video


class TestWorkerRecovery:
    def test_recover_interrupted_tasks(self, db_session, sample_video):
        """Worker 啟動時將 processing 狀態的任務重設為 pending"""
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
            status="processing",
            started_at=datetime.utcnow(),
        )
        sample_video.status = "processing"
        db_session.add(task)
        db_session.commit()

        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from worker import _recover_interrupted_tasks

        _recover_interrupted_tasks(db_session)

        db_session.refresh(task)
        db_session.refresh(sample_video)
        assert task.status == "pending"
        assert task.started_at is None
        assert sample_video.status == "queued"

    def test_recover_no_interrupted_tasks(self, db_session, sample_video):
        """無中斷任務時不改變任何狀態"""
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
            status="pending",
        )
        db_session.add(task)
        db_session.commit()

        from worker import _recover_interrupted_tasks

        _recover_interrupted_tasks(db_session)

        db_session.refresh(task)
        assert task.status == "pending"


class TestWorkerPickTask:
    def test_pick_highest_priority(self, db_session):
        """應取出優先級最高（數值最小）的任務"""
        vids = []
        for i, pri in enumerate([8, 1, 5]):
            v = Video(
                id=uuid.uuid4().hex,
                filename=f"v{i}.mp4",
                original_filename=f"v{i}.mp4",
                file_path=f"/p/v{i}.mp4",
                source="local_scan",
                file_size=100,
            )
            db_session.add(v)
            vids.append((v.id, pri))
        db_session.commit()

        for vid_id, pri in vids:
            db_session.add(TaskQueue(id=uuid.uuid4().hex, video_id=vid_id, priority=pri))
        db_session.commit()

        from worker import _pick_next_task

        task = _pick_next_task(db_session)
        assert task.priority == 1

    def test_pick_returns_none_when_empty(self, db_session):
        """佇列空時回傳 None"""
        from worker import _pick_next_task

        assert _pick_next_task(db_session) is None

    def test_pick_ignores_non_pending(self, db_session, sample_video):
        """不取出 processing/done/failed 的任務"""
        for status in ["processing", "done", "failed", "cancelled"]:
            db_session.add(
                TaskQueue(
                    id=uuid.uuid4().hex,
                    video_id=sample_video.id,
                    status=status,
                )
            )
        db_session.commit()

        from worker import _pick_next_task

        assert _pick_next_task(db_session) is None


class TestWorkerHandleFailure:
    def test_failure_increments_retry(self, db_session, sample_video):
        """失敗時 retry_count 增加"""
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
            status="processing",
            retry_count=0,
            max_retries=3,
        )
        db_session.add(task)
        db_session.commit()

        from worker import _handle_failure

        _handle_failure(task, sample_video, Exception("test error"), db_session)

        db_session.refresh(task)
        assert task.retry_count == 1
        assert task.error_message == "test error"
        assert task.status == "pending"  # 還未達最大重試次數

    def test_failure_marks_failed_after_max_retries(self, db_session, sample_video):
        """達到最大重試次數後標記為 failed"""
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
            status="processing",
            retry_count=2,
            max_retries=3,
        )
        db_session.add(task)
        db_session.commit()

        from worker import _handle_failure

        _handle_failure(task, sample_video, Exception("final failure"), db_session)

        db_session.refresh(task)
        db_session.refresh(sample_video)
        assert task.status == "failed"
        assert sample_video.status == "failed"
        assert "final failure" in sample_video.error_message


class TestProcessTask:
    def test_process_task_full_pipeline(self, db_session, tmp_path):
        """完整分析流程：音頻提取 → 轉錄 → 分析 → 儲存結果"""
        # 建立真實存在的假影片檔案
        video_file = tmp_path / "real.mp4"
        video_file.write_bytes(b"\x00" * 100)

        video = Video(
            id=uuid.uuid4().hex,
            filename="real.mp4",
            original_filename="real.mp4",
            file_path=str(video_file),
            source="local_scan",
            file_size=100,
            status="processing",
        )
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=video.id,
            status="processing",
        )
        db_session.add_all([video, task])
        db_session.commit()

        audio_file = tmp_path / "temp.mp3"
        audio_file.write_bytes(b"\x00" * 50)

        with (
            patch("worker.extract_audio", return_value=audio_file) as mock_extract,
            patch("worker.transcribe", return_value=("測試逐字稿", [])) as mock_transcribe,
            patch(
                "worker.analyze_all",
                return_value=(
                    "摘要",
                    ["重點一", "重點二"],
                    "占星學 (Astrology)",
                    0.9,
                    [{"question": "Q", "answer": "A"}],
                ),
            ) as mock_analyze_all,
            patch(
                "worker.generate_deep_content",
                return_value=("## 核心概念\n測試", ""),
            ),
            patch("worker.cleanup_audio") as mock_cleanup,
        ):
            from worker import _process_task

            _process_task(task, db_session)

        # 驗證呼叫順序
        mock_extract.assert_called_once()
        mock_transcribe.assert_called_once_with(audio_file, progress_callback=ANY)
        mock_analyze_all.assert_called_once_with("測試逐字稿")
        mock_cleanup.assert_called_once_with(audio_file)

        # 驗證資料庫結果
        db_session.refresh(video)
        db_session.refresh(task)
        assert video.status == "completed"
        assert task.status == "done"

        transcript = db_session.query(Transcript).filter_by(video_id=video.id).first()
        assert transcript.content == "測試逐字稿"

        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        assert summary.summary == "摘要"
        assert json.loads(summary.key_points) == ["重點一", "重點二"]

        cls = db_session.query(Classification).filter_by(video_id=video.id).first()
        assert cls.category == "占星學 (Astrology)"
        assert abs(cls.confidence - 0.9) < 0.001

    def test_process_task_missing_video_file(self, db_session, tmp_path):
        """影片檔案不存在時拋出 FileNotFoundError"""
        video = Video(
            id=uuid.uuid4().hex,
            filename="missing.mp4",
            original_filename="missing.mp4",
            file_path=str(tmp_path / "missing.mp4"),  # 不存在
            source="local_scan",
            file_size=100,
        )
        task = TaskQueue(id=uuid.uuid4().hex, video_id=video.id)
        db_session.add_all([video, task])
        db_session.commit()

        from worker import _process_task

        with pytest.raises(FileNotFoundError):
            _process_task(task, db_session)

    def test_process_task_cleans_up_audio_on_error(self, db_session, tmp_path):
        """即使分析失敗，也要清理暫存音頻"""
        video_file = tmp_path / "err.mp4"
        video_file.write_bytes(b"\x00" * 50)
        audio_file = tmp_path / "temp.mp3"
        audio_file.write_bytes(b"\x00" * 50)

        video = Video(
            id=uuid.uuid4().hex,
            filename="err.mp4",
            original_filename="err.mp4",
            file_path=str(video_file),
            source="local_scan",
            file_size=50,
        )
        task = TaskQueue(id=uuid.uuid4().hex, video_id=video.id)
        db_session.add_all([video, task])
        db_session.commit()

        with (
            patch("worker.extract_audio", return_value=audio_file),
            patch("worker.transcribe", side_effect=Exception("API error")),
            patch("worker.cleanup_audio") as mock_cleanup,
        ):
            from worker import _process_task

            with pytest.raises(Exception, match="API error"):
                _process_task(task, db_session)

            mock_cleanup.assert_called_once_with(audio_file)

    def test_process_task_updates_existing_results(self, db_session, tmp_path):
        """重新分析時更新現有逐字稿/摘要/分類，不建立重複記錄"""
        video_file = tmp_path / "rerun.mp4"
        video_file.write_bytes(b"\x00" * 100)
        audio_file = tmp_path / "rerun.mp3"
        audio_file.write_bytes(b"\x00" * 50)

        video = Video(
            id=uuid.uuid4().hex,
            filename="rerun.mp4",
            original_filename="rerun.mp4",
            file_path=str(video_file),
            source="local_scan",
            file_size=100,
        )
        db_session.add(video)
        db_session.flush()

        # 先建立舊結果
        db_session.add(Transcript(id=uuid.uuid4().hex, video_id=video.id, content="舊逐字稿"))
        db_session.add(
            Summary(id=uuid.uuid4().hex, video_id=video.id, summary="舊摘要", key_points="[]")
        )
        db_session.add(
            Classification(
                id=uuid.uuid4().hex,
                video_id=video.id,
                category="未分類 (Uncategorized)",
                confidence=0.1,
            )
        )
        task = TaskQueue(id=uuid.uuid4().hex, video_id=video.id)
        db_session.add(task)
        db_session.commit()

        with (
            patch("worker.extract_audio", return_value=audio_file),
            patch("worker.transcribe", return_value=("新逐字稿", [])),
            patch(
                "worker.analyze_all",
                return_value=(
                    "新摘要",
                    ["新重點"],
                    "風水 (Feng Shui)",
                    0.95,
                    [{"question": "Q", "answer": "A"}],
                ),
            ),
            patch("worker.generate_deep_content", return_value=("## 核心概念\n新內容", "")),
            patch("worker.cleanup_audio"),
        ):
            from worker import _process_task

            _process_task(task, db_session)

        # 確認只有一筆記錄（更新而非新增）
        assert db_session.query(Transcript).filter_by(video_id=video.id).count() == 1
        assert db_session.query(Summary).filter_by(video_id=video.id).count() == 1
        assert db_session.query(Classification).filter_by(video_id=video.id).count() == 1

        # 逐字稿已存在時，智慧跳過 Whisper，保留舊逐字稿，但摘要/分類更新
        transcript = db_session.query(Transcript).filter_by(video_id=video.id).first()
        assert transcript.content == "舊逐字稿"  # Whisper 被跳過，內容不變
        summary = db_session.query(Summary).filter_by(video_id=video.id).first()
        assert summary.summary == "新摘要"  # GPT 重跑，摘要更新
