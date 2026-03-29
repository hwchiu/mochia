#!/usr/bin/env python3
"""Host-side Google Drive File Stream warmup tool.

## 問題背景

Google Drive「串流模式（Stream files）」的檔案是虛擬佔位符。
Docker container 內的 FFmpeg 透過 VirtioFS/osxfs 讀取這些檔案時，
GDrive 不會觸發下載（因為 GDrive FUSE 只回應 macOS 原生 process 的 I/O）。

## 解法

此腳本在 HOST（macOS）上執行，做 sequential pre-read，
讓 GDrive 把影片下載到本地快取後，Docker 內的 FFmpeg 才能正常存取。

## 使用方式

    # 一次性：對指定檔案做預讀
    python3 tools/gdrive_warmup.py /Volumes/GoogleDrive/.../video.mp4

    # 批次：從 .env 讀取 VIDEO_DIR_1~5，對所有未快取影片做預讀
    python3 tools/gdrive_warmup.py --all

    # 監控模式：持續監控，有新檔案就自動預讀（適合背景執行）
    python3 tools/gdrive_warmup.py --watch
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ── 設定 ──────────────────────────────────────────────────────────────────────

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB per read chunk
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv", ".flv", ".webm", ".ts", ".mts"}
WATCH_INTERVAL = 30  # seconds between scans in --watch mode

# ── Core warmup ───────────────────────────────────────────────────────────────


def warmup_file(path: Path) -> bool:
    """Sequential read of *path* to force GDrive to download it locally.

    Returns True on success, False on error.
    """
    try:
        size = path.stat().st_size
    except OSError as e:
        print(f"  ✗ stat 失敗: {e}", file=sys.stderr)
        return False

    if size == 0:
        print(f"  ⚠ 檔案大小為 0，跳過: {path.name}")
        return True

    size_mb = size / (1024 * 1024)
    print(f"  ↓ 預讀 {path.name}  ({size_mb:.0f} MB)", end="", flush=True)

    try:
        read = 0
        last_pct = -1
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                read += len(chunk)
                pct = int(read * 100 / size)
                if pct >= last_pct + 10:
                    print(f"\r  ↓ 預讀 {path.name}  ({size_mb:.0f} MB)  {pct}%", end="", flush=True)
                    last_pct = pct
        print(f"\r  ✓ 完成   {path.name}  ({size_mb:.0f} MB)          ")
        return True
    except OSError as e:
        print(f"\n  ✗ 讀取失敗: {e}", file=sys.stderr)
        return False


# ── Path helpers ──────────────────────────────────────────────────────────────


def _load_env_video_dirs() -> list[Path]:
    """Read VIDEO_DIR_1~5 from .env in the project root."""
    env_path = Path(__file__).parent.parent / ".env"
    dirs: list[Path] = []
    if not env_path.exists():
        print(f"找不到 .env（{env_path}），請在專案根目錄建立", file=sys.stderr)
        return dirs
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("VIDEO_DIR_"):
            _, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if value:
                p = Path(value)
                if p.is_dir():
                    dirs.append(p)
                else:
                    print(f"  ⚠ VIDEO_DIR 不存在或不是目錄: {value}", file=sys.stderr)
    return dirs


def collect_video_files(dirs: list[Path]) -> list[Path]:
    """Recursively collect video files from *dirs*."""
    files: list[Path] = []
    for d in dirs:
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                files.append(p)
    return files


def is_locally_cached(path: Path) -> bool:
    """Heuristic: try to read the first 4 KB without blocking.

    On macOS, GDrive cached files read instantly; stubs may block or error.
    We use a quick non-blocking check via os.open with O_NONBLOCK.
    If the read completes immediately with real bytes, assume cached.
    Returns True if we can confirm the file is locally available.
    Falls back to False (assume not cached) on any error.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY | os.O_NONBLOCK)
        try:
            data = os.read(fd, 4096)
            return len(data) == 4096
        finally:
            os.close(fd)
    except (BlockingIOError, OSError):
        return False


# ── Modes ─────────────────────────────────────────────────────────────────────


def run_single(path: Path) -> None:
    if not path.exists():
        sys.exit(f"✗ 檔案不存在: {path}")
    print(f"=== 預讀單一檔案: {path} ===")
    ok = warmup_file(path)
    sys.exit(0 if ok else 1)


def run_all(check_cache: bool = True) -> None:
    dirs = _load_env_video_dirs()
    if not dirs:
        sys.exit("找不到任何有效的 VIDEO_DIR，請確認 .env 設定")
    print(f"=== 掃描 {len(dirs)} 個目錄 ===")
    files = collect_video_files(dirs)
    print(f"找到 {len(files)} 個影片檔案")
    ok_count = skip_count = fail_count = 0
    for f in files:
        if check_cache and is_locally_cached(f):
            skip_count += 1
            continue
        if warmup_file(f):
            ok_count += 1
        else:
            fail_count += 1
    print(f"\n完成：✓ {ok_count} 個預讀  ⏭ {skip_count} 個已快取  ✗ {fail_count} 個失敗")


def run_watch() -> None:
    dirs = _load_env_video_dirs()
    if not dirs:
        sys.exit("找不到任何有效的 VIDEO_DIR，請確認 .env 設定")
    print(f"=== 監控模式（每 {WATCH_INTERVAL}s 掃描一次，Ctrl+C 結束）===")
    warmed: set[Path] = set()
    while True:
        files = collect_video_files(dirs)
        new = [f for f in files if f not in warmed and not is_locally_cached(f)]
        if new:
            print(f"\n[{time.strftime('%H:%M:%S')}] 發現 {len(new)} 個未快取檔案")
        for f in new:
            if warmup_file(f):
                warmed.add(f)
        try:
            time.sleep(WATCH_INTERVAL)
        except KeyboardInterrupt:
            print("\n監控結束")
            break


# ── CLI ───────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Drive File Stream 預讀工具（在 HOST 上執行）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("file", nargs="?", type=Path, help="單一檔案路徑")
    group.add_argument("--all", action="store_true", help="批次預讀所有 VIDEO_DIR 下的影片")
    group.add_argument("--watch", action="store_true", help="持續監控模式")
    parser.add_argument(
        "--no-cache-check",
        action="store_true",
        help="跳過快取偵測，強制重新預讀所有檔案",
    )
    args = parser.parse_args()

    if args.file:
        run_single(args.file)
    elif args.all:
        run_all(check_cache=not args.no_cache_check)
    elif args.watch:
        run_watch()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
