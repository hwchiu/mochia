"""分析狀態與結果查詢 API"""
import json
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, Video, TaskQueue, Transcript, Summary, Classification, ChatMessage
from app.services.analyzer import generate_mindmap, generate_faq, generate_study_notes, ask_question

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

    existing = db.query(TaskQueue).filter(
        TaskQueue.video_id == video_id,
        TaskQueue.status.in_(["pending", "processing"]),
    ).first()
    if existing:
        return {"message": "已在佇列中", "task_id": existing.id}

    task = TaskQueue(
        id=uuid.uuid4().hex,
        video_id=video_id,
        priority=max(1, min(10, priority)),
        status="pending",
    )
    db.add(task)
    video.status = "queued"
    db.commit()
    return {"message": "已加入佇列", "task_id": task.id}


@router.post("/{video_id}/retry")
def retry_video(video_id: str, db: Session = Depends(get_db)):
    """重試失敗的影片分析（重設重試次數）"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    # 找到最新的失敗任務，重設它
    task = db.query(TaskQueue).filter(
        TaskQueue.video_id == video_id,
        TaskQueue.status == "failed",
    ).order_by(TaskQueue.created_at.desc()).first()

    if task:
        task.status = "pending"
        task.retry_count = 0
        task.error_message = None
        task.started_at = None
        task.completed_at = None
    else:
        # 沒有失敗任務就建立新的
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=video_id,
            priority=5,
            status="pending",
        )
        db.add(task)

    video.status = "queued"
    video.error_message = None
    video.progress_step = 0
    video.progress_message = None
    video.progress_sub = 0
    db.commit()
    return {"message": "已重新加入佇列", "task_id": task.id}


@router.get("/{video_id}/status")
def get_status(video_id: str, db: Session = Depends(get_db)):
    """取得影片分析狀態與進度"""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "影片不存在")

    task = db.query(TaskQueue).filter(TaskQueue.video_id == video_id).order_by(
        TaskQueue.created_at.desc()
    ).first()

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
            "step_name": step_names.get(step, "等待中"),
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
        } if task else None,
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

    import json
    return {
        "video_id": video_id,
        "transcript": transcript.content if transcript else None,
        "summary": summary.summary if summary else None,
        "key_points": json.loads(summary.key_points) if summary and summary.key_points else [],
        "category": classification.category if classification else None,
        "confidence": classification.confidence if classification else None,
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
    return {"video_id": video_id, "faq": json.loads(summary.faq)}


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

    answer = ask_question(transcript.content, question, chat_history)

    # Save user message
    db.add(ChatMessage(
        id=uuid.uuid4().hex,
        video_id=video_id,
        role="user",
        content=question,
    ))
    # Save assistant response
    db.add(ChatMessage(
        id=uuid.uuid4().hex,
        video_id=video_id,
        role="assistant",
        content=answer,
    ))
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
    valid_types = {"mindmap", "faq", "study_notes"}
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
        result = generate_mindmap(transcript.content)
        summary.mindmap = result
        db.commit()
        return {"video_id": video_id, "mindmap": result}
    elif content_type == "faq":
        result = generate_faq(transcript.content)
        summary.faq = json.dumps(result, ensure_ascii=False)
        db.commit()
        return {"video_id": video_id, "faq": result}
    elif content_type == "study_notes":
        result = generate_study_notes(transcript.content)
        summary.study_notes = result
        db.commit()
        return {"video_id": video_id, "study_notes": result}
