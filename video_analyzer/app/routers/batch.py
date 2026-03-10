"""批量操作 API：目錄掃描、全部加入佇列、佇列統計"""
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db, Video, TaskQueue
from app.config import settings
from app.services.audio_extractor import get_video_duration

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/batch", tags=["batch"])


def _scan_directory(scan_path: str, db: Session) -> dict:
    """掃描目錄，將新影片登錄到資料庫（不複製檔案）"""
    base = Path(scan_path)
    if not base.exists():
        raise ValueError(f"目錄不存在: {scan_path}")
    if not base.is_dir():
        raise ValueError(f"路徑不是目錄: {scan_path}")

    found = skipped = registered = 0

    for ext in settings.SUPPORTED_VIDEO_EXTENSIONS:
        for video_file in base.rglob(f"*{ext}"):
            found += 1
            abs_path = str(video_file.resolve())

            # 以絕對路徑檢查是否已登錄
            existing = db.query(Video).filter(Video.file_path == abs_path).first()
            if existing:
                skipped += 1
                continue

            file_size = video_file.stat().st_size
            duration = get_video_duration(video_file)
            video_id = uuid.uuid4().hex

            video = Video(
                id=video_id,
                filename=video_file.name,
                original_filename=video_file.name,
                file_path=abs_path,
                source="local_scan",
                file_size=file_size,
                duration=duration,
                status="pending",
            )
            db.add(video)
            registered += 1

    db.commit()
    logger.info(f"掃描完成: 發現 {found}，新登錄 {registered}，跳過 {skipped}")
    return {"found": found, "registered": registered, "skipped": skipped}


@router.post("/scan")
def scan_directory(
    path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    掃描本地目錄，將影片路徑登錄至資料庫（不複製檔案）。
    對於大型目錄會在背景執行。
    """
    scan_path = Path(path)
    if not scan_path.exists():
        raise HTTPException(400, f"目錄不存在: {path}")
    if not scan_path.is_dir():
        raise HTTPException(400, f"路徑不是目錄: {path}")

    # 先做一個快速計數
    result = _scan_directory(path, db)
    return {
        "message": "掃描完成",
        "path": path,
        **result,
    }


@router.post("/queue-all")
def queue_all_pending(
    priority: int = 5,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """將所有 pending 狀態的影片加入分析佇列"""
    query = db.query(Video).filter(Video.status == "pending")
    if source:
        query = query.filter(Video.source == source)

    videos = query.all()
    queued_count = 0

    for video in videos:
        # 避免重複加入
        existing = db.query(TaskQueue).filter(
            TaskQueue.video_id == video.id,
            TaskQueue.status.in_(["pending", "processing"]),
        ).first()
        if existing:
            continue

        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=video.id,
            priority=max(1, min(10, priority)),
            status="pending",
        )
        db.add(task)
        video.status = "queued"
        queued_count += 1

    db.commit()
    return {
        "message": f"已將 {queued_count} 支影片加入佇列",
        "queued": queued_count,
        "total_pending_found": len(videos),
    }


@router.post("/cancel-all")
def cancel_all_pending(db: Session = Depends(get_db)):
    """取消所有等待中的任務"""
    tasks = db.query(TaskQueue).filter(TaskQueue.status == "pending").all()
    cancelled = 0
    for task in tasks:
        task.status = "cancelled"
        video = db.query(Video).filter(Video.id == task.video_id).first()
        if video and video.status == "queued":
            video.status = "pending"
        cancelled += 1
    db.commit()
    return {"message": f"已取消 {cancelled} 個任務", "cancelled": cancelled}


@router.get("/status")
def get_queue_status(db: Session = Depends(get_db)):
    """取得整體佇列與影片狀態統計"""
    video_stats = {}
    for status in ["pending", "queued", "processing", "completed", "failed"]:
        video_stats[status] = db.query(Video).filter(Video.status == status).count()

    task_stats = {}
    for status in ["pending", "processing", "done", "failed", "cancelled"]:
        task_stats[status] = db.query(TaskQueue).filter(TaskQueue.status == status).count()

    # 目前正在處理的任務
    processing_tasks = db.query(TaskQueue).filter(
        TaskQueue.status == "processing"
    ).all()
    processing_info = []
    for t in processing_tasks:
        video = db.query(Video).filter(Video.id == t.video_id).first()
        processing_info.append({
            "task_id": t.id,
            "video_id": t.video_id,
            "video_name": video.original_filename if video else "unknown",
            "started_at": t.started_at.isoformat() if t.started_at else None,
        })

    return {
        "videos": video_stats,
        "tasks": task_stats,
        "currently_processing": processing_info,
    }


@router.post("/retry-failed")
def retry_failed(db: Session = Depends(get_db)):
    """將所有失敗的任務重設為 pending 以重新執行"""
    tasks = db.query(TaskQueue).filter(TaskQueue.status == "failed").all()
    retried = 0
    for task in tasks:
        task.status = "pending"
        task.retry_count = 0
        task.error_message = None
        video = db.query(Video).filter(Video.id == task.video_id).first()
        if video:
            video.status = "queued"
            video.error_message = None
        retried += 1
    db.commit()
    return {"message": f"已重設 {retried} 個失敗任務", "retried": retried}


@router.get("/pick-directory")
def pick_directory():
    """打開原生 macOS 資料夾選擇器，回傳選擇的路徑"""
    import subprocess
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'POSIX path of (choose folder with prompt "選擇影片目錄")'],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            # 使用者按了取消
            return {"cancelled": True, "path": None}
        path = result.stdout.strip()
        return {"cancelled": False, "path": path}
    except subprocess.TimeoutExpired:
        return {"cancelled": True, "path": None}
    except Exception as e:
        raise HTTPException(500, f"無法開啟目錄選擇器: {e}")
