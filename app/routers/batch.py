"""批量操作 API：目錄掃描、全部加入佇列、佇列統計"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import TaskQueue, Video, get_db

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
            video_id = uuid.uuid4().hex

            video = Video(
                id=video_id,
                filename=video_file.name,
                original_filename=video_file.name,
                file_path=abs_path,
                source="local_scan",
                file_size=file_size,
                duration=None,  # 分析時由 ffprobe 取得
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
    source: str | None = None,
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
        existing = (
            db.query(TaskQueue)
            .filter(
                TaskQueue.video_id == video.id,
                TaskQueue.status.in_(["pending", "processing"]),
            )
            .first()
        )
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
    processing_tasks = db.query(TaskQueue).filter(TaskQueue.status == "processing").all()
    processing_info = []
    for t in processing_tasks:
        video = db.query(Video).filter(Video.id == t.video_id).first()
        processing_info.append(
            {
                "task_id": t.id,
                "video_id": t.video_id,
                "video_name": video.original_filename if video else "unknown",
                "started_at": t.started_at.isoformat() if t.started_at else None,
            }
        )

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


@router.get("/sources")
def list_video_sources():
    """
    列出所有已掛載的影片來源目錄（快速版本，不計算影片數量）。

    只確認目錄存在且非空，立即回傳。影片數量請另呼叫
    GET /api/batch/sources/{slot}/count（非同步，逐一取得）。
    """
    sources = []
    videos_root = Path("/videos")

    if not videos_root.exists():
        logger.info("/videos 根目錄不存在，請確認 docker-compose volumes 設定")
        return {"sources": []}

    for slot in range(1, 6):
        source_path = videos_root / f"source{slot}"
        if not source_path.exists() or not source_path.is_dir():
            continue

        # 排除空目錄（未設定的 VIDEO_DIR_N 掛載到 .docker-empty）
        try:
            entries = list(source_path.iterdir())
        except PermissionError:
            logger.warning("來源 %d 無讀取權限: %s", slot, source_path)
            continue

        if not entries:
            continue

        logger.info("偵測到來源 %d: %s", slot, source_path)
        sources.append(
            {
                "slot": slot,
                "container_path": str(source_path),
                "display_name": f"來源 {slot}",
                "video_count": None,  # 由前端呼叫 /sources/{slot}/count 非同步取得
            }
        )

    logger.info("共偵測到 %d 個影片來源", len(sources))
    return {"sources": sources}


@router.get("/sources/{slot}/count")
def count_source_videos(slot: int):
    """
    計算指定來源的影片數量（遞迴掃描）。

    影片多時可能需數秒，請由前端以非同步方式逐一呼叫，
    避免 /sources 端點阻塞。進度可在 docker logs 觀察。
    """
    if not 1 <= slot <= 5:
        raise HTTPException(status_code=400, detail="slot 必須介於 1~5")

    source_path = Path("/videos") / f"source{slot}"
    if not source_path.exists() or not source_path.is_dir():
        raise HTTPException(status_code=404, detail=f"來源 {slot} 不存在")

    logger.info("開始統計來源 %d 的影片數量: %s", slot, source_path)
    video_count = sum(
        1 for f in source_path.rglob("*") if f.suffix.lower() in settings.SUPPORTED_VIDEO_EXTENSIONS
    )
    logger.info("來源 %d 統計完成: 共 %d 支影片", slot, video_count)
    return {"slot": slot, "video_count": video_count}


@router.get("/browse")
def browse_directory(path: str = "/videos"):
    """
    列出指定路徑下的子目錄（僅限 /videos 範圍內）。
    用於 UI 提供目錄瀏覽功能。
    """
    # 安全邊界：只允許瀏覽 /videos 下的路徑
    requested = Path(path).resolve()
    allowed_root = Path("/videos").resolve()

    try:
        requested.relative_to(allowed_root)
    except ValueError:
        raise HTTPException(400, f"不允許瀏覽 /videos 以外的路徑: {path}") from None

    if not requested.exists():
        raise HTTPException(404, f"路徑不存在: {path}")
    if not requested.is_dir():
        raise HTTPException(400, f"不是目錄: {path}")

    subdirs = []
    try:
        for entry in sorted(requested.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                subdirs.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                    }
                )
    except PermissionError:
        raise HTTPException(403, "無讀取權限") from None

    return {
        "current": str(requested),
        "parent": str(requested.parent) if requested != allowed_root else None,
        "subdirs": subdirs,
    }
