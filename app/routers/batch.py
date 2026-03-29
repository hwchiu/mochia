"""批量操作 API：目錄掃描、全部加入佇列、佇列統計"""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, TaskQueue, Video, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/batch", tags=["batch"])


# ─── 自動掃描狀態（容器啟動時背景執行）────────────────────────


@dataclass
class AutoScanState:
    status: str = "idle"  # idle | running | done | error
    current_source: str | None = None
    sources_total: int = 0
    sources_done: int = 0
    total_found: int = 0
    total_registered: int = 0
    total_skipped: int = 0
    error: str | None = None
    results: list = field(default_factory=list)


_auto_scan = AutoScanState()
_auto_scan_lock = threading.Lock()


# ─── 手動掃描狀態（使用者從 UI 觸發）────────────────────────


@dataclass
class ManualScanState:
    status: str = "idle"  # idle | running | done | error
    path: str | None = None
    files_scanned: int = 0
    files_found: int = 0
    registered: int = 0
    skipped: int = 0
    current_dir: str | None = None
    error: str | None = None


_manual_scan = ManualScanState()
_manual_scan_lock = threading.Lock()


def run_auto_scan() -> None:
    """容器啟動後在背景執行，掃描所有 /videos/source1~5 並登錄影片。"""
    videos_root = Path("/videos")
    if not videos_root.exists():
        logger.info("[auto-scan] /videos 目錄不存在，跳過自動掃描")
        return

    sources = []
    for slot in range(1, 6):
        p = videos_root / f"source{slot}"
        if p.exists() and p.is_dir():
            try:
                if list(p.iterdir()):  # 非空
                    sources.append(p)
            except PermissionError:
                logger.warning("[auto-scan] 無權限讀取: %s", p)

    if not sources:
        logger.info("[auto-scan] 未偵測到任何影片來源，跳過")
        return

    with _auto_scan_lock:
        _auto_scan.status = "running"
        _auto_scan.sources_total = len(sources)
        _auto_scan.sources_done = 0
        _auto_scan.results = []

    logger.info("[auto-scan] 開始掃描 %d 個來源", len(sources))

    for src in sources:
        with _auto_scan_lock:
            _auto_scan.current_source = str(src)
        logger.info("[auto-scan] 掃描中: %s", src)
        try:
            db = SessionLocal()
            try:
                result = _scan_directory(str(src), db)
            finally:
                db.close()
            with _auto_scan_lock:
                _auto_scan.sources_done += 1
                _auto_scan.total_found += result["found"]
                _auto_scan.total_registered += result["registered"]
                _auto_scan.total_skipped += result["skipped"]
                _auto_scan.results.append({"source": str(src), **result})
            logger.info(
                "[auto-scan] %s 完成: 發現 %d，新登錄 %d，跳過 %d",
                src.name,
                result["found"],
                result["registered"],
                result["skipped"],
            )
        except Exception as e:
            logger.error("[auto-scan] %s 掃描失敗: %s", src, e)
            with _auto_scan_lock:
                _auto_scan.sources_done += 1
                _auto_scan.results.append({"source": str(src), "error": str(e)})

    with _auto_scan_lock:
        _auto_scan.status = "done"
        _auto_scan.current_source = None

    logger.info(
        "[auto-scan] 全部完成: 共發現 %d，新登錄 %d，跳過 %d",
        _auto_scan.total_found,
        _auto_scan.total_registered,
        _auto_scan.total_skipped,
    )


_PROGRESS_INTERVAL = 100  # 每處理 N 個檔案回報一次進度


