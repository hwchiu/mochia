"""M3 題庫系統 API — 題目生成、答題記錄、錯題本"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import Quiz, QuizAttempt, QuizItem, Transcript, Video, get_db
from app.services.analyzer import generate_quizzes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/quiz", tags=["quiz"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────


class AttemptRequest(BaseModel):
    quiz_item_id: str
    user_answer: str


class AttemptResponse(BaseModel):
    id: str
    quiz_item_id: str
    is_correct: bool
    correct_answer: str
    explanation: str


class QuizItemOut(BaseModel):
    id: str
    question_type: str
    question: str
    options: list[str] | None
    answer: str
    explanation: str | None
    concept_name: str | None
    source_seg_idx: int | None
    source_start_sec: float | None
    source_end_sec: float | None


class QuizOut(BaseModel):
    video_id: str
    total_items: int
    items: list[QuizItemOut]


# ── Background task ──────────────────────────────────────────────────────────


def _rebuild_quiz_bg(video_id: str) -> None:
    """Run quiz generation in a background thread (used by BackgroundTasks)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rebuild_quiz_for_video(video_id, db)
    except Exception:
        logger.exception("[quiz] 背景生成題目失敗 video_id=%s", video_id)
    finally:
        db.close()


# ── Core generation logic ────────────────────────────────────────────────────


def rebuild_quiz_for_video(video_id: str, db: Session) -> None:
    """Generate (or regenerate) quiz questions for a video.

    Fetches the transcript and existing concepts from the database, calls
    generate_quizzes(), then writes Quiz + QuizItem rows, replacing any
    previous quiz for this video.
    """
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise ValueError(f"影片不存在: {video_id}")

    transcript_row = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript_row or not transcript_row.content:
        logger.info("[quiz] 影片 %s 尚無逐字稿，跳過題目生成", video_id)
        return

    # Load segments
    segments: list[dict] = []
    if transcript_row.segments:
        try:
            segments = json.loads(transcript_row.segments)
        except Exception:
            pass

    # Load existing concepts for richer context
    from app.database import Concept, SegmentConcept

    concept_rows = (
        db.query(Concept)
        .join(SegmentConcept, SegmentConcept.concept_id == Concept.id)
        .filter(SegmentConcept.video_id == video_id)
        .distinct()
        .all()
    )
    concepts = [{"name": c.name, "description": c.description or ""} for c in concept_rows]

    quiz_data = generate_quizzes(transcript_row.content, segments=segments, concepts=concepts)
    if not quiz_data:
        logger.warning("[quiz] generate_quizzes 返回空結果 video_id=%s", video_id)
        return

    # Delete existing quiz
    existing = db.query(Quiz).filter(Quiz.video_id == video_id).first()
    if existing:
        db.delete(existing)
        db.flush()

    quiz_id = str(uuid.uuid4())
    now = datetime.utcnow()
    quiz = Quiz(
        id=quiz_id,
        video_id=video_id,
        total_items=len(quiz_data),
        created_at=now,
        updated_at=now,
    )
    db.add(quiz)
    db.flush()

    for q in quiz_data:
        item = QuizItem(
            id=str(uuid.uuid4()),
            quiz_id=quiz_id,
            video_id=video_id,
            question_type=q["question_type"],
            question=q["question"],
            options=json.dumps(q["options"], ensure_ascii=False) if q["options"] else None,
            answer=q["answer"],
            explanation=q.get("explanation") or "",
            concept_name=q.get("concept_name"),
            source_seg_idx=q.get("source_seg_idx"),
            source_start_sec=q.get("source_start_sec"),
            source_end_sec=q.get("source_end_sec"),
            created_at=now,
        )
        db.add(item)

    db.commit()
    logger.info("[quiz] 題庫建立完成 video_id=%s total=%d", video_id, len(quiz_data))


# ── API endpoints ────────────────────────────────────────────────────────────


