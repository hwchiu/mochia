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
"""
import argparse
import sys
import uuid
from pathlib import Path
from datetime import datetime

# 確保從 video_analyzer 目錄執行
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.orm import Session
from app.database import SessionLocal, Video, TaskQueue, init_db
from app.config import settings
from app.services.audio_extractor import get_video_duration


# ─────────────────────── Helpers ───────────────────────

def _fmt_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes/1024:.1f} KB"
    if size_bytes < 1024 ** 3:
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
                print(f"   ✅ 登錄: {video_file.name} ({_fmt_size(file_size)}, {_fmt_duration(duration)})")

        db.commit()
        print()
        print(f"📊 掃描結果：發現 {found} 支 | 新登錄 {registered} 支 | 跳過 {skipped} 支")

        if registered > 0 and not args.no_queue:
            answer = input(f"\n是否立即將 {registered} 支新影片加入分析佇列？[Y/n] ").strip().lower()
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
        existing = db.query(TaskQueue).filter(
            TaskQueue.video_id == video.id,
            TaskQueue.status.in_(["pending", "processing"]),
        ).first()
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

        existing = db.query(TaskQueue).filter(
            TaskQueue.video_id == args.video_id,
            TaskQueue.status.in_(["pending", "processing"]),
        ).first()
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
            icon = {"pending": "⏳", "queued": "📋", "processing": "⚙️",
                    "completed": "✅", "failed": "❌"}.get(status, "•")
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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
