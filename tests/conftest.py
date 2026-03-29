"""
共用測試夾具（fixtures）
- 使用獨立的 in-memory SQLite，避免污染開發資料庫
- 每個測試函數都獲得乾淨的資料庫狀態
"""

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import (
    Base,
    ChatMessage,
    Classification,
    Label,
    Summary,
    Transcript,
    Video,
    VideoNote,
    get_db,
)

# ─── 測試用 In-memory DB ───────────────────────────────────────
# StaticPool：所有連線共用同一個 SQLite in-memory 連線，避免每次連線都是空的 DB


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


class _NonClosingSession:
    """包裝 Session，避免 CLI finally 塊呼叫 close() 導致測試中物件失效"""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass  # no-op：讓測試繼續持有 session


@pytest.fixture(scope="function")
def db_session_nc(db_session):
    """Non-Closing 版本的 db_session，供 CLI 測試使用"""
    return _NonClosingSession(db_session)


# ─── FastAPI TestClient（注入測試 DB）────────────────────────


@pytest.fixture(scope="function")
def client(db_engine):
    from app import app
    import app.routers.batch as batch_module

    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    # Patch background-task session factory to use the same test DB
    original_factory = batch_module._scan_session_factory
    batch_module._scan_session_factory = Session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
    batch_module._scan_session_factory = original_factory


# ─── 輔助 Fixtures ────────────────────────────────────────────


@pytest.fixture
def sample_video(db_session) -> Video:
    """建立一個 pending 狀態的測試影片"""
    v = Video(
        id=uuid.uuid4().hex,
        filename="test_video.mp4",
        original_filename="test_video.mp4",
        file_path="/fake/path/test_video.mp4",
        source="local_scan",
        file_size=10 * 1024 * 1024,  # 10 MB
        duration=300.0,
        status="pending",
    )
    db_session.add(v)
    db_session.commit()
    db_session.refresh(v)
    return v


@pytest.fixture
def completed_video(db_session) -> Video:
    """建立一個已完成分析的測試影片（含逐字稿、摘要、分類）"""
    import json

    vid_id = uuid.uuid4().hex

    video = Video(
        id=vid_id,
        filename="completed.mp4",
        original_filename="completed.mp4",
        file_path="/fake/path/completed.mp4",
        source="local_scan",
        file_size=5 * 1024 * 1024,
        duration=120.0,
        status="completed",
    )
    transcript = Transcript(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        content="這是測試逐字稿內容，主要討論占星學的基礎知識。",
    )
    summary = Summary(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        summary="本影片介紹占星學基礎，包含星座與行星的關係。",
        key_points=json.dumps(["星座介紹", "行星影響", "實用技巧"], ensure_ascii=False),
    )
    classification = Classification(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        category="占星學 (Astrology)",
        confidence=0.92,
    )
    for obj in [video, transcript, summary, classification]:
        db_session.add(obj)
    db_session.commit()
    db_session.refresh(video)
    return video


@pytest.fixture
def fake_video_file(tmp_path) -> Path:
    """建立一個假的影片檔案（實際上是空檔案）"""
    f = tmp_path / "fake_video.mp4"
    f.write_bytes(b"\x00" * 1024)
    return f


@pytest.fixture
def fake_audio_file(tmp_path) -> Path:
    """建立一個假的 MP3 音頻檔案"""
    f = tmp_path / "fake_audio.mp3"
    f.write_bytes(b"\x00" * 512)
    return f


@pytest.fixture
def completed_video_full(db_session) -> Video:
    """建立含有所有 NotebookLM 欄位的完整測試影片"""
    import json

    vid_id = uuid.uuid4().hex
    faq_data = json.dumps(
        [
            {"question": "什麼是占星學？", "answer": "研究天體對人的影響。"},
            {"question": "有幾個星座？", "answer": "十二個。"},
        ],
        ensure_ascii=False,
    )

    video = Video(
        id=vid_id,
        filename="full_test.mp4",
        original_filename="full_test.mp4",
        file_path="/fake/path/full_test.mp4",
        source="local_scan",
        file_size=5 * 1024 * 1024,
        duration=120.0,
        status="completed",
    )
    transcript = Transcript(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        content="這是完整的測試逐字稿，主要討論占星學知識。",
    )
    summary = Summary(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        summary="占星學基礎介紹",
        key_points=json.dumps(["星座", "行星"], ensure_ascii=False),
        mindmap="# 占星學\n## 星座\n### 火象\n## 行星\n### 太陽",
        faq=faq_data,
        study_notes="## 核心概念\n占星學是古老的學問。\n## 重要術語\n星座、行星",
    )
    classification = Classification(
        id=uuid.uuid4().hex,
        video_id=vid_id,
        category="占星學 (Astrology)",
        confidence=0.92,
    )
    for obj in [video, transcript, summary, classification]:
        db_session.add(obj)
    db_session.commit()
    db_session.refresh(video)
    return video


@pytest.fixture
def chat_with_history(db_session, completed_video) -> list:
    """建立有對話記錄的測試環境"""
    vid_id = completed_video.id
    messages = [
        ChatMessage(
            id=uuid.uuid4().hex,
            video_id=vid_id,
            role="user",
            content="什麼是占星學？",
            created_at=datetime(2024, 1, 1, 10, 0, 0),
        ),
        ChatMessage(
            id=uuid.uuid4().hex,
            video_id=vid_id,
            role="assistant",
            content="占星學是研究天體位置與人類事務關係的古老學問。",
            created_at=datetime(2024, 1, 1, 10, 0, 1),
        ),
    ]
    for m in messages:
        db_session.add(m)
    db_session.commit()
    return messages


@pytest.fixture
def reviewed_video(db_session) -> Video:
    """已複習過一次的影片（含 SM-2 欄位）"""
    from datetime import timedelta

    vid_id = uuid.uuid4().hex
    video = Video(
        id=vid_id,
        filename="reviewed.mp4",
        original_filename="reviewed.mp4",
        file_path="/fake/path/reviewed.mp4",
        source="local_scan",
        file_size=5 * 1024 * 1024,
        duration=180.0,
        status="completed",
        review_count=3,
        last_reviewed_at=datetime.utcnow() - timedelta(days=2),
        sr_interval=6,
        sr_ease_factor=2.5,
        sr_repetitions=2,
        sr_next_review_at=datetime.utcnow() - timedelta(days=1),  # 已到期
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


@pytest.fixture
def sample_label(db_session) -> Label:
    """建立一個測試標籤"""
    lbl = Label(
        id=uuid.uuid4().hex,
        name="測試標籤",
        color="#3b82f6",
    )
    db_session.add(lbl)
    db_session.commit()
    db_session.refresh(lbl)
    return lbl


@pytest.fixture
def video_with_note(db_session, completed_video) -> tuple:
    """建立有個人筆記的影片"""
    note = VideoNote(
        id=uuid.uuid4().hex,
        video_id=completed_video.id,
        content="## 我的筆記\n\n- 重點一\n- 重點二\n\n> 這很重要！",
        updated_at=datetime.utcnow(),
    )
    db_session.add(note)
    db_session.commit()
    return completed_video, note
