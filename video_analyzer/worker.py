"""
持久化背景 Worker
==============
獨立進程，與 Web Server 解耦，網頁關閉後繼續執行。

使用方式：
    python worker.py              # 前景執行
    nohup python worker.py &      # 背景執行（關閉終端機後仍繼續）

停止方式：
    kill <PID>                    # Graceful shutdown（完成當前任務再結束）
    kill -9 <PID>                 # 強制停止
"""
import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# 確保從 video_analyzer 目錄執行
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, Video, TaskQueue, Transcript, Summary, Classification
from app.services.audio_extractor import extract_audio, cleanup_audio
from app.services.transcriber import transcribe
from app.services.analyzer import analyze, generate_mindmap, generate_faq, generate_study_notes

# ──────────────────────────── Logging ────────────────────────────

log_file = settings.DATA_DIR / "worker.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(str(log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("worker")

# ──────────────────────────── State ────────────────────────────

_running = True  # 設為 False 時，完成當前任務後退出


def _handle_shutdown(signum, frame):
    global _running
    logger.info(f"收到信號 {signum}，完成當前任務後退出...")
    _running = False


signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)

# ──────────────────────────── Core Logic ────────────────────────────

def _set_progress(video: Video, db: Session, step: int, message: str, sub: int = 0) -> None:
    """更新影片分析進度並立即寫入 DB，供前端輪詢顯示"""
    video.progress_step = step
    video.progress_message = message
    video.progress_sub = sub
    db.commit()
    logger.info(f"  [{step}/4] {message}")


def _process_task(task: TaskQueue, db: Session) -> None:
    """執行單一分析任務：音頻提取 → 轉錄 → 分析 → NotebookLM 功能"""
    video = db.query(Video).filter(Video.id == task.video_id).first()
    if not video:
        raise ValueError(f"找不到影片 video_id={task.video_id}")

    video_path = video.file_path
    if not video_path or not Path(video_path).exists():
        raise FileNotFoundError(f"影片檔案不存在: {video_path}")

    logger.info(f"▶ 開始處理: {video.original_filename}")

    # Step 1: 提取音頻
    def ffmpeg_cb(pct: int) -> None:
        _set_progress(video, db, 1, f"提取音頻中... ({pct}%)", sub=pct)

    _set_progress(video, db, 1, "提取音頻中...", sub=0)
    audio_path = extract_audio(video_path, progress_callback=ffmpeg_cb)
    _set_progress(video, db, 1, "音頻提取完成", sub=100)

    try:
        # Step 2: 語音轉文字
        def whisper_cb(pct: int, chunk_idx: int, total_chunks: int) -> None:
            if total_chunks > 1:
                msg = f"語音轉文字中... (片段 {chunk_idx}/{total_chunks})"
            else:
                msg = "語音轉文字中..."
            _set_progress(video, db, 2, msg, sub=pct)

        file_size_mb = Path(audio_path).stat().st_size / 1024 / 1024
        _set_progress(video, db, 2, f"語音轉文字中... ({file_size_mb:.1f} MB)", sub=0)
        transcript_text = transcribe(audio_path, progress_callback=whisper_cb)

        # 儲存逐字稿
        existing_transcript = db.query(Transcript).filter(Transcript.video_id == task.video_id).first()
        if existing_transcript:
            existing_transcript.content = transcript_text
        else:
            db.add(Transcript(
                id=uuid.uuid4().hex,
                video_id=task.video_id,
                content=transcript_text,
            ))

        # Step 3: GPT 分析
        _set_progress(video, db, 3, f"GPT 分析中... ({len(transcript_text)} 字)", sub=0)
        summary_text, key_points, category, confidence = analyze(transcript_text)
        _set_progress(video, db, 3, f"GPT 分析完成 → {category}", sub=100)

        # 儲存摘要
        existing_summary = db.query(Summary).filter(Summary.video_id == task.video_id).first()
        if existing_summary:
            existing_summary.summary = summary_text
            existing_summary.key_points = json.dumps(key_points, ensure_ascii=False)
        else:
            db.add(Summary(
                id=uuid.uuid4().hex,
                video_id=task.video_id,
                summary=summary_text,
                key_points=json.dumps(key_points, ensure_ascii=False),
            ))

        # 儲存分類
        existing_cls = db.query(Classification).filter(Classification.video_id == task.video_id).first()
        if existing_cls:
            existing_cls.category = category
            existing_cls.confidence = confidence
        else:
            db.add(Classification(
                id=uuid.uuid4().hex,
                video_id=task.video_id,
                category=category,
                confidence=confidence,
            ))

        # Step 4: 生成 NotebookLM 功能
        _set_progress(video, db, 4, "生成心智圖...", sub=0)
        mindmap = generate_mindmap(transcript_text)
        _set_progress(video, db, 4, "生成 FAQ...", sub=33)
        faq_list = generate_faq(transcript_text)
        _set_progress(video, db, 4, "生成學習筆記...", sub=66)
        study_notes = generate_study_notes(transcript_text)

        existing_summary = db.query(Summary).filter(Summary.video_id == task.video_id).first()
        if existing_summary:
            existing_summary.mindmap = mindmap
            existing_summary.faq = json.dumps(faq_list, ensure_ascii=False)
            existing_summary.study_notes = study_notes

        # 更新影片狀態
        video.status = "completed"
        video.progress_step = 4
        video.progress_message = "分析完成"
        video.error_message = None
        task.status = "done"
        task.completed_at = datetime.utcnow()

        db.commit()
        logger.info(f"✅ 完成: {video.original_filename} → {category}")

    finally:
        cleanup_audio(audio_path)


