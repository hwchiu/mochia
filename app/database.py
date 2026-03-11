from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

DATABASE_URL = f"sqlite:///{settings.DATA_DIR}/video_analyzer.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base: Any = declarative_base()


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    filename = Column(String, unique=True, index=True)
    original_filename = Column(String)
    file_path = Column(String, nullable=True)
    source = Column(String, default="uploaded")
    upload_date = Column(DateTime, default=datetime.utcnow)
    file_size = Column(Integer)
    duration = Column(Float, nullable=True)
    status = Column(String, default="pending")
    progress_step = Column(Integer, default=0)
    progress_message = Column(String, nullable=True)
    progress_sub = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
    # 複習追蹤
    last_reviewed_at = Column(DateTime, nullable=True)
    review_count = Column(Integer, default=0)
    # 間隔重複 SM-2
    sr_interval = Column(Integer, default=1)
    sr_ease_factor = Column(Float, default=2.5)
    sr_repetitions = Column(Integer, default=0)
    sr_next_review_at = Column(DateTime, nullable=True)


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    content = Column(Text)
    language = Column(String, default="zh")
    created_at = Column(DateTime, default=datetime.utcnow)


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    summary = Column(Text)
    key_points = Column(Text)
    mindmap = Column(Text, nullable=True)
    faq = Column(Text, nullable=True)
    study_notes = Column(Text, nullable=True)
    case_analysis = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Classification(Base):
    __tablename__ = "classifications"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    category = Column(String)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskQueue(Base):
    __tablename__ = "task_queue"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    priority = Column(Integer, default=5)
    status = Column(String, default="pending", index=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    role = Column(String)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class Label(Base):
    __tablename__ = "labels"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, index=True)
    color = Column(String, default="#3b82f6")
    created_at = Column(DateTime, default=datetime.utcnow)


class VideoLabel(Base):
    __tablename__ = "video_labels"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    label_id = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewRecord(Base):
    """每次複習紀錄"""

    __tablename__ = "review_records"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    confidence = Column(Integer)  # 1-5
    reviewed_at = Column(DateTime, default=datetime.utcnow, index=True)


class VideoNote(Base):
    """個人筆記"""

    __tablename__ = "video_notes"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True, unique=True)
    content = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


def _migrate_db():
    """補齊新欄位與新資料表（不破壞已有資料）"""
    import sqlite3

    db_path = str(settings.DATA_DIR / "video_analyzer.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # summaries
    cursor.execute("PRAGMA table_info(summaries)")
    existing = {row[1] for row in cursor.fetchall()}
    for col, typ in [
        ("mindmap", "TEXT"),
        ("faq", "TEXT"),
        ("study_notes", "TEXT"),
        ("case_analysis", "TEXT"),
    ]:
        if col not in existing:
            cursor.execute(f"ALTER TABLE summaries ADD COLUMN {col} {typ}")
            print(f"[migration] summaries.{col}")

    # videos
    cursor.execute("PRAGMA table_info(videos)")
    vcols = {row[1] for row in cursor.fetchall()}
    for col, typ in [
        ("progress_step", "INTEGER DEFAULT 0"),
        ("progress_message", "TEXT"),
        ("progress_sub", "INTEGER DEFAULT 0"),
        ("last_reviewed_at", "DATETIME"),
        ("review_count", "INTEGER DEFAULT 0"),
        ("sr_interval", "INTEGER DEFAULT 1"),
        ("sr_ease_factor", "REAL DEFAULT 2.5"),
        ("sr_repetitions", "INTEGER DEFAULT 0"),
        ("sr_next_review_at", "DATETIME"),
    ]:
        if col not in vcols:
            cursor.execute(f"ALTER TABLE videos ADD COLUMN {col} {typ}")
            print(f"[migration] videos.{col}")

    # FTS5 全文搜尋虛擬表
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS video_fts USING fts5(
            video_id UNINDEXED,
            title,
            summary,
            transcript,
            key_points,
            content='',
            tokenize='unicode61'
        )
    """)

    conn.commit()
    conn.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
