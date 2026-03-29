"""影片管理 API：列表、詳情、刪除、單筆加入佇列"""

import asyncio
import logging
import os
import shutil
import subprocess
import uuid
from collections.abc import Generator
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import BROWSER_UNSUPPORTED_FORMATS, STREAM_CHUNK_SIZE
from app.database import Label, TaskQueue, Video, VideoLabel, get_db
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
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(400, f"不支援的檔案格式: {ext}")

    video_id = uuid.uuid4().hex
    safe_name = f"{video_id}{ext}"
    dest = settings.UPLOAD_DIR / safe_name

    try:
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, "檔案寫入失敗，請重試") from None

    file_size = dest.stat().st_size
    duration = await asyncio.to_thread(get_video_duration, dest)

    video = Video(
        id=video_id,
        filename=safe_name,
        original_filename=file.filename,
        file_path=str(dest),
        source="uploaded",
        file_size=file_size,
        duration=duration,  # type: ignore[arg-type]
        status="pending",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return _video_to_dict(video)


@router.get("/")
def list_videos(
    status: str | None = None,
    source: str | None = None,
    labels: str | None = None,  # comma-separated label names, AND logic
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
                query = query.filter(Video.id.in_(sub))  # type: ignore[arg-type]
            else:
                # 如果標籤不存在，沒有影片能匹配
                query = query.filter(Video.id == None)  # noqa: E711
    total = query.count()
    videos = query.order_by(Video.upload_date.desc()).offset(skip).limit(limit).all()

    # Fetch all label associations for this page in two queries (avoids N+1)
    video_ids = [v.id for v in videos]
    vl_rows = db.query(VideoLabel).filter(VideoLabel.video_id.in_(video_ids)).all()
    vl_by_video: dict[str, list[VideoLabel]] = {}
    for vl in vl_rows:
        vl_by_video.setdefault(vl.video_id, []).append(vl)  # type: ignore[arg-type]

    label_ids = list({vl.label_id for vl in vl_rows})
    labels_map: dict[str, Label] = {}
    if label_ids:
        lbls = db.query(Label).filter(Label.id.in_(label_ids)).all()
        labels_map = {lbl.id: lbl for lbl in lbls}  # type: ignore[misc]

    items = []
    for v in videos:
        d = _video_to_dict(v)
        d["labels"] = [
            {
                "id": labels_map[vl.label_id].id,
                "name": labels_map[vl.label_id].name,
                "color": labels_map[vl.label_id].color,
            }
            for vl in vl_by_video.get(v.id, [])  # type: ignore[arg-type]
            if vl.label_id in labels_map
        ]
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


def _ffmpeg_transcode_stream(file_path: str) -> Generator[bytes, None, None]:
    """On-the-fly FFmpeg transcode to fragmented MP4 for browser streaming.

    Pipes FFmpeg stdout directly to the HTTP response with no intermediate file,
    so no extra disk space is consumed.  The caller must verify FFmpeg is
    available before creating the StreamingResponse (HTTPException cannot be
    raised safely once streaming has started).
    """
    cmd = [
        "ffmpeg",
        "-i",
        file_path,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-f",
        "mp4",
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1",
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        if process.stdout is None:  # pragma: no cover
            return
        while True:
            chunk = process.stdout.read(STREAM_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        if process.stdout:
            process.stdout.close()
        process.terminate()
        process.wait()


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

    # 瀏覽器不原生支援的格式 → on-the-fly FFmpeg transcode，不儲存暫存檔
    # Guard must happen HERE before StreamingResponse starts — HTTPException
    # cannot be raised safely once the generator has begun yielding bytes.
    if ext in BROWSER_UNSUPPORTED_FORMATS:
        if not shutil.which("ffmpeg"):
            raise HTTPException(503, "FFmpeg 未安裝，無法串流此格式")
        logger.info(f"轉碼串流: {ext} → fragmented MP4 ({file_path})")
        return StreamingResponse(
            _ffmpeg_transcode_stream(file_path),
            media_type="video/mp4",
            headers={"X-Transcoded": "1"},
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
            os.startfile(file_path)  # type: ignore[attr-defined]  # nosec B606
        else:
            raise HTTPException(400, f"不支援的作業系統：{system}")
    except FileNotFoundError as e:
        raise HTTPException(500, f"無法開啟播放器：{e}") from e

    return {"message": "已傳送開啟指令"}