def _pick_next_task(db: Session) -> TaskQueue | None:
    """取出優先級最高的 pending 任務（priority 值越小越優先）"""
    return (
        db.query(TaskQueue)
        .filter(TaskQueue.status == "pending")
        .order_by(TaskQueue.priority.asc(), TaskQueue.created_at.asc())
        .first()
    )


def _handle_failure(task: TaskQueue, video: Video | None, error: Exception, db: Session) -> None:
    """處理任務失敗：記錄錯誤、決定是否重試"""
    task.retry_count += 1
    task.error_message = str(error)[:500]

    if task.retry_count >= task.max_retries:
        task.status = "failed"
        if video:
            video.status = "failed"
            video.error_message = task.error_message
        logger.error(f"❌ 任務失敗（已重試 {task.retry_count} 次）: {error}")
    else:
        task.status = "pending"  # 重新加回佇列
        logger.warning(f"⚠ 任務失敗，將重試（{task.retry_count}/{task.max_retries}）: {error}")

    db.commit()


def _recover_interrupted_tasks(db: Session) -> None:
    """Worker 啟動時，將上次中斷的 processing 任務重設為 pending"""
    stale = db.query(TaskQueue).filter(TaskQueue.status == "processing").all()
    if stale:
        logger.info(f"恢復 {len(stale)} 個中斷的任務...")
        for task in stale:
            task.status = "pending"
            task.started_at = None
            video = db.query(Video).filter(Video.id == task.video_id).first()
            if video and video.status == "processing":
                video.status = "queued"
        db.commit()


# ──────────────────────────── Main Loop ────────────────────────────

def run_worker():
    logger.info("=" * 50)
    logger.info(f"Worker 啟動 (PID: {os.getpid()})")
    logger.info(f"輪詢間隔: {settings.WORKER_POLL_INTERVAL}s")
    logger.info(f"最大重試: {settings.WORKER_MAX_RETRIES}")
    logger.info(f"日誌檔案: {log_file}")
    logger.info("=" * 50)

    db = SessionLocal()
    try:
        _recover_interrupted_tasks(db)

        while _running:
            task = _pick_next_task(db)

            if not task:
                # 佇列空，等待
                time.sleep(settings.WORKER_POLL_INTERVAL)
                continue

            # 標記為處理中
            task.status = "processing"
            task.started_at = datetime.utcnow()
            db.commit()

            video = db.query(Video).filter(Video.id == task.video_id).first()
            if video:
                video.status = "processing"
                db.commit()

            try:
                _process_task(task, db)
            except Exception as e:
                logger.exception(f"處理任務時發生錯誤: {e}")
                video = db.query(Video).filter(Video.id == task.video_id).first()
                _handle_failure(task, video, e, db)

                if task.status == "pending":
                    logger.info(f"等待 {settings.WORKER_RETRY_DELAY}s 後重試...")
                    time.sleep(settings.WORKER_RETRY_DELAY)

            # 任務間延遲，避免 API rate limit
            if _running:
                time.sleep(settings.WORKER_TASK_DELAY)

    except Exception as e:
        logger.critical(f"Worker 發生致命錯誤: {e}", exc_info=True)
    finally:
        db.close()
        logger.info("Worker 已停止")


if __name__ == "__main__":
    run_worker()
