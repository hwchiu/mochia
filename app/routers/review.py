"""複習系統 API — SM-2 間隔重複排程"""

import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import Classification, Label, ReviewRecord, Summary, Video, VideoLabel, get_db
from app.services.review_service import calculate_next_review
from app.utils import safe_json_loads

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/review", tags=["review"])


class MarkReviewedRequest(BaseModel):
    confidence: int = Field(..., ge=1, le=5, description="複習信心程度 1(完全不懂)~5(完全掌握)")


def _sm2_update(video: Video, confidence: int) -> None:
    """Apply SM-2 algorithm to video using the review service."""
    metrics = calculate_next_review(
        confidence=confidence,
        current_interval=video.sr_interval or 1,
        current_ease_factor=video.sr_ease_factor or 2.5,
        current_repetitions=video.sr_repetitions or 0,
    )
    video.sr_interval = metrics.interval  # type: ignore[assignment]
    video.sr_ease_factor = metrics.ease_factor  # type: ignore[assignment]
    video.sr_repetitions = metrics.repetitions  # type: ignore[assignment]
    video.sr_next_review_at = metrics.next_review_at  # type: ignore[assignment]
    video.last_reviewed_at = datetime.utcnow()  # type: ignore[assignment]
    video.review_count = (video.review_count or 0) + 1  # type: ignore[assignment]


def _build_review_maps(videos: list[Video], db: Session) -> tuple[dict, dict, dict]:
    """Batch-fetch summaries, classifications, and labels for a list of videos."""
    video_ids = [v.id for v in videos]

    summaries = db.query(Summary).filter(Summary.video_id.in_(video_ids)).all()
    summaries_map = {s.video_id: s for s in summaries}

    classifications = db.query(Classification).filter(Classification.video_id.in_(video_ids)).all()
    classifications_map = {c.video_id: c for c in classifications}

    vl_rows = db.query(VideoLabel).filter(VideoLabel.video_id.in_(video_ids)).all()
    vl_by_video: dict = {}
    for vl in vl_rows:
        vl_by_video.setdefault(vl.video_id, []).append(vl)
    label_ids = list({vl.label_id for vl in vl_rows})
    labels_lookup: dict = {}
    if label_ids:
        lbls = db.query(Label).filter(Label.id.in_(label_ids)).all()
        labels_lookup = {lbl.id: lbl for lbl in lbls}

    labels_by_video: dict = {}
    for vid_id, vls in vl_by_video.items():
        labels_by_video[vid_id] = [
            {
                "id": labels_lookup[vl.label_id].id,
                "name": labels_lookup[vl.label_id].name,
                "color": labels_lookup[vl.label_id].color,
            }
            for vl in vls
            if vl.label_id in labels_lookup
        ]

    return summaries_map, classifications_map, labels_by_video


def _video_to_review_item(
    video: Video,
    summary: Summary | None,
    classification: Classification | None,
    labels: list[dict],
) -> dict:
    return {
        "id": video.id,
        "filename": video.original_filename or video.filename,
        "category": classification.category if classification else None,
        "labels": labels,
        "summary_preview": (summary.summary or "")[:200] if summary else "",
        "key_points_count": len(safe_json_loads(summary.key_points if summary else None, [])),  # type: ignore[arg-type]
        "review_count": video.review_count or 0,
        "last_reviewed_at": video.last_reviewed_at.isoformat() if video.last_reviewed_at else None,
        "sr_next_review_at": video.sr_next_review_at.isoformat()
        if video.sr_next_review_at
        else None,
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

    record = ReviewRecord(
        id=str(uuid.uuid4()),
        video_id=video_id,
        confidence=body.confidence,
    )
    db.add(record)

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

    summaries_map, classifications_map, labels_by_video = _build_review_maps(videos, db)

    return {
        "total": len(videos),
        "items": [
            _video_to_review_item(
                v,
                summaries_map.get(v.id),
                classifications_map.get(v.id),
                labels_by_video.get(v.id, []),
            )
            for v in videos
        ],
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

    summaries_map, classifications_map, labels_by_video = _build_review_maps(videos, db)

    return {
        "days": days,
        "total": len(videos),
        "items": [
            _video_to_review_item(
                v,
                summaries_map.get(v.id),
                classifications_map.get(v.id),
                labels_by_video.get(v.id, []),
            )
            for v in videos
        ],
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
        "sr_next_review_at": video.sr_next_review_at.isoformat()
        if video.sr_next_review_at
        else None,
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

    total_completed = db.query(Video).filter(Video.status == "completed").count()
    reviewed_at_least_once = (
        db.query(Video).filter(Video.status == "completed", Video.review_count > 0).count()
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

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reviewed_today = db.query(ReviewRecord).filter(ReviewRecord.reviewed_at >= today_start).count()

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
