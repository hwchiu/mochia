"""複習系統 API — SM-2 間隔重複排程"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db, Video, ReviewRecord, Summary, Classification, VideoLabel, Label

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/review", tags=["review"])


class MarkReviewedRequest(BaseModel):
    confidence: int = Field(..., ge=1, le=5, description="複習信心程度 1(完全不懂)~5(完全掌握)")


def _sm2_update(video: Video, confidence: int) -> None:
    """
    SM-2 算法更新複習排程。
    confidence 1-2 = 需要重複學習 (reset)
    confidence 3   = 通過，輕微增加
    confidence 4-5 = 輕鬆通過，顯著增加
    """
    # 轉換為 SM-2 的 quality (0-5)
    quality = confidence - 1  # 1→0, 2→1, 3→2, 4→3, 5→4

    if quality < 2:
        # 答錯或非常困難 → 重置
        video.sr_repetitions = 0
        video.sr_interval = 1
    else:
        # 正確回答
        if video.sr_repetitions == 0:
            video.sr_interval = 1
        elif video.sr_repetitions == 1:
            video.sr_interval = 6
        else:
            video.sr_interval = round((video.sr_interval or 1) * (video.sr_ease_factor or 2.5))
        video.sr_repetitions = (video.sr_repetitions or 0) + 1

    # 更新易難係數 EF
    ef = (video.sr_ease_factor or 2.5) + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    video.sr_ease_factor = max(1.3, ef)

    # 下次複習時間
    video.sr_next_review_at = datetime.utcnow() + timedelta(days=video.sr_interval)
    video.last_reviewed_at = datetime.utcnow()
    video.review_count = (video.review_count or 0) + 1


def _video_to_review_item(video: Video, db: Session) -> dict:
    summary = db.query(Summary).filter(Summary.video_id == video.id).first()
    cls = db.query(Classification).filter(Classification.video_id == video.id).first()
    vl_rows = db.query(VideoLabel).filter(VideoLabel.video_id == video.id).all()
    label_ids = [vl.label_id for vl in vl_rows]
    labels = []
    if label_ids:
        lbls = db.query(Label).filter(Label.id.in_(label_ids)).all()
        labels = [{"id": l.id, "name": l.name, "color": l.color} for l in lbls]

    return {
        "id": video.id,
        "filename": video.original_filename or video.filename,
        "category": cls.category if cls else None,
        "labels": labels,
        "summary_preview": (summary.summary or "")[:200] if summary else "",
        "key_points_count": len(json.loads(summary.key_points or "[]")) if summary and summary.key_points else 0,
        "review_count": video.review_count or 0,
        "last_reviewed_at": video.last_reviewed_at.isoformat() if video.last_reviewed_at else None,
        "sr_next_review_at": video.sr_next_review_at.isoformat() if video.sr_next_review_at else None,
        "sr_interval": video.sr_interval or 1,
        "sr_ease_factor": round(video.sr_ease_factor or 2.5, 2),
        "sr_repetitions": video.sr_repetitions or 0,
    }


@router.post("/{video_id}/mark")
def mark_reviewed(
    video_id: str,
    body: MarkReviewedRequest,
    db: Session = Depends(get_db),
):
    """標記影片已複習，並根據信心程度更新 SM-2 排程"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    # 寫入複習紀錄
    record = ReviewRecord(
        id=str(uuid.uuid4()),
        video_id=video_id,
        confidence=body.confidence,
    )
    db.add(record)

    # 更新 SM-2
    _sm2_update(video, body.confidence)
    db.commit()

    return {
        "message": "已記錄複習",
        "video_id": video_id,
        "confidence": body.confidence,
        "sr_interval": video.sr_interval,
        "sr_next_review_at": video.sr_next_review_at.isoformat(),
        "review_count": video.review_count,
    }


@router.get("/due")
def get_due_reviews(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """取得今日到期的複習影片清單（優先按到期時間排序）"""
    now = datetime.utcnow()

    # 未曾複習過 OR sr_next_review_at <= now
    videos = (
        db.query(Video)
        .filter(
            Video.status == "completed",
            (Video.sr_next_review_at <= now) | (Video.sr_next_review_at.is_(None)),
        )
        .order_by(Video.sr_next_review_at.asc().nullsfirst())
        .limit(limit)
        .all()
    )

    return {
        "total": len(videos),
        "items": [_video_to_review_item(v, db) for v in videos],
    }


@router.get("/upcoming")
def get_upcoming_reviews(
    days: int = 7,
    db: Session = Depends(get_db),
):
    """取得未來 N 天的複習排程"""
    now = datetime.utcnow()
    future = now + timedelta(days=days)
    videos = (
        db.query(Video)
        .filter(
            Video.status == "completed",
            Video.sr_next_review_at > now,
            Video.sr_next_review_at <= future,
        )
        .order_by(Video.sr_next_review_at.asc())
        .all()
    )
    return {
        "days": days,
        "total": len(videos),
        "items": [_video_to_review_item(v, db) for v in videos],
    }


@router.get("/history/{video_id}")
def get_review_history(
    video_id: str,
    db: Session = Depends(get_db),
):
    """取得單部影片的完整複習紀錄"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    records = (
        db.query(ReviewRecord)
        .filter(ReviewRecord.video_id == video_id)
        .order_by(ReviewRecord.reviewed_at.desc())
        .all()
    )

    return {
        "video_id": video_id,
        "review_count": video.review_count or 0,
        "sr_interval": video.sr_interval,
        "sr_ease_factor": round(video.sr_ease_factor or 2.5, 2),
        "sr_next_review_at": video.sr_next_review_at.isoformat() if video.sr_next_review_at else None,
        "records": [
            {
                "id": r.id,
                "confidence": r.confidence,
                "reviewed_at": r.reviewed_at.isoformat(),
            }
            for r in records
        ],
    }


@router.get("/stats")
def get_review_stats(db: Session = Depends(get_db)):
    """全局複習統計"""
    from sqlalchemy import func

    total_completed = db.query(Video).filter(Video.status == "completed").count()
    reviewed_at_least_once = (
        db.query(Video)
        .filter(Video.status == "completed", Video.review_count > 0)
        .count()
    )
    never_reviewed = total_completed - reviewed_at_least_once

    now = datetime.utcnow()
    due_today = (
        db.query(Video)
        .filter(
            Video.status == "completed",
            (Video.sr_next_review_at <= now) | (Video.sr_next_review_at.is_(None)),
        )
        .count()
    )

    # 今日已複習
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reviewed_today = (
        db.query(ReviewRecord)
        .filter(ReviewRecord.reviewed_at >= today_start)
        .count()
    )

    # 近7天每天複習數量
    daily = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.reviewed_at >= day_start, ReviewRecord.reviewed_at < day_end)
            .count()
        )
        daily.append({"date": day_start.strftime("%m/%d"), "count": count})

    return {
        "total_completed": total_completed,
        "reviewed_at_least_once": reviewed_at_least_once,
        "never_reviewed": never_reviewed,
        "due_today": due_today,
        "reviewed_today": reviewed_today,
        "daily_review_counts": daily,
    }
