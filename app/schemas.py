from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LabelOut(BaseModel):
    id: str
    name: str
    color: str
    video_count: int = 0

    model_config = {"from_attributes": True}


class VideoOut(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_path: str
    title: str | None
    duration: float | None
    file_size: int | None
    status: str
    upload_date: datetime | None
    source_type: str
    transcription_progress: int
    analysis_progress: int
    current_step: int
    step_message: str
    error_message: str | None
    has_transcript: bool
    has_summary: bool
    summary_preview: str | None
    category: str | None
    labels: list[LabelOut] = []
    # spaced repetition
    review_count: int
    last_reviewed_at: datetime | None
    sr_interval: int
    sr_ease_factor: float
    sr_next_review_at: datetime | None

    model_config = {"from_attributes": True}


class VideoListOut(BaseModel):
    total: int
    items: list[VideoOut]


class NoteOut(BaseModel):
    video_id: str
    content: str
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class StatsOverviewOut(BaseModel):
    total: int
    completed: int
    pending: int
    processing: int
    failed: int
    reviewed: int
    completion_rate: float
    review_rate: float
