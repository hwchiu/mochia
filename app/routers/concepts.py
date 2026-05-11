"""知識圖譜 API — 概念節點、關係、片段連結"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import (
    Concept,
    ConceptRelation,
    SegmentConcept,
    Transcript,
    Video,
    get_db,
)
from app.utils import safe_json_loads

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/concepts", tags=["concepts"])


def _format_mmss(sec: float | int | None) -> str | None:
    if sec is None:
        return None
    try:
        total = max(0, int(float(sec)))
    except (TypeError, ValueError):
        return None
    mins = total // 60
    secs = total % 60
    return f"{mins:02d}:{secs:02d}"


def rebuild_concepts_for_video(video_id: str, db: Session) -> int:
    """抽取並儲存單支影片的知識點。

    若概念已存在（按名稱去重），則複用；否則建立新概念。
    回傳此次寫入的概念數量。

    此函式是 idempotent：可重複呼叫，舊的 segment_concepts 記錄會先清除再重建。
    """
    from app.services.analyzer import extract_concepts

    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        return 0

    transcript_row = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript_row or not transcript_row.content:
        logger.info("rebuild_concepts: 影片 %s 無逐字稿，跳過", video_id)
        return 0

    segments: list[dict] = safe_json_loads(transcript_row.segments or "[]", [])

    concepts_data = extract_concepts(transcript_row.content, segments or None)
    if not concepts_data:
        return 0

    # ── 清除舊的 segment_concept 記錄（重算時確保冪等）─────────────────────
    db.query(SegmentConcept).filter(SegmentConcept.video_id == video_id).delete(
        synchronize_session=False
    )
    db.flush()

    # ── 建立或取得概念；建立關係；建立 segment 連結 ──────────────────────────
    now = datetime.utcnow()
    concept_name_to_id: dict[str, str] = {}

    for item in concepts_data:
        name = item["name"]
        existing = db.query(Concept).filter(Concept.name == name).first()
        if existing:
            concept_id = str(existing.id)
            existing.updated_at = now  # type: ignore[assignment]
        else:
            concept_id = uuid.uuid4().hex
            db.add(
                Concept(
                    id=concept_id,
                    name=name,
                    description=item.get("description") or None,
                    video_count=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        concept_name_to_id[name] = concept_id

    db.flush()  # ensure all concepts are persisted before linking

    # ── video_count: 重算有 SegmentConcept 連結的影片數（稍後更新）───────────
    affected_concept_ids: set[str] = set(concept_name_to_id.values())

    for item in concepts_data:
        concept_id = concept_name_to_id[item["name"]]

        # Segment links
        for seg in item.get("segments", []):
            sc_id = uuid.uuid4().hex
            db.add(
                SegmentConcept(
                    id=sc_id,
                    video_id=video_id,
                    concept_id=concept_id,
                    seg_idx=seg["seg_idx"],
                    start_sec=seg["start_sec"],
                    end_sec=seg["end_sec"],
                    created_at=now,
                )
            )

        # Relations (only between concepts extracted this round)
        for rel in item.get("relations", []):
            target_name = rel.get("name", "")
            target_id = concept_name_to_id.get(target_name)
            if not target_id or target_id == concept_id:
                continue
            relation_type = rel.get("relation_type", "related")
            # Upsert: ignore duplicate
            existing_rel = (
                db.query(ConceptRelation)
                .filter(
                    ConceptRelation.source_concept_id == concept_id,
                    ConceptRelation.target_concept_id == target_id,
                    ConceptRelation.relation_type == relation_type,
                )
                .first()
            )
            if not existing_rel:
                db.add(
                    ConceptRelation(
                        id=uuid.uuid4().hex,
                        source_concept_id=concept_id,
                        target_concept_id=target_id,
                        relation_type=relation_type,
                        created_at=now,
                    )
                )

    db.flush()

    # ── 更新每個概念的 video_count ────────────────────────────────────────────
    for concept_id in affected_concept_ids:
        count = (
            db.query(SegmentConcept.video_id)
            .filter(SegmentConcept.concept_id == concept_id)
            .distinct()
            .count()
        )
        db.query(Concept).filter(Concept.id == concept_id).update({"video_count": count})

    db.commit()
    logger.info("rebuild_concepts: 影片 %s 完成，%d 個概念", video_id, len(concepts_data))
    return len(concepts_data)


# ─── API Endpoints ────────────────────────────────────────────────────────────


@router.get("/")
def list_concepts(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """列出所有知識點，依影片數降序排列"""
    total = db.query(Concept).count()
    concepts = (
        db.query(Concept)
        .order_by(Concept.video_count.desc(), Concept.name.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "video_count": c.video_count or 0,
            }
            for c in concepts
        ],
    }


@router.get("/{concept_id}")
def get_concept(concept_id: str, db: Session = Depends(get_db)):
    """取得單一知識點的詳情、關聯知識點與影片片段"""
    concept = db.query(Concept).filter(Concept.id == concept_id).first()
    if not concept:
        raise HTTPException(404, "知識點不存在")

    # Relations
    relations_from = (
        db.query(ConceptRelation)
        .filter(ConceptRelation.source_concept_id == concept_id)
        .all()
    )
    relations_to = (
        db.query(ConceptRelation)
        .filter(ConceptRelation.target_concept_id == concept_id)
        .all()
    )

    target_ids = [r.target_concept_id for r in relations_from]
    source_ids = [r.source_concept_id for r in relations_to]
    all_rel_ids = list(set(target_ids + source_ids))
    related_concepts = {
        c.id: c
        for c in db.query(Concept).filter(Concept.id.in_(all_rel_ids)).all()
    }

    relations_out = []
    for r in relations_from:
        rc = related_concepts.get(r.target_concept_id)
        if rc:
            relations_out.append(
                {
                    "id": str(rc.id),
                    "name": rc.name,
                    "relation_type": r.relation_type,
                    "direction": "outgoing",
                }
            )
    for r in relations_to:
        rc = related_concepts.get(r.source_concept_id)
        if rc:
            relations_out.append(
                {
                    "id": str(rc.id),
                    "name": rc.name,
                    "relation_type": r.relation_type,
                    "direction": "incoming",
                }
            )

    # Segment links with video info
    seg_links = (
        db.query(SegmentConcept)
        .filter(SegmentConcept.concept_id == concept_id)
        .order_by(SegmentConcept.start_sec.asc())
        .all()
    )
    video_ids = list({sl.video_id for sl in seg_links})
    videos_map = {v.id: v for v in db.query(Video).filter(Video.id.in_(video_ids)).all()}

    segments_out = []
    for sl in seg_links:
        vid = videos_map.get(sl.video_id)
        if not vid:
            continue
        segments_out.append(
            {
                "video_id": sl.video_id,
                "video_filename": vid.original_filename or vid.filename,
                "seg_idx": sl.seg_idx,
                "start_sec": sl.start_sec,
                "end_sec": sl.end_sec,
                "timestamp": _format_mmss(sl.start_sec),
            }
        )

    return {
        "id": concept.id,
        "name": concept.name,
        "description": concept.description,
        "video_count": concept.video_count or 0,
        "relations": relations_out,
        "segments": segments_out,
    }


@router.post("/rebuild/{video_id}")
def rebuild_concepts_api(video_id: str, db: Session = Depends(get_db)):
    """（維護用）重新抽取並儲存單支影片的知識點"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    count = rebuild_concepts_for_video(video_id, db)
    return {"message": f"已重建 {count} 個知識點", "count": count, "video_id": video_id}


