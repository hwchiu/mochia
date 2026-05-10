"""全文搜尋 API — 基於 SQLite FTS5"""

import json
import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Classification, Label, Summary, Transcript, Video, VideoLabel, get_db
from app.utils import safe_json_loads

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


def _get_fts_conn():
    return sqlite3.connect(str(settings.DATA_DIR / "video_analyzer.db"))


def _format_mmss(sec: float | int | None) -> str | None:
    if sec is None:
        return None
    total = max(0, int(float(sec)))
    mins = total // 60
    secs = total % 60
    return f"{mins:02d}:{secs:02d}"


def rebuild_fts_index(video_id: str, db: Session) -> None:
    """分析完成後更新該影片的 FTS 索引"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        return

    summary_row = db.query(Summary).filter(Summary.video_id == video_id).first()
    transcript_row = db.query(Transcript).filter(Transcript.video_id == video_id).first()

    title = video.original_filename or video.filename or ""
    summary_text = summary_row.summary or "" if summary_row else ""
    transcript_text = (transcript_row.content or "")[:8000] if transcript_row else ""
    kp_text = ""
    if summary_row and summary_row.key_points:
        kps = safe_json_loads(summary_row.key_points, [])
        parts = []
        for kp in kps:
            if isinstance(kp, dict):
                parts.append(kp.get("theme", ""))
                parts.extend(kp.get("points", []))
            elif isinstance(kp, str):
                parts.append(kp)
        kp_text = " ".join(parts)

    conn = _get_fts_conn()
    cur = conn.cursor()
    # 先刪除舊索引（若有），再插入
    cur.execute("DELETE FROM video_fts WHERE video_id = ?", (video_id,))
    cur.execute("DELETE FROM segment_fts WHERE video_id = ?", (video_id,))
    cur.execute(
        "INSERT INTO video_fts(video_id, title, summary, transcript, key_points) VALUES (?,?,?,?,?)",
        (video_id, title, summary_text, transcript_text, kp_text),
    )
    if transcript_row and transcript_row.segments:
        segments = []
        try:
            loaded = json.loads(transcript_row.segments)
            if isinstance(loaded, list):
                segments = loaded
        except Exception:
            segments = []

        for idx, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            start_sec = float(seg.get("start", 0.0) or 0.0)
            end_sec = float(seg.get("end", start_sec) or start_sec)
            cur.execute(
                """
                INSERT INTO segment_fts(video_id, seg_idx, start_sec, end_sec, text)
                VALUES (?,?,?,?,?)
                """,
                (video_id, idx, start_sec, end_sec, text),
            )
    conn.commit()
    conn.close()
    logger.info(f"FTS 索引已更新: {video_id}")


@router.get("/")
def search_videos(
    q: str = Query(..., min_length=1, description="搜尋關鍵字"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    全文搜尋影片（逐字稿、摘要、重點）。
    回傳匹配的影片清單，每筆附帶最相關的摘錄片段。
    """
    if not q.strip():
        raise HTTPException(400, "搜尋關鍵字不可為空")

    conn = _get_fts_conn()
    cur = conn.cursor()

    try:
        # 先查 segment 級命中（可直接跳時間戳）
        cur.execute(
            """
            SELECT
                video_id,
                start_sec,
                end_sec,
                snippet(segment_fts, 4, '<mark>', '</mark>', '...', 24) AS seg_snip,
                rank
            FROM segment_fts
            WHERE segment_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (q, limit),
        )
        segment_rows = cur.fetchall()

        # 再查影片層命中（摘要/逐字稿）
        cur.execute(
            """
            SELECT
                video_id,
                highlight(video_fts, 1, '<mark>', '</mark>') AS title_hl,
                highlight(video_fts, 2, '<mark>', '</mark>') AS summary_hl,
                snippet(video_fts, 3, '<mark>', '</mark>', '...', 32) AS transcript_snip,
                snippet(video_fts, 4, '<mark>', '</mark>', '...', 20) AS kp_snip,
                rank
            FROM video_fts
            WHERE video_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (q, limit),
        )
        video_rows = cur.fetchall()
    except sqlite3.OperationalError as e:
        logger.warning(f"FTS 查詢錯誤: {e}")
        segment_rows = []
        video_rows = []
    finally:
        conn.close()

    if not segment_rows and not video_rows:
        return {"query": q, "total": 0, "items": []}

    # 先保留每個影片第一筆 segment 命中
    segment_hit_map: dict[str, dict] = {}
    for vid_id, start_sec, end_sec, seg_snip, _rank in segment_rows:
        if vid_id not in segment_hit_map:
            segment_hit_map[vid_id] = {
                "start_sec": float(start_sec) if start_sec is not None else None,
                "end_sec": float(end_sec) if end_sec is not None else None,
                "segment_snippet": seg_snip or "",
            }

    # 合併排序：segment 命中優先，再補影片層命中
    ordered_video_ids: list[str] = []
    for vid_id, *_rest in segment_rows:
        if vid_id not in ordered_video_ids:
            ordered_video_ids.append(vid_id)
    for vid_id, *_rest in video_rows:
        if vid_id not in ordered_video_ids:
            ordered_video_ids.append(vid_id)
    ordered_video_ids = ordered_video_ids[:limit]

    # 取得影片詳細資訊
    video_ids = ordered_video_ids
    videos = {v.id: v for v in db.query(Video).filter(Video.id.in_(video_ids)).all()}
    classifications = {
        c.video_id: c
        for c in db.query(Classification).filter(Classification.video_id.in_(video_ids)).all()
    }
    # 取得 labels
    vl_rows = db.query(VideoLabel).filter(VideoLabel.video_id.in_(video_ids)).all()
    label_ids = [vl.label_id for vl in vl_rows]
    labels_map = {lbl.id: lbl for lbl in db.query(Label).filter(Label.id.in_(label_ids)).all()}
    video_labels: dict[str, list] = {}
    for vl in vl_rows:
        lbl = labels_map.get(vl.label_id)
        if lbl:
            video_labels.setdefault(vl.video_id, []).append(  # type: ignore[arg-type]
                {"id": lbl.id, "name": lbl.name, "color": lbl.color}
            )

    video_row_map = {row[0]: row for row in video_rows}
    items = []
    for vid_id in ordered_video_ids:
        video = videos.get(vid_id)
        if not video:
            continue
        cls = classifications.get(vid_id)
        vrow = video_row_map.get(vid_id)
        title_hl = vrow[1] if vrow else ""
        summary_hl = vrow[2] if vrow else ""
        transcript_snip = vrow[3] if vrow else ""
        kp_snip = vrow[4] if vrow else ""
        segment_hit = segment_hit_map.get(vid_id)

        # 選最佳片段展示
        snippet = (
            (segment_hit.get("segment_snippet") if segment_hit else "")
            or summary_hl
            or transcript_snip
            or kp_snip
            or ""
        )
        start_sec = segment_hit.get("start_sec") if segment_hit else None
        end_sec = segment_hit.get("end_sec") if segment_hit else None

        items.append(
            {
                "id": video.id,
                "filename": video.original_filename or video.filename,
                "status": video.status,
                "category": cls.category if cls else None,
                "labels": video_labels.get(vid_id, []),
                "last_reviewed_at": video.last_reviewed_at.isoformat()
                if video.last_reviewed_at
                else None,
                "review_count": video.review_count or 0,
                "sr_next_review_at": video.sr_next_review_at.isoformat()
                if video.sr_next_review_at
                else None,
                "snippet": snippet,
                "title_highlight": title_hl,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "timestamp": _format_mmss(start_sec),
            }
        )

    return {"query": q, "total": len(items), "items": items}


@router.post("/reindex")
def reindex_all(db: Session = Depends(get_db)):
    """重建所有已完成影片的 FTS 索引（維護用）"""
    videos = db.query(Video).filter(Video.status == "completed").all()
    count = 0
    for video in videos:
        try:
            rebuild_fts_index(video.id, db)  # type: ignore[arg-type]
            count += 1
        except Exception as e:
            logger.error(f"FTS reindex 失敗 {video.id}: {e}")
    return {"message": f"已重建 {count} 部影片的索引", "count": count}
