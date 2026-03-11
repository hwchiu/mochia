"""學習統計儀表板 API"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Classification, Label, ReviewRecord, Video, VideoLabel, get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    """全局學習概覽統計"""
    now = datetime.utcnow()

    # Single query for all status counts
    status_counts = (
        db.query(
            Video.status,
            func.count(Video.id).label("cnt"),
        )
        .group_by(Video.status)
        .all()
    )
    counts = {row.status: row.cnt for row in status_counts}

    total = sum(counts.values())
    completed = counts.get("completed", 0)
    failed = counts.get("failed", 0)
    pending = counts.get("pending", 0) + counts.get("queued", 0) + counts.get("processing", 0)

    reviewed = db.query(Video).filter(Video.status == "completed", Video.review_count > 0).count()
    never_reviewed = completed - reviewed

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
    total_review_sessions = db.query(ReviewRecord).count()

    # 分類分布
    cats = db.query(Classification).all()
    cat_dist: dict[str, int] = {}
    for c in cats:
        if c.category:
            cat_dist[c.category] = cat_dist.get(c.category, 0) + 1

    # 標籤統計 — batch count with GROUP BY instead of per-label COUNT
    labels = db.query(Label).all()
    label_counts_rows = (
        db.query(VideoLabel.label_id, func.count(VideoLabel.id).label("cnt"))
        .group_by(VideoLabel.label_id)
        .all()
    )
    label_counts = {row.label_id: row.cnt for row in label_counts_rows}

    label_stats = [
        {"id": lbl.id, "name": lbl.name, "color": lbl.color, "count": label_counts.get(lbl.id, 0)}
        for lbl in labels
    ]
    label_stats.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_videos": total,
        "completed": completed,
        "pending": pending,
        "failed": failed,
        "reviewed": reviewed,
        "never_reviewed": never_reviewed,
        "due_today": due_today,
        "reviewed_today": reviewed_today,
        "total_review_sessions": total_review_sessions,
        "category_distribution": cat_dist,
        "label_stats": label_stats,
    }


@router.get("/daily")
def get_daily_stats(days: int = 30, db: Session = Depends(get_db)):
    """近 N 天每日複習量"""
    now = datetime.utcnow()
    result = []
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = (
            db.query(ReviewRecord)
            .filter(
                ReviewRecord.reviewed_at >= day_start,
                ReviewRecord.reviewed_at < day_end,
            )
            .count()
        )
        result.append({"date": day_start.strftime("%Y-%m-%d"), "reviews": count})
    return {"days": days, "data": result}


@router.get("/confidence")
def get_confidence_distribution(db: Session = Depends(get_db)):
    """信心程度分布（最近一次複習的信心值）"""
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    # 取每部影片最新的複習紀錄信心值
    videos = db.query(Video).filter(Video.status == "completed", Video.review_count > 0).all()
    for video in videos:
        latest = (
            db.query(ReviewRecord)
            .filter(ReviewRecord.video_id == video.id)
            .order_by(ReviewRecord.reviewed_at.desc())
            .first()
        )
        if latest and isinstance(latest.confidence, int) and latest.confidence in dist:
            dist[latest.confidence] += 1

    labels = {1: "完全不懂", 2: "模糊記得", 3: "大致理解", 4: "掌握良好", 5: "完全掌握"}
    return {"distribution": [{"level": k, "label": labels[k], "count": v} for k, v in dist.items()]}


@router.get("/top-reviewed")
def get_top_reviewed(limit: int = 10, db: Session = Depends(get_db)):
    """複習次數最多的影片"""
    videos = (
        db.query(Video)
        .filter(Video.status == "completed", Video.review_count > 0)
        .order_by(Video.review_count.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": v.id,
                "filename": v.original_filename or v.filename,
                "review_count": v.review_count or 0,
                "last_reviewed_at": v.last_reviewed_at.isoformat() if v.last_reviewed_at else None,
                "sr_ease_factor": round(v.sr_ease_factor or 2.5, 2),
            }
            for v in videos
        ]
    }
