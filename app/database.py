import logging
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import settings

DATABASE_URL = f"sqlite:///{settings.DATA_DIR}/video_analyzer.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base: Any = declarative_base()
logger = logging.getLogger(__name__)


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    filename = Column(String, index=True)  # 不唯一：本地掃描多目錄可有同名檔案
    original_filename = Column(String)
    file_path = Column(String, nullable=True, unique=True)  # 本地掃描去重依據
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

    # ORM-level cascade: deleting a Video automatically removes all child records
    transcripts = relationship("Transcript", cascade="all, delete-orphan")  # type: ignore[misc]
    summaries = relationship("Summary", cascade="all, delete-orphan")  # type: ignore[misc]
    classifications = relationship("Classification", cascade="all, delete-orphan")  # type: ignore[misc]
    task_queue_entries = relationship("TaskQueue", cascade="all, delete-orphan")  # type: ignore[misc]
    video_labels = relationship("VideoLabel", cascade="all, delete-orphan")  # type: ignore[misc]
    review_records = relationship("ReviewRecord", cascade="all, delete-orphan")  # type: ignore[misc]
    notes = relationship("VideoNote", cascade="all, delete-orphan")  # type: ignore[misc]
    chat_messages = relationship("ChatMessage", cascade="all, delete-orphan")  # type: ignore[misc]


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(String, primary_key=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    content = Column(Text)
    segments = Column(Text, nullable=True)  # JSON: [{start, end, text}, ...]
    language = Column(String, default="zh")
    created_at = Column(DateTime, default=datetime.utcnow)


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(String, primary_key=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
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
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    category = Column(String)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskQueue(Base):
    __tablename__ = "task_queue"

    id = Column(String, primary_key=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
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
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
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
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    label_id = Column(String, ForeignKey("labels.id", ondelete="CASCADE"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("video_id", "label_id", name="uq_video_label"),)


class ReviewRecord(Base):
    """每次複習紀錄"""

    __tablename__ = "review_records"

    id = Column(String, primary_key=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    confidence = Column(Integer)  # 1-5
    reviewed_at = Column(DateTime, default=datetime.utcnow, index=True)


class VideoNote(Base):
    """個人筆記"""

    __tablename__ = "video_notes"

    id = Column(String, primary_key=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True, unique=True)
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
            logger.info("[migration] summaries.%s", col)

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
            logger.info("[migration] videos.%s", col)

    # transcripts
    try:
        cursor.execute("ALTER TABLE transcripts ADD COLUMN segments TEXT")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise

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

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_taskqueue_status ON task_queue(status)")

    # 重建 chat_messages 以加入 FK（SQLite 不支援 ALTER TABLE ADD CONSTRAINT）
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='chat_messages'")
    cm_row = cursor.fetchone()
    if cm_row and "FOREIGN KEY" not in (cm_row[0] or "").upper():
        logger.info("[migration] 重建 chat_messages 以加入 FK...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages_new (
                id TEXT PRIMARY KEY,
                video_id TEXT REFERENCES videos(id) ON DELETE CASCADE,
                role TEXT,
                content TEXT,
                created_at DATETIME
            )
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO chat_messages_new (id, video_id, role, content, created_at)
            SELECT id, video_id, role, content, created_at FROM chat_messages
        """)
        cursor.execute("DROP TABLE chat_messages")
        cursor.execute("ALTER TABLE chat_messages_new RENAME TO chat_messages")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_chat_messages_video_id ON chat_messages(video_id)"
        )

    conn.commit()
    conn.close()

    # 移除 videos.filename 的舊 UNIQUE index（local scan 多目錄可有同名檔案）
    # SQLite 不支援 DROP INDEX ON table，需直接 DROP INDEX by index name
    _drop_filename_unique_index()


def _drop_filename_unique_index():
    """移除 videos.filename 的 UNIQUE index（如果存在）。"""
    import sqlite3

    db_path = str(settings.DATA_DIR / "video_analyzer.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='videos'")
    for index_name, index_sql in cursor.fetchall():
        if index_sql and "filename" in index_sql and "UNIQUE" in (index_sql or "").upper():
            cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
            logger.info("[migration] dropped UNIQUE index on videos.filename: %s", index_name)
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
