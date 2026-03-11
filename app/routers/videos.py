"""影片管理 API：列表、詳情、刪除、單筆加入佇列"""
import uuid
import shutil
import logging
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, Video, TaskQueue, Label, VideoLabel
from app.config import settings
from app.services.audio_extractor import get_video_duration

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/videos", tags=["videos"])


def _video_to_dict(v: Video) -> dict:
    return {
        "id": v.id,
        "filename": v.filename,
        "original_filename": v.original_filename,
        "file_path": v.file_path,
        "source": v.source,
        "upload_date": v.upload_date.isoformat() if v.upload_date else None,
        "file_size": v.file_size,
        "duration": v.duration,
        "status": v.status,
        "error_message": v.error_message,
        # 複習追蹤
        "review_count": v.review_count or 0,
        "last_reviewed_at": v.last_reviewed_at.isoformat() if v.last_reviewed_at else None,
        "sr_next_review_at": v.sr_next_review_at.isoformat() if v.sr_next_review_at else None,
        "sr_interval": v.sr_interval or 1,
        "sr_ease_factor": round(v.sr_ease_factor or 2.5, 2),
        "sr_repetitions": v.sr_repetitions or 0,
    }


@router.post("/upload")
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """上傳影片檔案"""
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"不支援的檔案格式: {ext}")

    video_id = uuid.uuid4().hex
    safe_name = f"{video_id}{ext}"
    dest = settings.UPLOAD_DIR / safe_name

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = dest.stat().st_size
    duration = get_video_duration(dest)

    video = Video(
        id=video_id,
        filename=safe_name,
        original_filename=file.filename,
        file_path=str(dest),
        source="uploaded",
        file_size=file_size,
        duration=duration,
        status="pending",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return _video_to_dict(video)


@router.get("/")
def list_videos(
    status: Optional[str] = None,
    source: Optional[str] = None,
    labels: Optional[str] = None,   # comma-separated label names, AND logic
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """列出所有影片，支援狀態、來源和標籤篩選（AND 邏輯）"""
    query = db.query(Video)
    if status:
        query = query.filter(Video.status == status)
    if source:
        query = query.filter(Video.source == source)
    if labels:
        label_names = [n.strip() for n in labels.split(",") if n.strip()]
        for name in label_names:
            lbl = db.query(Label).filter(Label.name == name).first()
            if lbl:
                sub = db.query(VideoLabel.video_id).filter(VideoLabel.label_id == lbl.id).subquery()
                query = query.filter(Video.id.in_(sub))
            else:
                # 如果標籤不存在，沒有影片能匹配
                query = query.filter(Video.id == None)  # noqa: E711
    total = query.count()
    videos = query.order_by(Video.upload_date.desc()).offset(skip).limit(limit).all()

    # 為每部影片附帶標籤資訊
    items = []
    for v in videos:
        d = _video_to_dict(v)
        vl_rows = db.query(VideoLabel).filter(VideoLabel.video_id == v.id).all()
        d["labels"] = []
        for row in vl_rows:
            lbl = db.query(Label).filter(Label.id == row.label_id).first()
            if lbl:
                d["labels"].append({"id": lbl.id, "name": lbl.name, "color": lbl.color})
        items.append(d)

    return {"total": total, "items": items}


@router.get("/{video_id}")
def get_video(video_id: str, db: Session = Depends(get_db)):
    """取得單一影片詳情"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    return _video_to_dict(video)


@router.delete("/{video_id}")
def delete_video(video_id: str, db: Session = Depends(get_db)):
    """刪除影片（僅刪除 DB 記錄，上傳的檔案也一並刪除）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    # 只刪除上傳到 uploads/ 的檔案，不刪除本地掃描的原始檔案
    if video.source == "uploaded" and video.file_path:
        Path(video.file_path).unlink(missing_ok=True)

    db.query(TaskQueue).filter(TaskQueue.video_id == video_id).delete()
    db.delete(video)
    db.commit()
    return {"message": "已刪除"}


# ── 影片串流 ─────────────────────────────────────────────────────────

_MIME_MAP = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".wmv": "video/x-ms-wmv",
    ".m4v": "video/mp4",
    ".flv": "video/x-flv",
}


@router.get("/{video_id}/stream")
def stream_video(video_id: str, request: Request, db: Session = Depends(get_db)):
    """
    串流播放影片（支援 HTTP Range Request，瀏覽器可直接 seek）。
    瀏覽器不支援的格式（wmv 等）會回傳 415 讓前端顯示提示。
    """
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    file_path = video.file_path
    if not file_path or not Path(file_path).exists():
        raise HTTPException(404, "影片檔案不存在（可能已移動或刪除）")

    ext = Path(file_path).suffix.lower()
    mime = _MIME_MAP.get(ext)

    # 不支援的格式 → 回傳 415，前端顯示開啟本地播放器提示
    _BROWSER_UNSUPPORTED = {".wmv", ".mkv", ".avi", ".flv"}
    if ext in _BROWSER_UNSUPPORTED:
        raise HTTPException(
            status_code=415,
            detail=f"瀏覽器不支援 {ext.upper()} 格式直接播放",
        )

    if not mime:
        mime = "application/octet-stream"

    # FileResponse 內建支援 Range Request（Starlette 實作）
    return FileResponse(
        path=file_path,
        media_type=mime,
        headers={"Accept-Ranges": "bytes"},
    )


@router.post("/{video_id}/open-local")
def open_local_player(video_id: str, db: Session = Depends(get_db)):
    """
    呼叫系統預設播放器開啟影片（僅供本機使用）。
    macOS: open, Linux: xdg-open。
    """
    import platform
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    file_path = video.file_path
    if not file_path or not Path(file_path).exists():
        raise HTTPException(404, "影片檔案不存在")

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", file_path])
        elif system == "Linux":
            subprocess.Popen(["xdg-open", file_path])
        elif system == "Windows":
            subprocess.Popen(["start", "", file_path], shell=True)
        else:
            raise HTTPException(400, f"不支援的作業系統：{system}")
    except FileNotFoundError as e:
        raise HTTPException(500, f"無法開啟播放器：{e}")

    return {"message": "已傳送開啟指令"}
