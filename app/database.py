from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings

DATABASE_URL = f"sqlite:///{settings.DATA_DIR}/video_analyzer.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    filename: Mapped[str] = mapped_column(String, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, default="uploaded")  # "uploaded" | "local_scan"
    upload_date: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    file_size: Mapped[int] = mapped_column(Integer)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String, default="pending"
    )  # pending | queued | processing | completed | failed
    progress_step: Mapped[int] = mapped_column(
        Integer, default=0
    )  # 0=等待 1=音頻 2=轉錄 3=GPT 4=NotebookLM
    progress_message: Mapped[str | None] = mapped_column(String, nullable=True)
    progress_sub: Mapped[int] = mapped_column(Integer, default=0)  # 0-100, within-step progress
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    video_id: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String, default="zh")
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    video_id: Mapped[str] = mapped_column(String, index=True)
    summary: Mapped[str] = mapped_column(Text)
    key_points: Mapped[str] = mapped_column(Text)  # JSON 陣列
    mindmap: Mapped[str | None] = mapped_column(Text, nullable=True)  # Markmap Markdown 格式
    faq: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON 陣列 [{question, answer}]
    study_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Markdown 格式的學習筆記
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    video_id: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class TaskQueue(Base):
    """持久化任務佇列"""

    __tablename__ = "task_queue"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    video_id: Mapped[str] = mapped_column(String, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatMessage(Base):
    """影片 Q&A 對話記錄"""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    video_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class Label(Base):
    """自定義標籤"""

    __tablename__ = "labels"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    color: Mapped[str] = mapped_column(String, default="#3b82f6")  # hex color
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


class VideoLabel(Base):
    """影片與標籤的多對多關聯"""

    __tablename__ = "video_labels"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    video_id: Mapped[str] = mapped_column(String, index=True)
    label_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)


def _migrate_db():
    """
    為現有資料庫補齊新增的欄位（ALTER TABLE）。
    SQLAlchemy create_all 只建新表，不會修改已存在的表結構。
    """
    import sqlite3

    db_path = str(settings.DATA_DIR / "video_analyzer.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 取得 summaries 現有欄位
    cursor.execute("PRAGMA table_info(summaries)")
    existing = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("mindmap", "TEXT"),
        ("faq", "TEXT"),
        ("study_notes", "TEXT"),
    ]
    for col_name, col_type in new_columns:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE summaries ADD COLUMN {col_name} {col_type}")
            print(f"[migration] summaries.{col_name} 欄位已新增")

    # videos 表新欄位
    cursor.execute("PRAGMA table_info(videos)")
    videos_cols = {row[1] for row in cursor.fetchall()}
    video_columns = [
        ("progress_step", "INTEGER DEFAULT 0"),
        ("progress_message", "TEXT"),
        ("progress_sub", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in video_columns:
        if col_name not in videos_cols:
            cursor.execute(f"ALTER TABLE videos ADD COLUMN {col_name} {col_type}")
            print(f"[migration] videos.{col_name} 欄位已新增")

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
