"""資料庫模型測試"""

import json
import uuid
from datetime import datetime

import pytest

from app.database import Classification, Summary, TaskQueue, Transcript, Video


class TestVideoModel:
    def test_create_video_defaults(self, db_session):
        """新建 Video 時預設值正確"""
        v = Video(
            id=uuid.uuid4().hex,
            filename="test.mp4",
            original_filename="test.mp4",
            file_path="/path/test.mp4",
            source="local_scan",
            file_size=1024,
        )
        db_session.add(v)
        db_session.commit()

        fetched = db_session.query(Video).filter_by(filename="test.mp4").first()
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.source == "local_scan"
        assert fetched.duration is None
        assert fetched.error_message is None

    def test_create_uploaded_video(self, db_session):
        """上傳影片的 source 為 uploaded"""
        v = Video(
            id=uuid.uuid4().hex,
            filename="uploaded.mp4",
            original_filename="my_video.mp4",
            file_path="/uploads/uploaded.mp4",
            source="uploaded",
            file_size=2048,
        )
        db_session.add(v)
        db_session.commit()

        fetched = db_session.query(Video).filter_by(source="uploaded").first()
        assert fetched.source == "uploaded"
        assert fetched.original_filename == "my_video.mp4"

    def test_update_video_status(self, db_session, sample_video):
        """更新影片狀態"""
        sample_video.status = "completed"
        db_session.commit()

        fetched = db_session.query(Video).filter_by(id=sample_video.id).first()
        assert fetched.status == "completed"

    def test_video_status_transitions(self, db_session, sample_video):
        """影片狀態流程：pending → queued → processing → completed"""
        for status in ["queued", "processing", "completed"]:
            sample_video.status = status
            db_session.commit()
            assert db_session.query(Video).filter_by(id=sample_video.id).first().status == status

    def test_same_filename_allowed_different_paths(self, db_session):
        """同名檔案在不同路徑下可以共存（local scan 多目錄場景）"""
        v1 = Video(
            id=uuid.uuid4().hex,
            filename="meeting_01.mp4",
            original_filename="meeting_01.mp4",
            file_path="/videos/source1/course_a/meeting_01.mp4",
            source="local_scan",
            file_size=1,
        )
        v2 = Video(
            id=uuid.uuid4().hex,
            filename="meeting_01.mp4",
            original_filename="meeting_01.mp4",
            file_path="/videos/source1/course_b/meeting_01.mp4",
            source="local_scan",
            file_size=1,
        )
        db_session.add_all([v1, v2])
        db_session.commit()
        count = db_session.query(Video).filter(Video.filename == "meeting_01.mp4").count()
        assert count == 2

    def test_unique_file_path_constraint(self, db_session):
        """相同 file_path 不能重複（去重依據）"""
        from sqlalchemy.exc import IntegrityError

        v1 = Video(
            id=uuid.uuid4().hex,
            filename="dup.mp4",
            original_filename="dup.mp4",
            file_path="/videos/source1/dup.mp4",
            source="local_scan",
            file_size=1,
        )
        v2 = Video(
            id=uuid.uuid4().hex,
            filename="dup.mp4",
            original_filename="dup.mp4",
            file_path="/videos/source1/dup.mp4",  # 同一路徑
            source="local_scan",
            file_size=1,
        )
        db_session.add(v1)
        db_session.commit()
        db_session.add(v2)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestTaskQueueModel:
    def test_create_task_defaults(self, db_session, sample_video):
        """新建 TaskQueue 時預設值正確"""
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
        )
        db_session.add(task)
        db_session.commit()

        fetched = db_session.query(TaskQueue).filter_by(video_id=sample_video.id).first()
        assert fetched.status == "pending"
        assert fetched.priority == 5
        assert fetched.retry_count == 0
        assert fetched.max_retries == 3
        assert fetched.started_at is None
        assert fetched.completed_at is None

    def test_task_priority_ordering(self, db_session, sample_video):
        """高優先級任務排在前面（priority 值小）"""
        vid2 = Video(
            id=uuid.uuid4().hex,
            filename="vid2.mp4",
            original_filename="vid2.mp4",
            file_path="/p/vid2.mp4",
            source="local_scan",
            file_size=1,
        )
        vid3 = Video(
            id=uuid.uuid4().hex,
            filename="vid3.mp4",
            original_filename="vid3.mp4",
            file_path="/p/vid3.mp4",
            source="local_scan",
            file_size=1,
        )
        db_session.add_all([vid2, vid3])
        db_session.commit()

        task_low = TaskQueue(id=uuid.uuid4().hex, video_id=vid2.id, priority=8)
        task_high = TaskQueue(id=uuid.uuid4().hex, video_id=vid3.id, priority=1)
        db_session.add_all([task_low, task_high])
        db_session.commit()

        ordered = db_session.query(TaskQueue).order_by(TaskQueue.priority.asc()).all()
        assert ordered[0].priority == 1

    def test_task_status_update(self, db_session, sample_video):
        """更新任務狀態和時間戳"""
        task = TaskQueue(id=uuid.uuid4().hex, video_id=sample_video.id)
        db_session.add(task)
        db_session.commit()

        task.status = "processing"
        task.started_at = datetime.utcnow()
        db_session.commit()

        fetched = db_session.query(TaskQueue).filter_by(id=task.id).first()
        assert fetched.status == "processing"
        assert fetched.started_at is not None


class TestTranscriptModel:
    def test_create_transcript(self, db_session, sample_video):
        t = Transcript(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
            content="測試逐字稿",
            language="zh",
        )
        db_session.add(t)
        db_session.commit()

        fetched = db_session.query(Transcript).filter_by(video_id=sample_video.id).first()
        assert fetched.content == "測試逐字稿"
        assert fetched.language == "zh"


class TestSummaryModel:
    def test_create_summary_with_key_points(self, db_session, sample_video):
        key_points = ["重點一", "重點二", "重點三"]
        s = Summary(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
            summary="測試摘要",
            key_points=json.dumps(key_points, ensure_ascii=False),
        )
        db_session.add(s)
        db_session.commit()

        fetched = db_session.query(Summary).filter_by(video_id=sample_video.id).first()
        assert fetched.summary == "測試摘要"
        assert json.loads(fetched.key_points) == key_points


class TestClassificationModel:
    def test_create_classification(self, db_session, sample_video):
        c = Classification(
            id=uuid.uuid4().hex,
            video_id=sample_video.id,
            category="占星學 (Astrology)",
            confidence=0.85,
        )
        db_session.add(c)
        db_session.commit()

        fetched = db_session.query(Classification).filter_by(video_id=sample_video.id).first()
        assert fetched.category == "占星學 (Astrology)"
        assert abs(fetched.confidence - 0.85) < 0.001
