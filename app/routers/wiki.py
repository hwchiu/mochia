"""Wiki 知識庫路由 — API 端點 + HTML 頁面"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import (
    Concept,
    ConceptRelation,
    ConceptTopic,
    SegmentConcept,
    Topic,
    Video,
    WikiPage,
    WikiPageSource,
    get_db,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["wiki"])

_templates_dir = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


# ─── Helper ──────────────────────────────────────────────────────────────────


def _format_mmss(sec: float | None) -> str | None:
    if sec is None:
        return None
    try:
        total = max(0, int(float(sec)))
    except (TypeError, ValueError):
        return None
    return f"{total // 60:02d}:{total % 60:02d}"


def _topic_tree(db: Session, parent_id: str | None = None) -> list[dict]:
    """Recursively build topic tree from DB."""
    topics = (
        db.query(Topic)
        .filter(Topic.parent_id == parent_id)
        .order_by(Topic.learning_order.asc(), Topic.name.asc())
        .all()
    )
    result = []
    for t in topics:
        concept_count = db.query(ConceptTopic).filter(ConceptTopic.topic_id == t.id).count()
        result.append(
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "domain": t.domain,
                "description": t.description,
                "learning_order": t.learning_order,
                "concept_count": concept_count,
                "children": _topic_tree(db, t.id),
            }
        )
    return result


# ─── HTML Pages ──────────────────────────────────────────────────────────────


@router.get("/wiki", response_class=HTMLResponse, include_in_schema=False)
async def wiki_index(request: Request, db: Session = Depends(get_db)):
    """知識庫首頁"""
    domains = (
        db.query(Topic)
        .filter(Topic.parent_id.is_(None))
        .order_by(Topic.learning_order.asc(), Topic.name.asc())
        .all()
    )
    domain_data = []
    for d in domains:
        concept_count = (
            db.query(ConceptTopic)
            .join(Topic, ConceptTopic.topic_id == Topic.id)
            .filter(Topic.domain == d.name)
            .count()
        )
        wiki_count = (
            db.query(WikiPage)
            .join(Concept, WikiPage.concept_id == Concept.id)
            .join(ConceptTopic, ConceptTopic.concept_id == Concept.id)
            .join(Topic, ConceptTopic.topic_id == Topic.id)
            .filter(Topic.domain == d.name, WikiPage.status == "published")
            .count()
        )
        domain_data.append(
            {
                "id": d.id,
                "name": d.name,
                "slug": d.slug,
                "description": d.description,
                "concept_count": concept_count,
                "wiki_count": wiki_count,
                "children": _topic_tree(db, d.id),
            }
        )

    # Recent wiki pages
    recent_pages = (
        db.query(WikiPage)
        .filter(WikiPage.status == "published")
        .order_by(WikiPage.last_synthesized_at.desc())
        .limit(8)
        .all()
    )
    recent_data = [
        {
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "source_video_count": p.source_video_count,
        }
        for p in recent_pages
    ]

    total_concepts = db.query(Concept).count()
    total_wiki = db.query(WikiPage).filter(WikiPage.status == "published").count()
    total_topics = db.query(Topic).count()

    return templates.TemplateResponse(
        request,
        "wiki_index.html",
        {
            "domains": domain_data,
            "recent_pages": recent_data,
            "total_concepts": total_concepts,
            "total_wiki": total_wiki,
            "total_topics": total_topics,
        },
    )


@router.get("/wiki/concept/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def wiki_concept_page(request: Request, slug: str, db: Session = Depends(get_db)):
    """概念知識詳情頁"""
    wiki_page = db.query(WikiPage).filter(WikiPage.slug == slug).first()
    if not wiki_page:
        raise HTTPException(404, "知識頁不存在")

    concept = db.query(Concept).filter(Concept.id == wiki_page.concept_id).first()

    # Breadcrumb: topic hierarchy
    breadcrumb: list[dict] = []
    if concept:
        ct = db.query(ConceptTopic).filter(ConceptTopic.concept_id == concept.id).first()
        if ct:
            topic = db.query(Topic).filter(Topic.id == ct.topic_id).first()
            if topic:
                # Build ancestry chain
                chain: list[Topic] = []
                t: Topic | None = topic
                while t:
                    chain.insert(0, t)
                    t = db.query(Topic).filter(Topic.id == t.parent_id).first() if t.parent_id else None
                breadcrumb = [{"name": t.name, "slug": t.slug} for t in chain]

    # Relations
    prerequisites: list[dict] = []
    related: list[dict] = []
    if concept:
        relations_from = (
            db.query(ConceptRelation)
            .filter(ConceptRelation.source_concept_id == concept.id)
            .all()
        )
        relations_to = (
            db.query(ConceptRelation)
            .filter(ConceptRelation.target_concept_id == concept.id)
            .all()
        )
        all_rel_ids = list(
            {r.target_concept_id for r in relations_from}
            | {r.source_concept_id for r in relations_to}
        )
        rel_concepts = {
            c.id: c for c in db.query(Concept).filter(Concept.id.in_(all_rel_ids)).all()
        }
        # Get wiki slugs for related concepts
        rel_wiki_pages = {
            wp.concept_id: wp
            for wp in db.query(WikiPage)
            .filter(WikiPage.concept_id.in_(all_rel_ids), WikiPage.status == "published")
            .all()
        }
        for r in relations_from:
            rc = rel_concepts.get(r.target_concept_id)
            if not rc:
                continue
            entry = {
                "name": rc.name,
                "slug": rel_wiki_pages[rc.id].slug if rc.id in rel_wiki_pages else None,
                "relation_type": r.relation_type,
            }
            if r.relation_type == "prerequisite":
                prerequisites.append(entry)
            else:
                related.append(entry)
        for r in relations_to:
            rc = rel_concepts.get(r.source_concept_id)
            if not rc:
                continue
            entry = {
                "name": rc.name,
                "slug": rel_wiki_pages[rc.id].slug if rc.id in rel_wiki_pages else None,
                "relation_type": r.relation_type,
            }
            if r.relation_type not in [e["name"] for e in related]:
                related.append(entry)

    # Source videos
    sources = (
        db.query(WikiPageSource)
        .filter(WikiPageSource.wiki_page_id == wiki_page.id)
        .all()
    )
    video_ids = list({s.video_id for s in sources})
    videos_map = {v.id: v for v in db.query(Video).filter(Video.id.in_(video_ids)).all()}

    # Group sources by video with all timestamps
    seg_links_by_video: dict[str, dict] = {}
    if concept:
        all_seg_links = (
            db.query(SegmentConcept)
            .filter(SegmentConcept.concept_id == concept.id)
            .order_by(SegmentConcept.start_sec.asc())
            .all()
        )
        for sl in all_seg_links:
            vid = videos_map.get(sl.video_id)
            if not vid:
                continue
            vid_id = str(sl.video_id)
            if vid_id not in seg_links_by_video:
                seg_links_by_video[vid_id] = {
                    "video_id": vid_id,
                    "title": str(vid.original_filename or vid.filename),
                    "timestamps": [],
                }
            seg_links_by_video[vid_id]["timestamps"].append(
                {
                    "start_sec": sl.start_sec,
                    "end_sec": sl.end_sec,
                    "display": _format_mmss(sl.start_sec),
                }
            )

    source_videos = list(seg_links_by_video.values())

    return templates.TemplateResponse(
        request,
        "wiki_concept.html",
        {
            "wiki_page": {
                "id": wiki_page.id,
                "title": wiki_page.title,
                "slug": wiki_page.slug,
                "synthesized_content": wiki_page.synthesized_content or "",
                "source_video_count": wiki_page.source_video_count,
                "last_synthesized_at": wiki_page.last_synthesized_at,
                "status": wiki_page.status,
            },
            "concept": {
                "id": concept.id if concept else None,
                "name": concept.name if concept else wiki_page.title,
                "description": concept.description if concept else None,
            },
            "breadcrumb": breadcrumb,
            "prerequisites": prerequisites,
            "related": related,
            "source_videos": source_videos,
        },
    )


@router.get("/wiki/{slug}", response_class=HTMLResponse, include_in_schema=False)
async def wiki_topic_page(request: Request, slug: str, db: Session = Depends(get_db)):
    """主題頁面（domain 或 category）"""
    topic = db.query(Topic).filter(Topic.slug == slug).first()
    if not topic:
        raise HTTPException(404, "主題不存在")

    # Breadcrumb
    breadcrumb: list[dict] = []
    t: Topic | None = topic
    chain: list[Topic] = []
    while t:
        chain.insert(0, t)
        t = db.query(Topic).filter(Topic.id == t.parent_id).first() if t.parent_id else None
    breadcrumb = [{"name": t.name, "slug": t.slug} for t in chain]

    # Sub-topics
    children = _topic_tree(db, topic.id)

    # Concepts in this topic (ordered by learning path)
    concept_links = (
        db.query(ConceptTopic).filter(ConceptTopic.topic_id == topic.id).all()
    )
    concept_ids = [cl.concept_id for cl in concept_links]
    concepts_map = {c.id: c for c in db.query(Concept).filter(Concept.id.in_(concept_ids)).all()}
    wiki_pages_map = {
        wp.concept_id: wp
        for wp in db.query(WikiPage)
        .filter(WikiPage.concept_id.in_(concept_ids), WikiPage.status == "published")
        .all()
    }

    concept_cards = []
    for concept_id in concept_ids:
        c = concepts_map.get(concept_id)
        if not c:
            continue
        wp = wiki_pages_map.get(concept_id)
        concept_cards.append(
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "video_count": c.video_count or 0,
                "wiki_slug": wp.slug if wp else None,
                "has_wiki": wp is not None,
            }
        )

    # Sort by video_count desc for prominence
    concept_cards.sort(key=lambda x: x["video_count"], reverse=True)

    return templates.TemplateResponse(
        request,
        "wiki_topic.html",
        {
            "topic": {
                "id": topic.id,
                "name": topic.name,
                "slug": topic.slug,
                "description": topic.description,
                "domain": topic.domain,
                "learning_order": topic.learning_order,
            },
            "breadcrumb": breadcrumb,
            "children": children,
            "concept_cards": concept_cards,
        },
    )


# ─── API Endpoints ────────────────────────────────────────────────────────────


@router.get("/api/wiki/topics")
def api_list_topics(db: Session = Depends(get_db)):
    """列出所有主題（樹狀結構）"""
    tree = _topic_tree(db, parent_id=None)
    return {"total": db.query(Topic).count(), "tree": tree}


@router.get("/api/wiki/topics/{topic_id}")
def api_get_topic(topic_id: str, db: Session = Depends(get_db)):
    """取得單一主題"""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(404, "主題不存在")
    concept_links = db.query(ConceptTopic).filter(ConceptTopic.topic_id == topic_id).all()
    concept_ids = [cl.concept_id for cl in concept_links]
    return {
        "id": topic.id,
        "name": topic.name,
        "slug": topic.slug,
        "parent_id": topic.parent_id,
        "domain": topic.domain,
        "description": topic.description,
        "learning_order": topic.learning_order,
        "concept_count": len(concept_ids),
        "children": _topic_tree(db, topic.id),
    }


@router.get("/api/wiki/pages")
def api_list_wiki_pages(
    status: str = "published",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """列出所有 wiki 知識頁面"""
    query = db.query(WikiPage)
    if status:
        query = query.filter(WikiPage.status == status)
    total = query.count()
    pages = query.order_by(WikiPage.updated_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": p.id,
                "title": p.title,
                "slug": p.slug,
                "concept_id": p.concept_id,
                "topic_id": p.topic_id,
                "source_video_count": p.source_video_count,
                "status": p.status,
                "last_synthesized_at": p.last_synthesized_at.isoformat()
                if p.last_synthesized_at
                else None,
            }
            for p in pages
        ],
    }


@router.get("/api/wiki/pages/{page_id_or_slug}")
def api_get_wiki_page(page_id_or_slug: str, db: Session = Depends(get_db)):
    """取得單一 wiki 知識頁面（by ID or slug）"""
    page = (
        db.query(WikiPage).filter(WikiPage.id == page_id_or_slug).first()
        or db.query(WikiPage).filter(WikiPage.slug == page_id_or_slug).first()
    )
    if not page:
        raise HTTPException(404, "知識頁不存在")

    sources = db.query(WikiPageSource).filter(WikiPageSource.wiki_page_id == page.id).all()
    video_ids = list({s.video_id for s in sources})
    videos_map = {v.id: v for v in db.query(Video).filter(Video.id.in_(video_ids)).all()}

    return {
        "id": page.id,
        "title": page.title,
        "slug": page.slug,
        "concept_id": page.concept_id,
        "topic_id": page.topic_id,
        "synthesized_content": page.synthesized_content,
        "source_video_count": page.source_video_count,
        "status": page.status,
        "last_synthesized_at": page.last_synthesized_at.isoformat()
        if page.last_synthesized_at
        else None,
        "sources": [
            {
                "video_id": s.video_id,
                "video_title": str(
                    videos_map[s.video_id].original_filename
                    or videos_map[s.video_id].filename
                )
                if s.video_id in videos_map
                else s.video_id,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "timestamp": _format_mmss(s.start_time),
                "excerpt": s.excerpt,
            }
            for s in sources
        ],
    }


@router.post("/api/wiki/build-taxonomy")
def api_build_taxonomy(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """（維護用）呼叫 GPT 建立/更新主題分類樹"""
    from app.services.taxonomy_builder import build_taxonomy

    result = build_taxonomy(db)
    return {
        "message": (
            f"分類樹建立完成 — "
            f"領域 {result['domains_created']}, "
            f"主題 {result['topics_created']}, "
            f"概念連結 {result['concept_links_created']}"
        ),
        **result,
    }


@router.post("/api/wiki/synthesize")
def api_synthesize_wiki(
    concept_id: str | None = None,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """（維護用）為概念合成 wiki 知識頁面。
    - 若提供 concept_id，只合成該概念
    - 若未提供，合成所有概念（force=True 則強制重新合成）
    """
    from app.services.wiki_synthesizer import synthesize_all_wiki_pages, synthesize_wiki_page

    if concept_id:
        concept = db.query(Concept).filter(Concept.id == concept_id).first()
        if not concept:
            raise HTTPException(404, "概念不存在")
        page = synthesize_wiki_page(concept_id, db)
        if not page:
            return {"message": "無法合成（無素材）", "concept_id": concept_id}
        return {
            "message": f"已合成知識頁：{page.title}",
            "wiki_page_id": page.id,
            "slug": page.slug,
        }
    else:
        result = synthesize_all_wiki_pages(db, force=force)
        return {
            "message": (
                f"批次合成完成 — 合成 {result['synthesized']}, "
                f"跳過 {result['skipped']}, 錯誤 {result['errors']}"
            ),
            **result,
        }


@router.get("/api/wiki/stats")
def api_wiki_stats(db: Session = Depends(get_db)):
    """知識庫統計"""
    return {
        "total_topics": db.query(Topic).count(),
        "total_domains": db.query(Topic).filter(Topic.parent_id.is_(None)).count(),
        "total_wiki_pages": db.query(WikiPage).count(),
        "published_wiki_pages": db.query(WikiPage)
        .filter(WikiPage.status == "published")
        .count(),
        "stale_wiki_pages": db.query(WikiPage).filter(WikiPage.status == "stale").count(),
        "total_concept_links": db.query(ConceptTopic).count(),
    }
