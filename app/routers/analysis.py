"""分析狀態與結果查詢 API"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import ChatMessage, Classification, Summary, TaskQueue, Transcript, Video, get_db
from app.services.analyzer import (
    analyze,
    ask_question,
    extract_case_analysis,
    generate_faq,
    generate_mindmap,
)
from app.services.analyzer import (
    suggest_labels as _suggest_labels,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AskRequest(BaseModel):
    question: str


@router.post("/{video_id}/queue")
def queue_video(video_id: str, priority: int = 5, db: Session = Depends(get_db)):
    """將單支影片加入分析佇列"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    existing = (
        db.query(TaskQueue)
        .filter(
            TaskQueue.video_id == video_id,
            TaskQueue.status.in_(["pending", "processing"]),
        )
        .first()
    )
    if existing:
        return {"message": "已在佇列中", "task_id": existing.id}

    task = TaskQueue(
        id=uuid.uuid4().hex,
        video_id=video_id,
        priority=max(1, min(10, priority)),
        status="pending",
    )
    db.add(task)
    video.status = "queued"  # type: ignore[assignment]
    db.commit()
    return {"message": "已加入佇列", "task_id": task.id}


@router.post("/{video_id}/retry")
def retry_video(video_id: str, db: Session = Depends(get_db)):
    """重試失敗的影片分析（重設重試次數）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    # 找到最新的失敗任務，重設它
    task = (
        db.query(TaskQueue)
        .filter(
            TaskQueue.video_id == video_id,
            TaskQueue.status == "failed",
        )
        .order_by(TaskQueue.created_at.desc())
        .first()
    )

    if task:
        task.status = "pending"  # type: ignore[assignment]
        task.retry_count = 0  # type: ignore[assignment]
        task.error_message = None  # type: ignore[assignment]
        task.started_at = None  # type: ignore[assignment]
        task.completed_at = None  # type: ignore[assignment]
    else:
        # 沒有失敗任務就建立新的
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=video_id,
            priority=5,
            status="pending",
        )
        db.add(task)

    video.status = "queued"  # type: ignore[assignment]
    video.error_message = None  # type: ignore[assignment]
    video.progress_step = 0  # type: ignore[assignment]
    video.progress_message = None  # type: ignore[assignment]
    video.progress_sub = 0  # type: ignore[assignment]
    db.commit()
    return {"message": "已重新加入佇列", "task_id": task.id}


@router.get("/{video_id}/status")
def get_status(video_id: str, db: Session = Depends(get_db)):
    """取得影片分析狀態與進度"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    # 優先取 done 任務；若沒有再取最新的（避免已完成影片顯示殘留 pending 任務）
    task = (
        db.query(TaskQueue)
        .filter(TaskQueue.video_id == video_id, TaskQueue.status == "done")
        .order_by(TaskQueue.created_at.desc())
        .first()
    ) or (
        db.query(TaskQueue)
        .filter(TaskQueue.video_id == video_id)
        .order_by(TaskQueue.created_at.desc())
        .first()
    )

    step_names = {
        0: "等待中",
        1: "提取音頻",
        2: "語音轉文字",
        3: "GPT 分析",
        4: "生成摘要功能",
    }
    step = video.progress_step or 0

    return {
        "video_id": video_id,
        "video_status": video.status,
        "progress": {
            "step": step,
            "total_steps": 4,
            "step_name": step_names.get(step, "等待中"),  # type: ignore[arg-type]
            "message": video.progress_message or "",
            "percent": int(step / 4 * 100),
            "sub_percent": video.progress_sub or 0,
        },
        "task": {
            "id": task.id,
            "status": task.status,
            "retry_count": task.retry_count,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }
        if task
        else None,
    }


@router.get("/{video_id}/results")
def get_results(video_id: str, db: Session = Depends(get_db)):
    """取得影片分析結果"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    if video.status != "completed":
        raise HTTPException(409, f"影片尚未分析完成，目前狀態: {video.status}")

    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    classification = db.query(Classification).filter(Classification.video_id == video_id).first()

    return {
        "video_id": video_id,
        "transcript": transcript.content if transcript else None,
        "summary": summary.summary if summary else None,
        "key_points": json.loads(summary.key_points) if summary and summary.key_points else [],  # type: ignore[arg-type]
        "category": classification.category if classification else None,
        "confidence": classification.confidence if classification else None,
        "case_analysis": summary.case_analysis if summary else None,
    }


@router.get("/{video_id}/mindmap")
def get_mindmap(video_id: str, db: Session = Depends(get_db)):
    """取得心智圖"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    if video.status != "completed":
        raise HTTPException(409, "分析尚未完成")
    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    if not summary or summary.mindmap is None:
        raise HTTPException(404, "尚未生成")
    return {"video_id": video_id, "mindmap": summary.mindmap}


@router.get("/{video_id}/faq")
def get_faq(video_id: str, db: Session = Depends(get_db)):
    """取得 FAQ"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    if video.status != "completed":
        raise HTTPException(409, "分析尚未完成")
    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    if not summary or summary.faq is None:
        raise HTTPException(404, "尚未生成")
    return {"video_id": video_id, "faq": json.loads(summary.faq)}  # type: ignore[arg-type]


@router.get("/{video_id}/study-notes")
def get_study_notes(video_id: str, db: Session = Depends(get_db)):
    """取得學習筆記"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    if video.status != "completed":
        raise HTTPException(409, "分析尚未完成")
    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    if not summary or summary.study_notes is None:
        raise HTTPException(404, "尚未生成")
    return {"video_id": video_id, "study_notes": summary.study_notes}