def _scan_directory(scan_path: str, db: Session, progress_cb=None) -> dict:
    """掃描目錄，將新影片登錄到資料庫（不複製檔案）。

    演算法：
    - 單次 rglob("*") 走完目錄樹，副檔名用 set lookup（O(1)）過濾
    - 預先載入 DB 所有 file_path 到 set，避免 N 次 SELECT
    - 批次 add + 一次 commit
    - progress_cb(files_scanned, found, registered, skipped, current_dir) 每 100 檔回呼
    """
    base = Path(scan_path)
    if not base.exists():
        raise ValueError(f"目錄不存在: {scan_path}")
    if not base.is_dir():
        raise ValueError(f"路徑不是目錄: {scan_path}")

    ext_set = {e.lower() for e in settings.SUPPORTED_VIDEO_EXTENSIONS}

    # 一次 query 取得所有已登錄路徑，避免每個檔案都打 DB
    existing_paths: set[str] = {
        row[0] for row in db.query(Video.file_path).filter(Video.file_path.isnot(None)).all()
    }

    found = skipped = registered = files_scanned = 0
    new_videos = []

    # 單次遍歷，副檔名 set lookup
    for entry in base.rglob("*"):
        if not entry.is_file():
            continue
        files_scanned += 1

        if entry.suffix.lower() not in ext_set:
            if progress_cb and files_scanned % _PROGRESS_INTERVAL == 0:
                progress_cb(files_scanned, found, registered, skipped, str(entry.parent))
            continue

        found += 1
        abs_path = str(entry.resolve())

        if abs_path in existing_paths:
            skipped += 1
        else:
            new_videos.append(
                Video(
                    id=uuid.uuid4().hex,
                    filename=entry.name,
                    original_filename=entry.name,
                    file_path=abs_path,
                    source="local_scan",
                    file_size=entry.stat().st_size,
                    duration=None,  # 分析時由 ffprobe 取得
                    status="pending",
                )
            )
            existing_paths.add(abs_path)  # 防止同一次掃描內重複
            registered += 1

        if progress_cb and files_scanned % _PROGRESS_INTERVAL == 0:
            progress_cb(files_scanned, found, registered, skipped, str(entry.parent))

    if new_videos:
        db.add_all(new_videos)
        db.commit()

    logger.info(f"掃描完成: 發現 {found}，新登錄 {registered}，跳過 {skipped}")
    return {"found": found, "registered": registered, "skipped": skipped}


# 允許測試替換 session factory（測試時替換為 test session maker）
_scan_session_factory = SessionLocal


def _run_manual_scan(scan_path: str) -> None:
    """背景執行手動掃描，持續更新 _manual_scan 狀態。"""
    db = _scan_session_factory()
    try:

        def _progress(
            files_scanned: int, found: int, registered: int, skipped: int, current_dir: str
        ) -> None:
            with _manual_scan_lock:
                _manual_scan.files_scanned = files_scanned
                _manual_scan.files_found = found
                _manual_scan.registered = registered
                _manual_scan.skipped = skipped
                _manual_scan.current_dir = current_dir

        result = _scan_directory(scan_path, db, progress_cb=_progress)
        with _manual_scan_lock:
            _manual_scan.status = "done"
            _manual_scan.files_found = result["found"]
            _manual_scan.registered = result["registered"]
            _manual_scan.skipped = result["skipped"]
    except Exception as e:
        with _manual_scan_lock:
            _manual_scan.status = "error"
            _manual_scan.error = str(e)
        logger.exception("手動掃描失敗: %s", scan_path)
    finally:
        db.close()


@router.post("/scan")
def scan_directory(
    path: str,
    background_tasks: BackgroundTasks,
):
    """
    掃描本地目錄，將影片路徑登錄至資料庫（不複製檔案）。
    立即回傳，掃描在背景執行；用 GET /api/batch/manual-scan-status 輪詢進度。
    """
    scan_path = Path(path)
    if not scan_path.exists():
        raise HTTPException(400, f"目錄不存在: {path}")
    if not scan_path.is_dir():
        raise HTTPException(400, f"路徑不是目錄: {path}")

    with _manual_scan_lock:
        if _manual_scan.status == "running":
            raise HTTPException(409, "掃描正在進行中，請稍候")
        _manual_scan.status = "running"
        _manual_scan.path = path
        _manual_scan.files_scanned = 0
        _manual_scan.files_found = 0
        _manual_scan.registered = 0
        _manual_scan.skipped = 0
        _manual_scan.current_dir = path
        _manual_scan.error = None

    background_tasks.add_task(_run_manual_scan, path)
    return {"status": "started"}


@router.get("/manual-scan-status")
def get_manual_scan_status():
    """回傳手動掃描的即時進度。"""
    with _manual_scan_lock:
        return {
            "status": _manual_scan.status,
            "path": _manual_scan.path,
            "files_scanned": _manual_scan.files_scanned,
            "files_found": _manual_scan.files_found,
            "registered": _manual_scan.registered,
            "skipped": _manual_scan.skipped,
            "current_dir": _manual_scan.current_dir,
            "error": _manual_scan.error,
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


@router.get("/scan-status")
def get_scan_status():
    """回傳容器啟動時自動掃描的即時進度。"""
    with _auto_scan_lock:
        return {
            "status": _auto_scan.status,
            "current_source": _auto_scan.current_source,
            "sources_total": _auto_scan.sources_total,
            "sources_done": _auto_scan.sources_done,
            "total_found": _auto_scan.total_found,
            "total_registered": _auto_scan.total_registered,
            "total_skipped": _auto_scan.total_skipped,
            "error": _auto_scan.error,
            "results": _auto_scan.results,
        }


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
                try:
                    resolved = entry.resolve()
                    resolved.relative_to(allowed_root)  # 若超出邊界會 raise ValueError
                except ValueError:
                    continue  # 跳過指向邊界外的 symlink
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
