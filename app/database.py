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


# ── M2 知識圖譜 ────────────────────────────────────────────────────────────────


class Concept(Base):
    """知識點（概念節點）"""

    __tablename__ = "concepts"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, index=True)
    description = Column(Text, nullable=True)
    video_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    relations_from = relationship(  # type: ignore[misc]
        "ConceptRelation",
        foreign_keys="ConceptRelation.source_concept_id",
        cascade="all, delete-orphan",
    )
    relations_to = relationship(  # type: ignore[misc]
        "ConceptRelation",
        foreign_keys="ConceptRelation.target_concept_id",
        cascade="all, delete-orphan",
    )
    segment_links = relationship("SegmentConcept", cascade="all, delete-orphan")  # type: ignore[misc]


class ConceptRelation(Base):
    """知識點之間的關係邊"""

    __tablename__ = "concept_relations"

    id = Column(String, primary_key=True)
    source_concept_id = Column(
        String, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    target_concept_id = Column(
        String, ForeignKey("concepts.id", ondelete="CASCADE"), index=True
    )
    relation_type = Column(String, default="related")  # related / prerequisite / part_of
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "source_concept_id", "target_concept_id", "relation_type",
            name="uq_concept_relation",
        ),
    )


class SegmentConcept(Base):
    """片段與知識點的關聯（可追溯回原始時間點）"""

    __tablename__ = "segment_concepts"

    id = Column(String, primary_key=True)
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    concept_id = Column(String, ForeignKey("concepts.id", ondelete="CASCADE"), index=True)
    seg_idx = Column(Integer)       # segment index in transcript.segments JSON
    start_sec = Column(Float)       # segment start time (seconds)
    end_sec = Column(Float)         # segment end time (seconds)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("video_id", "concept_id", "seg_idx", name="uq_seg_concept"),
    )


class Topic(Base):
    """知識庫主題節點（支援無限層級）"""

    __tablename__ = "topics"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, index=True)
    slug = Column(String, unique=True, index=True)  # URL-friendly identifier
    parent_id = Column(String, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True)
    domain = Column(String, nullable=True, index=True)  # top-level domain label
    description = Column(Text, nullable=True)
    learning_order = Column(Integer, default=0)  # ordering weight within parent
    prerequisites = Column(Text, nullable=True)  # JSON: [topic_id, ...]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    children = relationship(  # type: ignore[misc]
        "Topic",
        foreign_keys="Topic.parent_id",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    parent = relationship(  # type: ignore[misc]
        "Topic",
        foreign_keys="Topic.parent_id",
        back_populates="children",
        remote_side="Topic.id",
    )
    concept_links = relationship("ConceptTopic", cascade="all, delete-orphan")  # type: ignore[misc]


class ConceptTopic(Base):
    """概念 ↔ 主題 多對多關聯"""

    __tablename__ = "concept_topics"

    id = Column(String, primary_key=True)
    concept_id = Column(String, ForeignKey("concepts.id", ondelete="CASCADE"), index=True)
    topic_id = Column(String, ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("concept_id", "topic_id", name="uq_concept_topic"),)


