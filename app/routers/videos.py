"""影片管理 API：列表、詳情、刪除、單筆加入佇列"""
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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
