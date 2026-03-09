"""CLI 工具測試"""
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

from app.database import Video, TaskQueue


class TestCLIScan:
    def test_scan_nonexistent_path(self, db_session, tmp_path):
        """不存在的路徑應退出並顯示錯誤"""
        import cli
        args = MagicMock()
        args.path = str(tmp_path / "nonexistent")
        args.no_queue = True

        with pytest.raises(SystemExit):
            cli.cmd_scan(args)

    def test_scan_registers_videos(self, db_session, tmp_path):
        """掃描目錄登錄新影片"""
        for name in ["a.mp4", "b.mkv", "sub/c.mp4"]:
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"\x00" * 100)

        import cli
        args = MagicMock()
        args.path = str(tmp_path)
        args.no_queue = True

        with patch("cli._get_db", return_value=db_session), \
             patch("cli.get_video_duration", return_value=60.0):
            cli.cmd_scan(args)

        count = db_session.query(Video).count()
        assert count == 3

    def test_scan_skips_duplicates(self, db_session, tmp_path):
        """重複掃描不登錄已存在影片"""
        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00" * 100)

        import cli
        args = MagicMock()
        args.path = str(tmp_path)
        args.no_queue = True

        with patch("cli._get_db", return_value=db_session), \
             patch("cli.get_video_duration", return_value=60.0):
            cli.cmd_scan(args)
            cli.cmd_scan(args)  # 第二次掃描

        # 仍然只有 1 筆
        count = db_session.query(Video).count()
        assert count == 1

    def test_scan_supports_subdirectories(self, db_session, tmp_path):
        """遞迴掃描子目錄"""
        for depth in range(3):
            subdir = tmp_path / "/".join([f"level{i}" for i in range(depth + 1)])
            subdir.mkdir(parents=True, exist_ok=True)
            (subdir / f"video_{depth}.mp4").write_bytes(b"\x00" * 50)

        import cli
        args = MagicMock()
        args.path = str(tmp_path)
        args.no_queue = True

        with patch("cli._get_db", return_value=db_session), \
             patch("cli.get_video_duration", return_value=None):
            cli.cmd_scan(args)

        assert db_session.query(Video).count() == 3


class TestCLIQueueAll:
    def test_queue_all_pending_videos(self, db_session):
        """queue-all 將所有 pending 影片加入佇列"""
        for i in range(3):
            db_session.add(Video(
                id=uuid.uuid4().hex, filename=f"q{i}.mp4",
                original_filename=f"q{i}.mp4", file_path=f"/p/q{i}.mp4",
                source="local_scan", file_size=100, status="pending",
            ))
        db_session.commit()

        import cli
        args = MagicMock()
        with patch("cli._get_db", return_value=db_session):
            cli.cmd_queue_all(args)

        queued_count = db_session.query(TaskQueue).filter_by(status="pending").count()
        assert queued_count == 3

        videos = db_session.query(Video).all()
        assert all(v.status == "queued" for v in videos)

    def test_queue_all_skips_non_pending(self, db_session):
        """queue-all 不影響非 pending 狀態的影片"""
        for status in ["queued", "processing", "completed", "failed"]:
            db_session.add(Video(
                id=uuid.uuid4().hex, filename=f"{status}.mp4",
                original_filename=f"{status}.mp4", file_path=f"/p/{status}.mp4",
                source="local_scan", file_size=100, status=status,
            ))
        db_session.commit()

        import cli
        args = MagicMock()
        with patch("cli._get_db", return_value=db_session):
            cli.cmd_queue_all(args)

        # 沒有新的 pending 任務被加入
        task_count = db_session.query(TaskQueue).count()
        assert task_count == 0


class TestCLIQueueOne:
    def test_queue_single_video(self, db_session, db_session_nc, sample_video):
        import cli
        args = MagicMock()
        args.video_id = sample_video.id
        args.priority = 3

        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_queue(args)

        task = db_session.query(TaskQueue).filter_by(video_id=sample_video.id).first()
        assert task is not None
        assert task.priority == 3
        db_session.refresh(sample_video)
        assert sample_video.status == "queued"

    def test_queue_nonexistent_video(self, db_session, db_session_nc):
        import cli
        args = MagicMock()
        args.video_id = "nonexistent_id"

        with patch("cli._get_db", return_value=db_session_nc), \
             pytest.raises(SystemExit):
            cli.cmd_queue(args)


class TestCLIStatus:
    def test_status_output(self, db_session, db_session_nc, sample_video, capsys):
        import cli
        args = MagicMock()
        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_status(args)

        captured = capsys.readouterr()
        assert "pending" in captured.out
        assert "1" in captured.out

    def test_status_shows_processing(self, db_session, db_session_nc, capsys):
        """有處理中任務時顯示詳情"""
        vid = Video(id=uuid.uuid4().hex, filename="proc.mp4", original_filename="proc.mp4",
                    file_path="/p/proc.mp4", source="local_scan", file_size=100,
                    status="processing")
        db_session.add(vid)
        db_session.commit()

        from datetime import datetime
        task = TaskQueue(id=uuid.uuid4().hex, video_id=vid.id, status="processing",
                         started_at=datetime.utcnow())
        db_session.add(task)
        db_session.commit()

        import cli
        args = MagicMock()
        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_status(args)

        captured = capsys.readouterr()
        assert "proc.mp4" in captured.out


class TestCLIRetry:
    def test_retry_failed_tasks(self, db_session, db_session_nc):
        """retry 將失敗任務重設為 pending"""
        vid = Video(id=uuid.uuid4().hex, filename="fail.mp4", original_filename="fail.mp4",
                    file_path="/p/fail.mp4", source="local_scan", file_size=100,
                    status="failed", error_message="error")
        db_session.add(vid)
        db_session.commit()

        task = TaskQueue(id=uuid.uuid4().hex, video_id=vid.id, status="failed",
                         retry_count=3, error_message="error")
        db_session.add(task)
        db_session.commit()

        import cli
        args = MagicMock()
        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_retry(args)

        db_session.refresh(task)
        db_session.refresh(vid)
        assert task.status == "pending"
        assert task.retry_count == 0
        assert vid.status == "queued"

    def test_retry_no_failed_tasks(self, db_session, db_session_nc, capsys):
        """無失敗任務時顯示提示訊息"""
        import cli
        args = MagicMock()
        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_retry(args)

        captured = capsys.readouterr()
        assert "沒有失敗" in captured.out


class TestCLIList:
    def test_list_all(self, db_session, db_session_nc, sample_video, capsys):
        # Pre-read the name before session might close
        name = sample_video.original_filename
        import cli
        args = MagicMock()
        args.status = None
        args.limit = 50

        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_list(args)

        captured = capsys.readouterr()
        assert name in captured.out

    def test_list_filter_status(self, db_session, db_session_nc, sample_video, completed_video, capsys):
        completed_name = completed_video.original_filename
        pending_name = sample_video.original_filename
        import cli
        args = MagicMock()
        args.status = "completed"
        args.limit = 50

        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_list(args)

        captured = capsys.readouterr()
        assert completed_name in captured.out
        assert pending_name not in captured.out

    def test_list_empty(self, db_session, db_session_nc, capsys):
        import cli
        args = MagicMock()
        args.status = "completed"
        args.limit = 50

        with patch("cli._get_db", return_value=db_session_nc):
            cli.cmd_list(args)

        captured = capsys.readouterr()
        assert "無符合" in captured.out
