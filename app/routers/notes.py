"""個人筆記 API — Markdown 格式"""
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, Video, VideoNote

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notes", tags=["notes"])


class NoteUpsertRequest(BaseModel):
    content: str


@router.get("/{video_id}")
def get_note(video_id: str, db: Session = Depends(get_db)):
    """取得影片的個人筆記"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    note = db.query(VideoNote).filter(VideoNote.video_id == video_id).first()
    return {
        "video_id": video_id,
        "content": note.content if note else "",
        "updated_at": note.updated_at.isoformat() if note else None,
    }


@router.put("/{video_id}")
def upsert_note(video_id: str, body: NoteUpsertRequest, db: Session = Depends(get_db)):
    """新增或更新影片的個人筆記（Markdown 格式）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    note = db.query(VideoNote).filter(VideoNote.video_id == video_id).first()
    if note:
        note.content = body.content
        note.updated_at = datetime.utcnow()
    else:
        note = VideoNote(
            id=str(uuid.uuid4()),
            video_id=video_id,
            content=body.content,
        )
        db.add(note)

    db.commit()
    return {
        "video_id": video_id,
        "content": note.content,
        "updated_at": note.updated_at.isoformat(),
    }


@router.delete("/{video_id}")
def delete_note(video_id: str, db: Session = Depends(get_db)):
    """刪除影片的個人筆記"""
    note = db.query(VideoNote).filter(VideoNote.video_id == video_id).first()
    if note:
        db.delete(note)
        db.commit()
    return {"message": "筆記已刪除"}