@router.post("/{video_id}/ask")
def ask_video_question(video_id: str, req: AskRequest, db: Session = Depends(get_db)):
    """對影片提問"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    if video.status != "completed":
        raise HTTPException(409, "分析尚未完成")
    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript:
        raise HTTPException(400, "逐字稿不存在")

    question = req.question.strip()
    if not question:
        raise HTTPException(400, "問題不能為空")

    # Load last 10 chat messages BEFORE saving new ones
    history_records = (
        db.query(ChatMessage)
        .filter(ChatMessage.video_id == video_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    chat_history = [{"role": m.role, "content": m.content} for m in history_records[-10:]]

    answer = ask_question(transcript.content, question, chat_history)  # type: ignore[arg-type]

    # Save user message
    db.add(
        ChatMessage(
            id=uuid.uuid4().hex,
            video_id=video_id,
            role="user",
            content=question,
        )
    )
    # Save assistant response
    db.add(
        ChatMessage(
            id=uuid.uuid4().hex,
            video_id=video_id,
            role="assistant",
            content=answer,
        )
    )
    db.commit()

    return {"answer": answer}


@router.get("/{video_id}/chat-history")
def get_chat_history(video_id: str, db: Session = Depends(get_db)):
    """取得對話歷史"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.video_id == video_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return {
        "video_id": video_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/{video_id}/chat-history")
def delete_chat_history(video_id: str, db: Session = Depends(get_db)):
    """清除對話歷史"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    db.query(ChatMessage).filter(ChatMessage.video_id == video_id).delete()
    db.commit()
    return {"message": "已清除"}


@router.post("/{video_id}/regenerate/{content_type}")
def regenerate_content(video_id: str, content_type: str, db: Session = Depends(get_db)):
    """重新生成內容"""
    valid_types = {"mindmap", "faq"}
    if content_type not in valid_types:
        raise HTTPException(400, f"無效的內容類型，支援: {', '.join(valid_types)}")

    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    if video.status != "completed":
        raise HTTPException(409, "分析尚未完成")

    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript:
        raise HTTPException(400, "逐字稿不存在")

    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    if not summary:
        raise HTTPException(404, "摘要記錄不存在")

    if content_type == "mindmap":
        result = generate_mindmap(transcript.content)  # type: ignore[arg-type]
        summary.mindmap = result  # type: ignore[assignment]
        db.commit()
        return {"video_id": video_id, "mindmap": result}
    elif content_type == "faq":
        result = generate_faq(transcript.content)  # type: ignore[arg-type,assignment]
        summary.faq = json.dumps(result, ensure_ascii=False)  # type: ignore[assignment]
        db.commit()
        return {"video_id": video_id, "faq": result}


@router.post("/{video_id}/reanalyze")
def reanalyze_video(video_id: str, db: Session = Depends(get_db)):
    """重新執行 GPT 分析（摘要+重點+分類），保留逐字稿不重跑 Whisper"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    if not transcript or not transcript.content:
        raise HTTPException(409, "逐字稿不存在，請先完成語音辨識")

    summary_text, key_points, category, confidence = analyze(transcript.content)  # type: ignore[arg-type]
    case_analysis_text = extract_case_analysis(transcript.content)  # type: ignore[arg-type]

    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    if summary:
        summary.summary = summary_text  # type: ignore[assignment]
        summary.key_points = json.dumps(key_points, ensure_ascii=False)  # type: ignore[assignment]
        summary.case_analysis = case_analysis_text or None  # type: ignore[assignment]
    else:
        db.add(
            Summary(
                id=uuid.uuid4().hex,
                video_id=video_id,
                summary=summary_text,
                key_points=json.dumps(key_points, ensure_ascii=False),
                case_analysis=case_analysis_text or None,
            )
        )

    existing_cls = db.query(Classification).filter(Classification.video_id == video_id).first()
    if existing_cls:
        existing_cls.category = category  # type: ignore[assignment]
        existing_cls.confidence = confidence  # type: ignore[assignment]
    else:
        db.add(
            Classification(
                id=uuid.uuid4().hex,
                video_id=video_id,
                category=category,
                confidence=confidence,
            )
        )

    video.status = "completed"  # type: ignore[assignment]
    db.commit()
    return {
        "message": "重新分析完成",
        "summary": summary_text,
        "key_points": key_points,
        "category": category,
        "confidence": confidence,
        "case_analysis": case_analysis_text or None,
    }


@router.post("/{video_id}/suggest-labels")
def suggest_labels(video_id: str, db: Session = Depends(get_db)):
    """用 GPT 根據摘要自動建議 3-5 個標籤"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    if not summary or not summary.summary:
        raise HTTPException(409, "尚無摘要，請先完成分析")

    labels = _suggest_labels(summary.summary)  # type: ignore[arg-type]
    return {"video_id": video_id, "suggestions": labels}


@router.get("/{video_id}/case-analysis")
def get_case_analysis(video_id: str, db: Session = Depends(get_db)):
    """取得案例分析（若影片無案例則回傳空字串）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")
    if video.status != "completed":
        raise HTTPException(409, "分析尚未完成")
    summary = db.query(Summary).filter(Summary.video_id == video_id).first()
    return {
        "video_id": video_id,
        "case_analysis": summary.case_analysis if summary else None,
    }
