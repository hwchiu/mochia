"""標籤管理 API"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, Label, VideoLabel, Video

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/labels", tags=["labels"])

# 12-色調色盤，自動循環分配
_PALETTE = [
    "#ef4444", "#f97316", "#eab308", "#22c55e",
    "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899",
    "#06b6d4", "#84cc16", "#f59e0b", "#6366f1",
]


def _next_color(db: Session) -> str:
    count = db.query(Label).count()
    return _PALETTE[count % len(_PALETTE)]


class LabelCreate(BaseModel):
    name: str
    color: str | None = None


# ─── 所有標籤 ───────────────────────────────────────────────
@router.get("/")
def list_labels(db: Session = Depends(get_db)):
    """列出所有標籤，附帶每個標籤的影片數"""
    labels = db.query(Label).order_by(Label.name).all()
    result = []
    for lbl in labels:
        count = db.query(VideoLabel).filter(VideoLabel.label_id == lbl.id).count()
        result.append({
            "id": lbl.id,
            "name": lbl.name,
            "color": lbl.color,
            "video_count": count,
            "created_at": lbl.created_at.isoformat() if lbl.created_at else None,
        })
    return result


@router.post("/", status_code=201)
def create_label(body: LabelCreate, db: Session = Depends(get_db)):
    """建立新標籤（若同名已存在則直接回傳）"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "標籤名稱不可為空")

    existing = db.query(Label).filter(Label.name == name).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "color": existing.color, "created": False}

    color = body.color or _next_color(db)
    lbl = Label(id=uuid.uuid4().hex, name=name, color=color)
    db.add(lbl)
    db.commit()
    db.refresh(lbl)
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color, "created": True}


@router.delete("/{label_id}", status_code=204)
def delete_label(label_id: str, db: Session = Depends(get_db)):
    """刪除標籤（同時移除所有影片關聯）"""
    lbl = db.query(Label).filter(Label.id == label_id).first()
    if not lbl:
        raise HTTPException(404, "標籤不存在")
    db.query(VideoLabel).filter(VideoLabel.label_id == label_id).delete()
    db.delete(lbl)
    db.commit()


# ─── 影片標籤操作（掛在 /api/labels/videos/{id} 下）─────────
@router.get("/videos/{video_id}")
def get_video_labels(video_id: str, db: Session = Depends(get_db)):
    """取得影片的所有標籤"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    rows = db.query(VideoLabel).filter(VideoLabel.video_id == video_id).all()
    result = []
    for row in rows:
        lbl = db.query(Label).filter(Label.id == row.label_id).first()
        if lbl:
            result.append({"id": lbl.id, "name": lbl.name, "color": lbl.color})
    return result


@router.post("/videos/{video_id}", status_code=201)
def add_video_label(video_id: str, body: LabelCreate, db: Session = Depends(get_db)):
    """為影片新增標籤（若標籤不存在則自動建立）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    name = body.name.strip()
    if not name:
        raise HTTPException(400, "標籤名稱不可為空")

    # 取得或建立標籤
    lbl = db.query(Label).filter(Label.name == name).first()
    if not lbl:
        color = body.color or _next_color(db)
        lbl = Label(id=uuid.uuid4().hex, name=name, color=color)
        db.add(lbl)
        db.flush()

    # 避免重複
    already = db.query(VideoLabel).filter(
        VideoLabel.video_id == video_id,
        VideoLabel.label_id == lbl.id,
    ).first()
    if already:
        return {"id": lbl.id, "name": lbl.name, "color": lbl.color, "added": False}

    vl = VideoLabel(id=uuid.uuid4().hex, video_id=video_id, label_id=lbl.id)
    db.add(vl)
    db.commit()
    return {"id": lbl.id, "name": lbl.name, "color": lbl.color, "added": True}


@router.delete("/videos/{video_id}/{label_id}", status_code=204)
def remove_video_label(video_id: str, label_id: str, db: Session = Depends(get_db)):
    """從影片移除標籤"""
    row = db.query(VideoLabel).filter(
        VideoLabel.video_id == video_id,
        VideoLabel.label_id == label_id,
    ).first()
    if not row:
        raise HTTPException(404, "關聯不存在")
    db.delete(row)
    db.commit()
