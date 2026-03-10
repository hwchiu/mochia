from sqlalchemy import create_engine, Column, String, DateTime, Integer, Float, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from app.config import settings

DATABASE_URL = f"sqlite:///{settings.DATA_DIR}/video_analyzer.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    filename = Column(String, unique=True, index=True)
    original_filename = Column(String)
    file_path = Column(String, nullable=True)
    source = Column(String, default="uploaded")  # "uploaded" | "local_scan"
    upload_date = Column(DateTime, default=datetime.utcnow)
    file_size = Column(Integer)
    duration = Column(Float, nullable=True)
    status = Column(String, default="pending")  # pending | queued | processing | completed | failed
    progress_step = Column(Integer, default=0)   # 0=等待 1=音頻 2=轉錄 3=GPT 4=NotebookLM
    progress_message = Column(String, nullable=True)
    progress_sub = Column(Integer, default=0)    # 0-100, within-step progress
    error_message = Column(String, nullable=True)


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
    key_points = Column(Text)       # JSON 陣列
    mindmap = Column(Text, nullable=True)       # Markmap Markdown 格式
    faq = Column(Text, nullable=True)           # JSON 陣列 [{question, answer}]
    study_notes = Column(Text, nullable=True)   # Markdown 格式的學習筆記
    created_at = Column(DateTime, default=datetime.utcnow)


class Classification(Base):
    __tablename__ = "classifications"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    category = Column(String)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class TaskQueue(Base):
    """持久化任務佇列"""
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
    """影片 Q&A 對話記錄"""
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    video_id = Column(String, index=True)
    role = Column(String)           # "user" | "assistant"
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


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
        ("mindmap",          "TEXT"),
        ("faq",              "TEXT"),
        ("study_notes",      "TEXT"),
    ]
    for col_name, col_type in new_columns:
        if col_name not in existing:
            cursor.execute(f"ALTER TABLE summaries ADD COLUMN {col_name} {col_type}")
            print(f"[migration] summaries.{col_name} 欄位已新增")

    # videos 表新欄位
    cursor.execute("PRAGMA table_info(videos)")
    videos_cols = {row[1] for row in cursor.fetchall()}
    video_columns = [
        ("progress_step",    "INTEGER DEFAULT 0"),
        ("progress_message", "TEXT"),
        ("progress_sub",     "INTEGER DEFAULT 0"),
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
