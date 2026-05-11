"""Wiki 知識頁面合成器

對每個知識點（Concept），收集所有關聯影片片段的逐字稿，
呼叫 GPT 合成成一篇完整的知識說明，並儲存到 wiki_pages 表。
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import Concept, SegmentConcept, Transcript, Video, WikiPage, WikiPageSource
from app.utils import safe_json_loads

logger = logging.getLogger(__name__)

_MAX_EXCERPT_CHARS = 400
_MAX_SYNTHESIS_SEGMENTS = 30  # cap to avoid huge GPT context


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    import unicodedata

    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\s/\\()（）【】「」：:]+", "-", text)
    text = re.sub(r"[^\w\-\u4e00-\u9fff]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or uuid.uuid4().hex[:8]


def _unique_slug(base: str, existing: set[str]) -> str:
    slug = base
    counter = 2
    while slug in existing:
        slug = f"{base}-{counter}"
        counter += 1
    existing.add(slug)
    return slug


def synthesize_wiki_page(concept_id: str, db: Session) -> WikiPage | None:
    """為單一概念合成 wiki 知識頁面。

    1. 查詢所有含此概念的影片片段
    2. 收集片段逐字稿文字
    3. 呼叫 GPT 合成完整知識說明（Markdown）
    4. 儲存/更新 wiki_pages + wiki_page_sources

    Returns:
        The WikiPage ORM object, or None if concept/transcript not found.
    """
    from app.services.analyzer import _chat

    concept = db.query(Concept).filter(Concept.id == concept_id).first()
    if not concept:
        return None

    # ── 收集所有片段 ──────────────────────────────────────────────────────────
    seg_links = (
        db.query(SegmentConcept)
        .filter(SegmentConcept.concept_id == concept_id)
        .order_by(SegmentConcept.start_sec.asc())
        .limit(_MAX_SYNTHESIS_SEGMENTS)
        .all()
    )

    # Load transcripts indexed by video_id
    video_ids = list({sl.video_id for sl in seg_links})
    transcripts_map: dict[str, dict] = {}
    for tr in db.query(Transcript).filter(Transcript.video_id.in_(video_ids)).all():
        segs_json: list[dict] = safe_json_loads(tr.segments or "[]", [])
        transcripts_map[str(tr.video_id)] = {
            "content": tr.content or "",
            "segments": segs_json,
        }

    videos_map = {str(v.id): v for v in db.query(Video).filter(Video.id.in_(video_ids)).all()}

    # ── 組合輸入給 GPT 的片段文字 ─────────────────────────────────────────────
    source_blocks: list[str] = []
    source_meta: list[dict] = []  # for wiki_page_sources

    for sl in seg_links:
        vid_id = str(sl.video_id)
        tr_data = transcripts_map.get(vid_id)
        if not tr_data:
            continue

        seg_text = ""
        segs: list[dict] = tr_data["segments"]
        idx = sl.seg_idx
        if segs and 0 <= idx < len(segs):
            # Include surrounding context (±1 segment)
            context_segs = segs[max(0, idx - 1) : min(len(segs), idx + 2)]
            seg_text = " ".join(str(s.get("text", "")).strip() for s in context_segs)
        if not seg_text:
            # Fallback: use raw transcript excerpt at approximate character offset
            avg_seg_len = max(1, len(tr_data["content"]) // max(1, len(segs)))
            start_char = idx * avg_seg_len
            seg_text = tr_data["content"][start_char : start_char + _MAX_EXCERPT_CHARS]

        vid = videos_map.get(vid_id)
        vid_title = str(vid.original_filename or vid.filename) if vid else vid_id
        block_text = seg_text[:_MAX_EXCERPT_CHARS]

        source_blocks.append(f"【影片：{vid_title}】\n{block_text}")
        source_meta.append(
            {
                "video_id": vid_id,
                "start_time": float(sl.start_sec or 0),
                "end_time": float(sl.end_sec or 0),
                "excerpt": block_text,
            }
        )

    # If no segments found, try using the full transcripts where this concept was mentioned
    if not source_blocks and concept.description:
        source_blocks.append(f"【概念說明】\n{concept.description}")

    if not source_blocks:
        logger.info("synthesize_wiki_page: 概念 %s 無素材，跳過", concept.name)
        return None

    combined_sources = "\n\n---\n\n".join(source_blocks[:20])  # cap total input

    # ── GPT 合成 ──────────────────────────────────────────────────────────────
    system_prompt = """你是一位知識管理專家，擅長整合多個影片片段的知識，撰寫結構清晰的知識詞條。