@router.post("/rebuild-all")
def rebuild_all_concepts(db: Session = Depends(get_db)):
    """（維護用）重建所有已完成影片的知識點索引"""
    videos = db.query(Video).filter(Video.status == "completed").all()
    total_concepts = 0
    processed = 0
    errors = 0
    for video in videos:
        try:
            count = rebuild_concepts_for_video(str(video.id), db)
            total_concepts += count
            processed += 1
        except Exception as e:
            logger.error("rebuild_all_concepts 失敗 video_id=%s: %s", video.id, e)
            errors += 1
    return {
        "message": f"已處理 {processed} 部影片，共 {total_concepts} 個知識點，失敗 {errors} 部",
        "processed": processed,
        "total_concepts": total_concepts,
        "errors": errors,
    }


@router.get("/by-video/{video_id}")
def get_concepts_by_video(video_id: str, db: Session = Depends(get_db)):
    """取得單支影片的所有知識點（含片段連結）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    seg_links = (
        db.query(SegmentConcept)
        .filter(SegmentConcept.video_id == video_id)
        .order_by(SegmentConcept.start_sec.asc())
        .all()
    )

    concept_ids = list({sl.concept_id for sl in seg_links})
    concepts_map = {c.id: c for c in db.query(Concept).filter(Concept.id.in_(concept_ids)).all()}

    # Group segment links by concept
    by_concept: dict[str, list[dict]] = {}
    for sl in seg_links:
        by_concept.setdefault(sl.concept_id, []).append(
            {
                "seg_idx": sl.seg_idx,
                "start_sec": sl.start_sec,
                "end_sec": sl.end_sec,
                "timestamp": _format_mmss(sl.start_sec),
            }
        )

    items = []
    for concept_id, segs in by_concept.items():
        c = concepts_map.get(concept_id)
        if not c:
            continue
        items.append(
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "segments": sorted(segs, key=lambda s: s["start_sec"]),
            }
        )

    # Sort by first segment time
    items.sort(key=lambda x: x["segments"][0]["start_sec"] if x["segments"] else 0)

    return {
        "video_id": video_id,
        "total": len(items),
        "items": items,
    }
