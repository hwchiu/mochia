"""從影片檔案提取音頻，供 Whisper 轉錄使用"""
import re
import subprocess
import logging
from pathlib import Path
from typing import Callable
import uuid

from app.config import settings

logger = logging.getLogger(__name__)


def extract_audio(video_path: str | Path, progress_callback: Callable[[int], None] | None = None) -> Path:
    """
    使用 FFmpeg 從影片提取音頻，輸出為 MP3 格式。
    若提供 progress_callback，會即時回報提取進度（0-100）。

    Args:
        video_path: 影片檔案的路徑
        progress_callback: 可選的進度回呼，接受 int (0-100)

    Returns:
        提取的音頻檔案路徑（位於 AUDIO_TEMP_DIR）

    Raises:
        FileNotFoundError: 影片檔案不存在
        RuntimeError: FFmpeg 提取失敗
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"影片檔案不存在: {video_path}")

    audio_filename = f"{uuid.uuid4().hex}.mp3"
    audio_path = settings.AUDIO_TEMP_DIR / audio_filename

    duration = get_video_duration(video_path) if progress_callback else None

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",                    # 不處理影像
        "-acodec", "libmp3lame",
        "-ab", "32k",             # 32kbps 足夠語音識別，支援更長影片不超 25MB 限制
        "-ar", "16000",           # 16kHz 採樣率（Whisper 最佳化）
        "-ac", "1",               # 單聲道
        "-y",                     # 覆蓋輸出檔案
        str(audio_path),
    ]

    logger.info(f"提取音頻: {video_path.name} -> {audio_path.name}")

    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, bufsize=1)

    for line in process.stderr:
        if progress_callback and duration and 'time=' in line:
            m = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
            if m:
                h, mn, s = m.groups()
                secs = int(h) * 3600 + int(mn) * 60 + float(s)
                pct = min(int(secs / duration * 100), 99)
                progress_callback(pct)

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg 提取失敗（returncode={process.returncode}）")

    logger.info(f"音頻提取完成: {audio_path.name} ({audio_path.stat().st_size / 1024:.1f} KB)")
    return audio_path


def get_video_duration(video_path: str | Path) -> float | None:
    """
    使用 ffprobe 取得影片時長（秒）。
    若失敗則回傳 None，不中斷流程。
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"無法取得影片時長 {video_path}: {e}")
    return None


def cleanup_audio(audio_path: str | Path) -> None:
    """刪除暫存音頻檔案"""
    try:
        Path(audio_path).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"刪除暫存音頻失敗 {audio_path}: {e}")