@router.get("/{video_id}", response_model=QuizOut)
def get_quiz(video_id: str, db: Session = Depends(get_db)):
    """Get all quiz items for a video."""
    quiz = db.query(Quiz).filter(Quiz.video_id == video_id).first()
    if not quiz:
        return QuizOut(video_id=video_id, total_items=0, items=[])

    items = db.query(QuizItem).filter(QuizItem.quiz_id == quiz.id).all()
    return QuizOut(
        video_id=video_id,
        total_items=quiz.total_items or 0,
        items=[
            QuizItemOut(
                id=item.id or "",
                question_type=item.question_type or "mcq",
                question=item.question or "",
                options=json.loads(item.options) if item.options else None,
                answer=item.answer or "",
                explanation=item.explanation,
                concept_name=item.concept_name,
                source_seg_idx=item.source_seg_idx,
                source_start_sec=float(item.source_start_sec)
                if item.source_start_sec is not None
                else None,
                source_end_sec=float(item.source_end_sec)
                if item.source_end_sec is not None
                else None,
            )
            for item in items
        ],
    )


@router.post("/{video_id}/generate")
def generate_quiz(
    video_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger quiz generation for a video (runs in background)."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="影片不存在")

    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript or not transcript.content:
        raise HTTPException(status_code=400, detail="影片尚無逐字稿，請先完成分析")

    background_tasks.add_task(_rebuild_quiz_bg, video_id)
    return {"status": "generating", "video_id": video_id, "message": "題目生成中，請稍後重新整理"}


@router.post("/attempt", response_model=AttemptResponse)
def submit_attempt(req: AttemptRequest, db: Session = Depends(get_db)):
    """Submit an answer attempt and get feedback."""
    item = db.query(QuizItem).filter(QuizItem.id == req.quiz_item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="題目不存在")

    # Normalize comparison: strip, lowercase
    correct = (item.answer or "").strip()
    user = req.user_answer.strip()

    # For MCQ, compare first char (A/B/C/D) or full text
    is_correct = user.upper() == correct.upper() or user == correct
    # Also accept if user sends just the leading letter for MCQ
    if not is_correct and item.question_type == "mcq":
        is_correct = user.upper()[:1] == correct.upper()[:1]

    attempt = QuizAttempt(
        id=str(uuid.uuid4()),
        quiz_item_id=item.id,
        video_id=item.video_id,
        user_answer=user,
        is_correct=int(is_correct),
        attempted_at=datetime.utcnow(),
    )
    db.add(attempt)
    db.commit()

    return AttemptResponse(
        id=attempt.id or "",
        quiz_item_id=item.id or "",
        is_correct=is_correct,
        correct_answer=item.answer or "",
        explanation=item.explanation or "",
    )


@router.get("/wrong-answers/list")
def get_wrong_answers(limit: int = 50, db: Session = Depends(get_db)):
    """Get wrong answer records with question context."""
    wrong = (
        db.query(QuizAttempt)
        .filter(QuizAttempt.is_correct == 0)
        .order_by(QuizAttempt.attempted_at.desc())
        .limit(limit)
        .all()
    )

    item_ids = list({a.quiz_item_id for a in wrong})
    items_map = {i.id: i for i in db.query(QuizItem).filter(QuizItem.id.in_(item_ids)).all()}

    result = []
    for attempt in wrong:
        item = items_map.get(attempt.quiz_item_id)
        if not item:
            continue
        result.append(
            {
                "attempt_id": attempt.id,
                "quiz_item_id": item.id,
                "video_id": item.video_id,
                "question_type": item.question_type,
                "question": item.question,
                "options": json.loads(item.options) if item.options else None,
                "correct_answer": item.answer,
                "user_answer": attempt.user_answer,
                "explanation": item.explanation,
                "concept_name": item.concept_name,
                "source_start_sec": item.source_start_sec,
                "source_end_sec": item.source_end_sec,
                "attempted_at": attempt.attempted_at.isoformat() if attempt.attempted_at else "",
            }
        )
    return {"total": len(result), "items": result}


@router.get("/stats/overview")
def get_quiz_stats(db: Session = Depends(get_db)):
    """Get overall quiz statistics."""
    total_items = db.query(QuizItem).count()
    total_attempts = db.query(QuizAttempt).count()
    correct_attempts = db.query(QuizAttempt).filter(QuizAttempt.is_correct == 1).count()
    wrong_attempts = total_attempts - correct_attempts
    accuracy = round(correct_attempts / total_attempts * 100, 1) if total_attempts else 0.0

    return {
        "total_items": total_items,
        "total_attempts": total_attempts,
        "correct_attempts": correct_attempts,
        "wrong_attempts": wrong_attempts,
        "accuracy_percent": accuracy,
    }
