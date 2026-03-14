#!/usr/bin/env python3
"""
convert_to_mp4.py — Batch video converter
==========================================

Recursively scans a folder (or converts a single file) and converts
unsupported/non-seekable formats (avi/flv/mkv/wmv/…) to H.264/AAC MP4
with a front-loaded moov atom so the browser can seek immediately.

Usage:
    python tools/convert_to_mp4.py <path>
    python tools/convert_to_mp4.py <path> --dry-run
    python tools/convert_to_mp4.py <path> --workers 4
    python tools/convert_to_mp4.py <path> --delete-original
    python tools/convert_to_mp4.py <path> --output-dir /some/dest
    python tools/convert_to_mp4.py <path> --formats .avi .mkv
    python tools/convert_to_mp4.py <path> --overwrite

No dependency on the web app or its database — pure stdlib + FFmpeg.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_FORMATS: frozenset[str] = frozenset({".wmv", ".mkv", ".avi", ".flv"})

# H.264/AAC, CRF 23 (visually transparent), faststart for instant browser seek.
_FFMPEG_BASE: list[str] = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "error",
    "-y",          # overwrite output without asking
    "-i", "{input}",
    "-c:v", "libx264",
    "-preset", "fast",
    "-crf", "23",
    "-c:a", "aac",
    "-b:a", "128k",
    "-movflags", "+faststart",
    "{output}",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Result dataclass ──────────────────────────────────────────────────────────


@dataclass
class ConvertResult:
    source: Path
    dest: Path
    skipped: bool = False        # output already exists and --overwrite not set
    dry_run: bool = False
    success: bool = False
    error: str = ""


# ── Core helpers ──────────────────────────────────────────────────────────────


def find_targets(
    root: Path,
    formats: frozenset[str],
    recursive: bool = True,
) -> list[Path]:
    """Return all video files under *root* whose suffix matches *formats*."""
    if root.is_file():
        return [root] if root.suffix.lower() in formats else []

    glob = root.rglob if recursive else root.glob
    files: list[Path] = []
    for ext in formats:
        files.extend(glob(f"*{ext}"))
        files.extend(glob(f"*{ext.upper()}"))
    return sorted(set(files))


def _build_output_path(source: Path, output_dir: Path | None) -> Path:
    """Compute the .mp4 destination path for *source*."""
    dest_dir = output_dir if output_dir else source.parent
    return dest_dir / (source.stem + ".mp4")


def convert_one(
    source: Path,
    dest: Path,
    *,
    overwrite: bool,
    dry_run: bool,
    delete_original: bool,
    lock: threading.Lock,
) -> ConvertResult:
    """Convert a single file; thread-safe console output via *lock*."""
    result = ConvertResult(source=source, dest=dest)

    if dest.exists() and not overwrite:
        with lock:
            log.info("⏭  跳過（已存在）: %s", dest.name)
        result.skipped = True
        return result

    if dry_run:
        with lock:
            log.info("🔍 [dry-run] %s  →  %s", source, dest)
        result.dry_run = True
        result.success = True
        return result

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        arg.replace("{input}", str(source)).replace("{output}", str(dest))
        for arg in _FFMPEG_BASE
    ]

    with lock:
        log.info("⚙️  轉換中: %s", source.name)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            result.error = proc.stderr.strip().splitlines()[-1] if proc.stderr else "unknown error"
            with lock:
                log.error("❌ 失敗: %s\n   %s", source.name, result.error)
            return result

        result.success = True
        size_mb = dest.stat().st_size / 1024 / 1024
        with lock:
            log.info("✅ 完成: %s  (%.1f MB)", dest.name, size_mb)

        if delete_original:
            source.unlink()
            with lock:
                log.info("🗑  已刪除原始檔: %s", source.name)

    except FileNotFoundError:
        result.error = "ffmpeg not found — please install FFmpeg first"
        with lock:
            log.error("❌ %s", result.error)

    return result


# ── Orchestrator ──────────────────────────────────────────────────────────────


def run_conversion(
    root: Path,
    *,
    formats: frozenset[str],
    output_dir: Path | None,
    workers: int,
    overwrite: bool,
    dry_run: bool,
    delete_original: bool,
    recursive: bool,
) -> list[ConvertResult]:
    """Discover files and convert them (possibly in parallel)."""
    targets = find_targets(root, formats, recursive=recursive)

    if not targets:
        log.info("😶 沒有找到需要轉換的檔案（格式：%s）", ", ".join(sorted(formats)))
        return []

    log.info("📂 發現 %d 個檔案，使用 %d 個執行緒", len(targets), workers)

    jobs = [
        (src, _build_output_path(src, output_dir))
        for src in targets
    ]

    lock = threading.Lock()
    results: list[ConvertResult] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                convert_one,
                src,
                dest,
                overwrite=overwrite,
                dry_run=dry_run,
                delete_original=delete_original,
                lock=lock,
            ): src
            for src, dest in jobs
        }
        for future in as_completed(futures):
            results.append(future.result())

    return results


def _print_summary(results: list[ConvertResult]) -> int:
    """Print a results summary; return exit code (0 = all ok)."""
    total = len(results)
    ok = sum(1 for r in results if r.success)
    skipped = sum(1 for r in results if r.skipped)
    failed = [r for r in results if not r.success and not r.skipped and not r.dry_run]

    print()
    print("═" * 50)
    print(f"  📊 轉換結果")
    print(f"  總計: {total}  ✅成功: {ok}  ⏭跳過: {skipped}  ❌失敗: {len(failed)}")
    if failed:
        print()
        print("  失敗清單:")
        for r in failed:
            print(f"    • {r.source.name}: {r.error}")
    print("═" * 50)

    return 1 if failed else 0


# ── CLI entry point ───────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="convert_to_mp4",
        description="批次將影片轉換成可線上 seek 的 MP4 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "path",
        help="目標目錄（遞迴掃描）或單一影片檔案",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        default=sorted(DEFAULT_FORMATS),
        metavar="EXT",
        help=f"要轉換的副檔名（預設: {' '.join(sorted(DEFAULT_FORMATS))}）",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        help="輸出目錄（預設：與原始檔案同目錄）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        metavar="N",
        help="平行轉換執行緒數（預設: 2）",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="若輸出 MP4 已存在，強制覆蓋",
    )
    parser.add_argument(
        "--delete-original",
        action="store_true",
        help="轉換成功後刪除原始檔案",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="不遞迴掃描子目錄",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出會被轉換的檔案，不實際執行",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not shutil.which("ffmpeg"):
        print("❌ FFmpeg 未安裝。請先安裝：\n  macOS: brew install ffmpeg\n  Ubuntu: sudo apt install ffmpeg")
        return 1

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"❌ 路徑不存在: {root}")
        return 1

    output_dir: Path | None = Path(args.output_dir).resolve() if args.output_dir else None
    formats = frozenset(
        ext if ext.startswith(".") else f".{ext}"
        for ext in args.formats
    )

    results = run_conversion(
        root,
        formats=formats,
        output_dir=output_dir,
        workers=max(1, args.workers),
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        delete_original=args.delete_original,
        recursive=not args.no_recursive,
    )

    return _print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
