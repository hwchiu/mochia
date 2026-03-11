from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, Video


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_video_or_404(video_id: str, db: Session = Depends(get_db)) -> Video:
    """Reusable dependency: fetch video by id or raise HTTP 404."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="影片不存在")
    return video
