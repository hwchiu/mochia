#!/usr/bin/env python3
"""
Video Analyzer CLI
==================
管理影片分析的命令列工具。

指令：
    python cli.py scan <目錄路徑>      掃描目錄並登錄影片
    python cli.py status               顯示佇列與影片統計
    python cli.py queue-all            將所有 pending 影片加入佇列
    python cli.py queue <video_id>     將單支影片加入佇列
    python cli.py retry                重試所有失敗任務
    python cli.py list [--status S]    列出影片
    python cli.py worker               啟動 Worker（等同 python worker.py）
    python cli.py export-wiki          匯出 wiki 知識庫為靜態 HTML 網站
    python cli.py backfill             補齊所有已完成影片的 segments/知識點/題目
      --dry-run                          預覽，不實際執行
      --skip-whisper                     跳過 Whisper 重跑
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

# 確保從專案根目錄執行
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, TaskQueue, Video, init_db
from app.services.audio_extractor import get_video_duration

# ─────────────────────── Helpers ───────────────────────


def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} KB"
    if size_bytes < 1024**3:
        return f"{size_bytes/1024**2:.1f} MB"
    return f"{size_bytes/1024**3:.2f} GB"


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _get_db() -> Session:
    init_db()
    return SessionLocal()


# ─────────────────────── Commands ───────────────────────


def cmd_scan(args):
    """遞迴掃描目錄，登錄影片到資料庫"""
    scan_path = Path(args.path).resolve()
    if not scan_path.exists():
        print(f"❌ 目錄不存在: {scan_path}")
        sys.exit(1)
    if not scan_path.is_dir():
        print(f"❌ 不是目錄: {scan_path}")
        sys.exit(1)

    db = _get_db()
    try:
        found = skipped = registered = 0
        print(f"🔍 掃描目錄: {scan_path}")
        print(f"   支援格式: {', '.join(settings.SUPPORTED_VIDEO_EXTENSIONS)}")
        print()

        for ext in settings.SUPPORTED_VIDEO_EXTENSIONS:
            for video_file in sorted(scan_path.rglob(f"*{ext}")):
                found += 1
                abs_path = str(video_file.resolve())

                existing = db.query(Video).filter(Video.file_path == abs_path).first()
                if existing:
                    skipped += 1
                    print(f"   ⏭  跳過（已登錄）: {video_file.name}")
                    continue

                file_size = video_file.stat().st_size
                duration = get_video_duration(video_file)
                video_id = uuid.uuid4().hex

                video = Video(
                    id=video_id,
                    filename=video_file.name,
                    original_filename=video_file.name,
                    file_path=abs_path,
                    source="local_scan",
                    file_size=file_size,
                    duration=duration,
                    status="pending",
                )
                db.add(video)
                registered += 1
                print(
                    f"   ✅ 登錄: {video_file.name} ({_fmt_size(file_size)}, {_fmt_duration(duration)})"
                )

        db.commit()
        print()
        print(f"📊 掃描結果：發現 {found} 支 | 新登錄 {registered} 支 | 跳過 {skipped} 支")

        if registered > 0 and not args.no_queue:
            answer = (
                input(f"\n是否立即將 {registered} 支新影片加入分析佇列？[Y/n] ").strip().lower()
            )
            if answer in ("", "y", "yes"):
                cmd_queue_all_videos(db, source="local_scan")
    finally:
        db.close()


def cmd_queue_all_videos(db: Session, source: str | None = None):
    """將所有 pending 影片加入佇列（內部輔助函數）"""
    query = db.query(Video).filter(Video.status == "pending")
    if source:
        query = query.filter(Video.source == source)
    videos = query.all()

    queued = 0
    for video in videos:
        existing = (
            db.query(TaskQueue)
            .filter(
                TaskQueue.video_id == video.id,
                TaskQueue.status.in_(["pending", "processing"]),
            )
            .first()
        )
        if existing:
            continue
        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=video.id,
            priority=5,
            status="pending",
        )
        db.add(task)
        video.status = "queued"
        queued += 1

    db.commit()
    print(f"🚀 已將 {queued} 支影片加入佇列")


def cmd_queue_all(args):
    db = _get_db()
    try:
        cmd_queue_all_videos(db)
    finally:
        db.close()


def cmd_queue(args):
    """將單支影片加入佇列"""
    db = _get_db()
    try:
        video = db.query(Video).filter(Video.id == args.video_id).first()
        if not video:
            print(f"❌ 影片不存在: {args.video_id}")
            sys.exit(1)

        existing = (
            db.query(TaskQueue)
            .filter(
                TaskQueue.video_id == args.video_id,
                TaskQueue.status.in_(["pending", "processing"]),
            )
            .first()
        )
        if existing:
            print(f"⚠ 影片已在佇列中 (task_id={existing.id})")
            return

        task = TaskQueue(
            id=uuid.uuid4().hex,
            video_id=args.video_id,
            priority=getattr(args, "priority", 5),
            status="pending",
        )
        db.add(task)
        video.status = "queued"
        db.commit()
        print(f"✅ 已加入佇列: {video.original_filename}")
    finally:
        db.close()


def cmd_status(args):
    """顯示佇列統計"""
    db = _get_db()
    try:
        print("=" * 50)
        print("📊 影片狀態統計")
        print("=" * 50)
        for status in ["pending", "queued", "processing", "completed", "failed"]:
            count = db.query(Video).filter(Video.status == status).count()
            icon = {
                "pending": "⏳",
                "queued": "📋",
                "processing": "⚙️",
                "completed": "✅",
                "failed": "❌",
            }.get(status, "•")
            print(f"  {icon} {status:<12}: {count:>5} 支")

        total = db.query(Video).count()
        print(f"  {'合計':<13}: {total:>5} 支")

        print()
        print("📋 任務佇列統計")
        print("-" * 50)
        for status in ["pending", "processing", "done", "failed", "cancelled"]:
            count = db.query(TaskQueue).filter(TaskQueue.status == status).count()
            print(f"  {status:<12}: {count:>5} 個")

        # 顯示目前處理中的任務
        processing = db.query(TaskQueue).filter(TaskQueue.status == "processing").all()
        if processing:
            print()
            print("⚙️  目前處理中:")
            for t in processing:
                video = db.query(Video).filter(Video.id == t.video_id).first()
                name = video.original_filename if video else "unknown"
                elapsed = ""
                if t.started_at:
                    secs = int((datetime.utcnow() - t.started_at).total_seconds())
                    elapsed = f" (已執行 {secs}s)"
                print(f"     {name}{elapsed}")
        print("=" * 50)
    finally:
        db.close()


def cmd_list(args):
    """列出影片"""
    db = _get_db()
    try:
        query = db.query(Video)
        if args.status:
            query = query.filter(Video.status == args.status)
        videos = query.order_by(Video.upload_date.desc()).limit(args.limit).all()

        if not videos:
            print("（無符合條件的影片）")
            return

        print(f"{'ID':<10} {'名稱':<40} {'狀態':<12} {'大小':<10} {'時長':<10} {'來源'}")
        print("-" * 100)
        for v in videos:
            print(
                f"{v.id[:8]:<10} "
                f"{v.original_filename[:38]:<40} "
                f"{v.status:<12} "
                f"{_fmt_size(v.file_size or 0):<10} "
                f"{_fmt_duration(v.duration):<10} "
                f"{v.source}"
            )
        print(f"\n共 {len(videos)} 筆")
    finally:
        db.close()


def cmd_retry(args):
    """重試所有失敗任務"""
    db = _get_db()
    try:
        tasks = db.query(TaskQueue).filter(TaskQueue.status == "failed").all()
        if not tasks:
            print("沒有失敗的任務")
            return
        for task in tasks:
            task.status = "pending"
            task.retry_count = 0
            task.error_message = None
            video = db.query(Video).filter(Video.id == task.video_id).first()
            if video:
                video.status = "queued"
                video.error_message = None
        db.commit()
        print(f"✅ 已重設 {len(tasks)} 個失敗任務")
    finally:
        db.close()


def cmd_worker(args):
    """啟動 Worker"""
    from worker import run_worker

    run_worker()


def cmd_backfill(args):
    """補齊所有已完成影片的 segments / 知識點 / 題目"""
    import json
    import os

    from app.database import Transcript, Video, init_db
    from app.routers.concepts import rebuild_concepts_for_video
    from app.routers.quiz import rebuild_quiz_for_video

    init_db()
    db = _get_db()
    dry_run: bool = getattr(args, "dry_run", False)
    skip_whisper: bool = getattr(args, "skip_whisper", False)

    try:
        videos = db.query(Video).filter(Video.status == "completed").all()
        print(f"\n📊 已完成影片：{len(videos)} 支\n")

        seg_ok = seg_skip = seg_fail = 0
        concept_ok = concept_skip = concept_fail = 0
        quiz_ok = quiz_fail = 0

        for i, video in enumerate(videos, 1):
            vid_id = str(video.id)
            fname = str(video.original_filename or video.filename or vid_id)[:40]
            t = db.query(Transcript).filter(Transcript.video_id == vid_id).first()

            print(f"[{i:2d}/{len(videos)}] {fname}")

            # ── Step 1: Re-run Whisper for segments ──────────────────────────
            if not skip_whisper:
                has_segments = bool(t and t.segments and t.segments not in ("null", "[]"))
                if has_segments:
                    print("  ✓ segments 已有，跳過 Whisper")
                    seg_skip += 1
                elif not t or not t.content:
                    print("  ⚠ 無逐字稿，跳過 Whisper")
                    seg_skip += 1
                else:
                    file_path = str(video.file_path or "")
                    if not file_path or not os.path.exists(file_path):
                        print(f"  ⚠ 原始檔不存在 ({file_path or '未知'})，跳過 Whisper")
                        seg_skip += 1
                    elif dry_run:
                        print(f"  [DRY-RUN] 會重跑 Whisper: {file_path}")
                        seg_ok += 1
                    else:
                        try:
                            from app.services.audio_extractor import extract_audio
                            from app.services.transcriber import transcribe

                            print("  🎤 重跑 Whisper…", end="", flush=True)
                            audio_path = extract_audio(file_path)
                            _, segments = transcribe(audio_path, language="zh")
                            if segments:
                                t.segments = json.dumps(segments, ensure_ascii=False)
                                db.commit()
                                print(f" ✅ {len(segments)} 片段")
                                seg_ok += 1
                            else:
                                print(" ⚠ 無片段回傳")
                                seg_skip += 1
                            try:
                                os.remove(audio_path)
                            except OSError:
                                pass
                        except Exception as e:
                            print(f" ❌ {e}")
                            seg_fail += 1

            # ── Step 2: Extract concepts ─────────────────────────────────────
            if dry_run:
                print("  [DRY-RUN] 會抽取知識點")
                concept_ok += 1
            else:
                try:
                    db.expire_all()
                    n = rebuild_concepts_for_video(vid_id, db)
                    if n > 0:
                        print(f"  🧠 知識點：{n} 個 ✅")
                        concept_ok += 1
                    else:
                        print("  🧠 知識點：0 個（GPT 無輸出）")
                        concept_skip += 1
                except Exception as e:
                    print(f"  🧠 知識點失敗：{e}")
                    concept_fail += 1

            # ── Step 3: Generate quiz ─────────────────────────────────────────
            if dry_run:
                print("  [DRY-RUN] 會生成題目")
                quiz_ok += 1
            else:
                try:
                    rebuild_quiz_for_video(vid_id, db)
                    from app.database import Quiz

                    q = db.query(Quiz).filter(Quiz.video_id == vid_id).first()
                    n_quiz = int(q.total_items or 0) if q else 0
                    print(f"  🧩 題目：{n_quiz} 題 ✅")
                    quiz_ok += 1
                except Exception as e:
                    print(f"  🧩 題目失敗：{e}")
                    quiz_fail += 1

            print()

        print("=" * 50)
        if not skip_whisper:
            print(f"🎤 Whisper segments：成功 {seg_ok}，跳過 {seg_skip}，失敗 {seg_fail}")
        print(f"🧠 知識點：成功 {concept_ok}，跳過/空 {concept_skip}，失敗 {concept_fail}")
        print(f"🧩 題目：成功 {quiz_ok}，失敗 {quiz_fail}")
        if dry_run:
            print("\n（以上為 DRY-RUN 預覽，未實際執行）")

    finally:
        db.close()


def cmd_export_wiki(args):
    """匯出 wiki 知識庫為靜態 HTML 網站"""
    import shutil

    from jinja2 import Environment, FileSystemLoader

    from app.database import (
        Concept,
        ConceptRelation,
        ConceptTopic,
        SegmentConcept,
        Topic,
        Video,
        WikiPage,
        WikiPageSource,
    )

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "concept").mkdir(exist_ok=True)

    db = _get_db()
    try:
        templates_dir = Path(__file__).parent / "templates"
        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)
        # Add tojson filter (Jinja2 has it built in with autoescape=True)

        def _fmt_mmss(sec):
            if sec is None:
                return None
            total = max(0, int(float(sec)))
            return f"{total // 60:02d}:{total % 60:02d}"

        def _topic_tree_static(parent_id=None):
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
                        "children": _topic_tree_static(t.id),
                    }
                )
            return result

        pages_exported = 0
        topics_exported = 0

        # ── Index page ────────────────────────────────────────────────────────
        domains_raw = (
            db.query(Topic)
            .filter(Topic.parent_id.is_(None))
            .order_by(Topic.learning_order.asc())
            .all()
        )
        domain_data = []
        for d in domains_raw:
            cc = (
                db.query(ConceptTopic)
                .join(Topic, ConceptTopic.topic_id == Topic.id)
                .filter(Topic.domain == d.name)
                .count()
            )
            wc = (
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
                    "concept_count": cc,
                    "wiki_count": wc,
                    "children": _topic_tree_static(d.id),
                }
            )

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

        tmpl = env.get_template("wiki_index.html")
        html = tmpl.render(
            domains=domain_data,
            recent_pages=recent_data,
            total_concepts=db.query(Concept).count(),
            total_wiki=db.query(WikiPage).filter(WikiPage.status == "published").count(),
            total_topics=db.query(Topic).count(),
        )
        (output_dir / "index.html").write_text(html, encoding="utf-8")
        print("✅ 匯出首頁: index.html")

        # ── Topic pages ───────────────────────────────────────────────────────
        all_topics = db.query(Topic).all()
        for topic in all_topics:
            chain = []
            t = topic
            while t:
                chain.insert(0, t)
                t = db.query(Topic).filter(Topic.id == t.parent_id).first() if t.parent_id else None
            breadcrumb = [{"name": t.name, "slug": t.slug} for t in chain]

            children = _topic_tree_static(topic.id)
            concept_links = db.query(ConceptTopic).filter(ConceptTopic.topic_id == topic.id).all()
            concept_ids = [cl.concept_id for cl in concept_links]
            concepts_map = {
                c.id: c for c in db.query(Concept).filter(Concept.id.in_(concept_ids)).all()
            }
            wiki_pages_map = {
                wp.concept_id: wp
                for wp in db.query(WikiPage)
                .filter(WikiPage.concept_id.in_(concept_ids), WikiPage.status == "published")
                .all()
            }
            concept_cards = []
            for cid in concept_ids:
                c = concepts_map.get(cid)
                if not c:
                    continue
                wp = wiki_pages_map.get(cid)
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
            concept_cards.sort(key=lambda x: x["video_count"], reverse=True)

            tmpl = env.get_template("wiki_topic.html")
            html = tmpl.render(
                topic={
                    "id": topic.id,
                    "name": topic.name,
                    "slug": topic.slug,
                    "description": topic.description,
                    "domain": topic.domain,
                    "learning_order": topic.learning_order,
                },
                breadcrumb=breadcrumb,
                children=children,
                concept_cards=concept_cards,
            )
            (output_dir / f"{topic.slug}.html").write_text(html, encoding="utf-8")
            topics_exported += 1

        print(f"✅ 匯出主題頁: {topics_exported} 頁")

        # ── Concept/wiki pages ────────────────────────────────────────────────
        wiki_pages = db.query(WikiPage).filter(WikiPage.status == "published").all()
        for wp in wiki_pages:
            concept = db.query(Concept).filter(Concept.id == wp.concept_id).first()
            breadcrumb = []
            if concept:
                ct = db.query(ConceptTopic).filter(ConceptTopic.concept_id == concept.id).first()
                if ct:
                    topic = db.query(Topic).filter(Topic.id == ct.topic_id).first()
                    if topic:
                        chain = []
                        t = topic
                        while t:
                            chain.insert(0, t)
                            t = (
                                db.query(Topic).filter(Topic.id == t.parent_id).first()
                                if t.parent_id
                                else None
                            )
                        breadcrumb = [{"name": t.name, "slug": t.slug} for t in chain]

            # Relations
            prerequisites = []
            related = []
            if concept:
                rels_from = (
                    db.query(ConceptRelation)
                    .filter(ConceptRelation.source_concept_id == concept.id)
                    .all()
                )
                rels_to = (
                    db.query(ConceptRelation)
                    .filter(ConceptRelation.target_concept_id == concept.id)
                    .all()
                )
                all_ids = list(
                    {r.target_concept_id for r in rels_from}
                    | {r.source_concept_id for r in rels_to}
                )
                rel_concepts = {
                    c.id: c for c in db.query(Concept).filter(Concept.id.in_(all_ids)).all()
                }
                rel_wiki = {
                    p.concept_id: p
                    for p in db.query(WikiPage)
                    .filter(WikiPage.concept_id.in_(all_ids), WikiPage.status == "published")
                    .all()
                }
                for r in rels_from:
                    rc = rel_concepts.get(r.target_concept_id)
                    if not rc:
                        continue
                    entry = {
                        "name": rc.name,
                        "slug": rel_wiki[rc.id].slug if rc.id in rel_wiki else None,
                        "relation_type": r.relation_type,
                    }
                    if r.relation_type == "prerequisite":
                        prerequisites.append(entry)
                    else:
                        related.append(entry)

            # Source videos
            sources = db.query(WikiPageSource).filter(WikiPageSource.wiki_page_id == wp.id).all()
            vid_ids = list({s.video_id for s in sources})
            vmap = {v.id: v for v in db.query(Video).filter(Video.id.in_(vid_ids)).all()}
            seg_by_vid = {}
            if concept:
                for sl in (
                    db.query(SegmentConcept)
                    .filter(SegmentConcept.concept_id == concept.id)
                    .order_by(SegmentConcept.start_sec)
                    .all()
                ):
                    vid = vmap.get(sl.video_id)
                    if not vid:
                        continue
                    vid_id = str(sl.video_id)
                    if vid_id not in seg_by_vid:
                        seg_by_vid[vid_id] = {
                            "video_id": vid_id,
                            "title": str(vid.original_filename or vid.filename),
                            "timestamps": [],
                        }
                    seg_by_vid[vid_id]["timestamps"].append(
                        {
                            "start_sec": sl.start_sec,
                            "end_sec": sl.end_sec,
                            "display": _fmt_mmss(sl.start_sec),
                        }
                    )

            tmpl = env.get_template("wiki_concept.html")
            html = tmpl.render(
                wiki_page={
                    "id": wp.id,
                    "title": wp.title,
                    "slug": wp.slug,
                    "synthesized_content": wp.synthesized_content or "",
                    "source_video_count": wp.source_video_count,
                    "last_synthesized_at": wp.last_synthesized_at,
                    "status": wp.status,
                },
                concept={
                    "id": concept.id if concept else None,
                    "name": concept.name if concept else wp.title,
                    "description": concept.description if concept else None,
                },
                breadcrumb=breadcrumb,
                prerequisites=prerequisites,
                related=related,
                source_videos=list(seg_by_vid.values()),
            )
            (output_dir / "concept" / f"{wp.slug}.html").write_text(html, encoding="utf-8")
            pages_exported += 1

        print(f"✅ 匯出知識詞條: {pages_exported} 頁")

        # ── Copy static assets ────────────────────────────────────────────────
        static_src = Path(__file__).parent / "static"
        static_dst = output_dir / "static"
        if static_src.exists():
            if static_dst.exists():
                shutil.rmtree(static_dst)
            shutil.copytree(str(static_src), str(static_dst))
            print("✅ 複製靜態資源")

        # ── Sitemap ───────────────────────────────────────────────────────────
        sitemap_urls = ["index.html"]
        sitemap_urls += [f"{t.slug}.html" for t in db.query(Topic).all()]
        sitemap_urls += [
            f"concept/{p.slug}.html"
            for p in db.query(WikiPage).filter(WikiPage.status == "published").all()
        ]
        sitemap = "\n".join(sitemap_urls)
        (output_dir / "sitemap.txt").write_text(sitemap, encoding="utf-8")
        print(f"✅ 生成 sitemap.txt ({len(sitemap_urls)} 頁)")

        print()
        print(f"🎉 匯出完成！輸出目錄: {output_dir}")
        print(f"   首頁:         {output_dir}/index.html")
        print(f"   主題頁:       {topics_exported} 頁")
        print(f"   知識詞條:     {pages_exported} 頁")

    finally:
        db.close()


# ─────────────────────── Argument Parser ───────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Video Analyzer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    p_scan = subparsers.add_parser("scan", help="掃描目錄並登錄影片")
    p_scan.add_argument("path", help="要掃描的目錄路徑")
    p_scan.add_argument("--no-queue", action="store_true", help="掃描後不詢問是否加入佇列")
    p_scan.set_defaults(func=cmd_scan)

    # status
    p_status = subparsers.add_parser("status", help="顯示佇列統計")
    p_status.set_defaults(func=cmd_status)

    # queue-all
    p_qa = subparsers.add_parser("queue-all", help="將所有 pending 影片加入佇列")
    p_qa.set_defaults(func=cmd_queue_all)

    # queue
    p_q = subparsers.add_parser("queue", help="將單支影片加入佇列")
    p_q.add_argument("video_id", help="影片 ID")
    p_q.add_argument("--priority", type=int, default=5, help="優先級 1-10（預設 5）")
    p_q.set_defaults(func=cmd_queue)

    # retry
    p_retry = subparsers.add_parser("retry", help="重試所有失敗任務")
    p_retry.set_defaults(func=cmd_retry)

    # list
    p_list = subparsers.add_parser("list", help="列出影片")
    p_list.add_argument("--status", help="篩選狀態")
    p_list.add_argument("--limit", type=int, default=50, help="最多顯示筆數（預設 50）")
    p_list.set_defaults(func=cmd_list)

    # worker
    p_worker = subparsers.add_parser("worker", help="啟動 Worker 進程")
    p_worker.set_defaults(func=cmd_worker)

    # export-wiki
    p_export = subparsers.add_parser("export-wiki", help="匯出 wiki 知識庫為靜態 HTML 網站")
    p_export.add_argument("--output", default="./wiki-site", help="輸出目錄（預設 ./wiki-site）")
    p_export.set_defaults(func=cmd_export_wiki)

    # backfill
    p_bf = subparsers.add_parser(
        "backfill",
        help="補齊所有已完成影片的 segments / 知識點 / 題目",
    )
    p_bf.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="預覽會處理哪些影片，不實際執行",
    )
    p_bf.add_argument(
        "--skip-whisper",
        action="store_true",
        dest="skip_whisper",
        help="跳過 Whisper 重跑，只補知識點和題目",
    )
    p_bf.set_defaults(func=cmd_backfill)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