class WikiPage(Base):
    """跨影片合成的知識頁面"""

    __tablename__ = "wiki_pages"

    id = Column(String, primary_key=True)
    concept_id = Column(
        String, ForeignKey("concepts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    topic_id = Column(
        String, ForeignKey("topics.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title = Column(String, index=True)
    slug = Column(String, unique=True, index=True)
    synthesized_content = Column(Text, nullable=True)  # GPT-generated Markdown
    source_video_count = Column(Integer, default=0)
    last_synthesized_at = Column(DateTime, nullable=True)
    status = Column(String, default="draft")  # draft / published / stale
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    sources = relationship("WikiPageSource", cascade="all, delete-orphan")  # type: ignore[misc]


class WikiPageSource(Base):
    """知識頁 ↔ 影片片段 溯源記錄"""

    __tablename__ = "wiki_page_sources"

    id = Column(String, primary_key=True)
    wiki_page_id = Column(
        String, ForeignKey("wiki_pages.id", ondelete="CASCADE"), index=True
    )
    video_id = Column(String, ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    start_time = Column(Float, nullable=True)
    end_time = Column(Float, nullable=True)
    excerpt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def _migrate_db():
    """補齊新欄位與新資料表（不破壞已有資料）"""
    import re
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
    # NOTE: 不要使用 content=''（contentless FTS）。
    # 我們需要保留 UNINDEXED 欄位（video_id/start_sec 等）供搜尋結果回傳。
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS video_fts USING fts5(
            video_id UNINDEXED,
            title,
            summary,
            transcript,
            key_points,
            tokenize='unicode61'
        )
    """)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS segment_fts USING fts5(
            video_id UNINDEXED,
            seg_idx UNINDEXED,
            start_sec UNINDEXED,
            end_sec UNINDEXED,
            text,
            tokenize='unicode61'
        )
    """)
    # 舊版使用 content=''（contentless FTS）時，UNINDEXED 欄位讀回會是 NULL；
    # 需重建表以保留 video_id/start_sec 等欄位值。
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='video_fts'")
    video_fts_sql = (cursor.fetchone() or [""])[0] or ""
    if re.search(r"\bcontent\s*=\s*''", video_fts_sql, re.IGNORECASE):
        cursor.execute("DROP TABLE IF EXISTS video_fts")
        cursor.execute("""
            CREATE VIRTUAL TABLE video_fts USING fts5(
                video_id UNINDEXED,
                title,
                summary,
                transcript,
                key_points,
                tokenize='unicode61'
            )
        """)
        logger.info("[migration] rebuilt video_fts without content=''")

    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='segment_fts'")
    segment_fts_sql = (cursor.fetchone() or [""])[0] or ""
    if re.search(r"\bcontent\s*=\s*''", segment_fts_sql, re.IGNORECASE):
        cursor.execute("DROP TABLE IF EXISTS segment_fts")
        cursor.execute("""
            CREATE VIRTUAL TABLE segment_fts USING fts5(
                video_id UNINDEXED,
                seg_idx UNINDEXED,
                start_sec UNINDEXED,
                end_sec UNINDEXED,
                text,
                tokenize='unicode61'
            )
        """)
        logger.info("[migration] rebuilt segment_fts without content=''")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_taskqueue_status ON task_queue(status)")

    # M2 知識圖譜表（idempotent）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concepts (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            video_count INTEGER DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_relations (
            id TEXT PRIMARY KEY,
            source_concept_id TEXT REFERENCES concepts(id) ON DELETE CASCADE,
            target_concept_id TEXT REFERENCES concepts(id) ON DELETE CASCADE,
            relation_type TEXT DEFAULT 'related',
            created_at DATETIME,
            UNIQUE(source_concept_id, target_concept_id, relation_type)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_concept_rel_src ON concept_relations(source_concept_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_concept_rel_tgt ON concept_relations(target_concept_id)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS segment_concepts (
            id TEXT PRIMARY KEY,
            video_id TEXT REFERENCES videos(id) ON DELETE CASCADE,
            concept_id TEXT REFERENCES concepts(id) ON DELETE CASCADE,
            seg_idx INTEGER,
            start_sec REAL,
            end_sec REAL,
            created_at DATETIME,
            UNIQUE(video_id, concept_id, seg_idx)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_seg_concept_video ON segment_concepts(video_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_seg_concept_concept ON segment_concepts(concept_id)"
    )

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

    # Wiki 知識庫表（idempotent）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            parent_id TEXT REFERENCES topics(id) ON DELETE SET NULL,
            domain TEXT,
            description TEXT,
            learning_order INTEGER DEFAULT 0,
            prerequisites TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topics_domain ON topics(domain)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_topics_parent ON topics(parent_id)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS concept_topics (
            id TEXT PRIMARY KEY,
            concept_id TEXT REFERENCES concepts(id) ON DELETE CASCADE,
            topic_id TEXT REFERENCES topics(id) ON DELETE CASCADE,
            created_at DATETIME,
            UNIQUE(concept_id, topic_id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_concept_topics_concept ON concept_topics(concept_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_concept_topics_topic ON concept_topics(topic_id)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wiki_pages (
            id TEXT PRIMARY KEY,
            concept_id TEXT REFERENCES concepts(id) ON DELETE CASCADE,
            topic_id TEXT REFERENCES topics(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            synthesized_content TEXT,
            source_video_count INTEGER DEFAULT 0,
            last_synthesized_at DATETIME,
            status TEXT DEFAULT 'draft',
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_pages_concept ON wiki_pages(concept_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_pages_topic ON wiki_pages(topic_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_wiki_pages_status ON wiki_pages(status)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wiki_page_sources (
            id TEXT PRIMARY KEY,
            wiki_page_id TEXT REFERENCES wiki_pages(id) ON DELETE CASCADE,
            video_id TEXT REFERENCES videos(id) ON DELETE CASCADE,
            start_time REAL,
            end_time REAL,
            excerpt TEXT,
            created_at DATETIME
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_wiki_sources_page ON wiki_page_sources(wiki_page_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_wiki_sources_video ON wiki_page_sources(video_id)"
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