請以繁體中文、Markdown 格式撰寫。"""

    user_content = f"""請根據以下影片片段，為「{concept.name}」撰寫一篇完整的知識說明。

原始影片片段：
{combined_sources}

請以 Markdown 格式撰寫，包含以下結構：
## 定義
（簡短定義，2-4句）

## 核心原理
（詳細說明，可用子標題或列表）

## 應用情境
（實際應用場景，條列式）

## 注意事項
（學習或應用時需注意的重點）

## 相關概念
（與其他概念的關聯，用簡短說明，不要用列表連結）

要求：
- 融會貫通多個片段的知識，不要只是重複片段內容
- 清晰易懂，適合初學者到進階者閱讀
- 繁體中文，術語保持一致
- 不要在內容中提到「影片」或「片段」等來源資訊"""

    raw_content = _chat(system_prompt, user_content, max_tokens=2000)

    # ── 儲存到 DB ─────────────────────────────────────────────────────────────
    now = datetime.utcnow()
    existing_slugs: set[str] = {str(p.slug) for p in db.query(WikiPage).all()}

    # Check if wiki page already exists for this concept
    wiki_page = db.query(WikiPage).filter(WikiPage.concept_id == concept_id).first()
    if wiki_page:
        wiki_page.title = concept.name  # type: ignore[assignment]
        wiki_page.synthesized_content = raw_content  # type: ignore[assignment]
        wiki_page.source_video_count = len(video_ids)  # type: ignore[assignment]
        wiki_page.last_synthesized_at = now  # type: ignore[assignment]
        wiki_page.status = "published"  # type: ignore[assignment]
        wiki_page.updated_at = now  # type: ignore[assignment]
        # Clear old sources
        db.query(WikiPageSource).filter(WikiPageSource.wiki_page_id == wiki_page.id).delete(
            synchronize_session=False
        )
    else:
        existing_slugs.discard("")  # remove empty slug if present
        slug = _unique_slug(_slugify(concept.name), existing_slugs)
        wiki_page = WikiPage(
            id=uuid.uuid4().hex,
            concept_id=concept_id,
            title=concept.name,
            slug=slug,
            synthesized_content=raw_content,
            source_video_count=len(video_ids),
            last_synthesized_at=now,
            status="published",
            created_at=now,
            updated_at=now,
        )
        db.add(wiki_page)

    db.flush()

    # Add source records
    for meta in source_meta:
        db.add(
            WikiPageSource(
                id=uuid.uuid4().hex,
                wiki_page_id=wiki_page.id,
                video_id=meta["video_id"],
                start_time=meta["start_time"],
                end_time=meta["end_time"],
                excerpt=meta["excerpt"],
                created_at=now,
            )
        )

    db.commit()
    logger.info(
        "synthesize_wiki_page: 概念 '%s' 完成，%d 個來源片段",
        concept.name,
        len(source_meta),
    )
    return wiki_page


def synthesize_all_wiki_pages(db: Session, force: bool = False) -> dict:
    """為所有概念合成 wiki 知識頁面。

    Args:
        force: 若 True 則強制重新合成所有頁面（包含已 published 的）。
    Returns:
        dict with keys: synthesized, skipped, errors
    """
    synthesized = 0
    skipped = 0
    errors = 0

    concepts = db.query(Concept).order_by(Concept.video_count.desc()).all()
    for concept in concepts:
        # Skip if already published and not forced
        if not force:
            existing = (
                db.query(WikiPage)
                .filter(
                    WikiPage.concept_id == concept.id,
                    WikiPage.status == "published",
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

        try:
            result = synthesize_wiki_page(str(concept.id), db)
            if result:
                synthesized += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error("synthesize_all_wiki_pages 失敗 concept=%s: %s", concept.name, e)
            errors += 1

    logger.info(
        "synthesize_all_wiki_pages 完成 — 合成 %d, 跳過 %d, 錯誤 %d",
        synthesized,
        skipped,
        errors,
    )
    return {"synthesized": synthesized, "skipped": skipped, "errors": errors}


def mark_concept_wiki_stale(concept_id: str, db: Session) -> None:
    """標記某概念的 wiki 頁面為 stale（供 worker 呼叫）。"""
    db.query(WikiPage).filter(
        WikiPage.concept_id == concept_id,
        WikiPage.status == "published",
    ).update({"status": "stale"}, synchronize_session=False)
    db.flush()


def _format_mmss(sec: float | None) -> str | None:
    if sec is None:
        return None
    try:
        total = max(0, int(float(sec)))
    except (TypeError, ValueError):
        return None
    mins = total // 60
    secs = total % 60
    return f"{mins:02d}:{secs:02d}"
