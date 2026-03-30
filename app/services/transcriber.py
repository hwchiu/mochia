"""使用 Azure OpenAI Whisper 進行語音轉文字"""

from __future__ import annotations

import logging
import math
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

import openai
from openai import AzureOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

logger = logging.getLogger(__name__)

_client: AzureOpenAI | None = None
_client_lock = threading.Lock()

# Whisper API 單次最大 25MB，保留 1MB 安全緩衝
WHISPER_MAX_BYTES = 24 * 1024 * 1024


def _get_client() -> AzureOpenAI:
    global _client
    with _client_lock:
        if _client is None:
            if not settings.whisper_api_key or not settings.whisper_endpoint:
                raise ValueError(
                    "AZURE_OPENAI_API_KEY 或 AZURE_OPENAI_ENDPOINT 未設定，請在 .env 中配置"
                )
            _client = AzureOpenAI(
                api_key=settings.whisper_api_key,
                azure_endpoint=settings.whisper_endpoint,
                api_version=settings.whisper_api_version,
                timeout=settings.WHISPER_TIMEOUT,
            )
    return _client


def _get_audio_duration(audio_path: Path) -> float:
    """使用 ffprobe 取得音頻時長（秒）"""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


def _split_audio(audio_path: Path) -> list[Path]:
    """Split oversized audio into chunks for Whisper API limits.

    Args:
        audio_path: Path to the source MP3 audio file.

    Returns:
        List of chunk file paths. Returns ``[audio_path]`` if the file is
        within the ``WHISPER_MAX_BYTES`` limit (no split needed).
    """
    file_size = audio_path.stat().st_size
    if file_size <= WHISPER_MAX_BYTES:
        return [audio_path]

    duration = _get_audio_duration(audio_path)
    n_chunks = math.ceil(file_size / WHISPER_MAX_BYTES) + 1
    chunk_duration = duration / n_chunks

    logger.info(
        f"音頻 {file_size / 1024 / 1024:.1f} MB 超過限制，切割為 {n_chunks} 個片段（每段 {chunk_duration:.0f}s）"
    )

    chunk_dir = audio_path.parent / f"{audio_path.stem}_chunks"
    chunk_dir.mkdir(exist_ok=True)
    chunks: list[Path] = []

    for i in range(n_chunks):
        start = i * chunk_duration
        chunk_path = chunk_dir / f"chunk_{i:03d}.mp3"
        cmd = [
            "ffmpeg",
            "-i",
            str(audio_path),
            "-ss",
            str(start),
            "-t",
            str(chunk_duration),
            "-c",
            "copy",
            "-y",
            str(chunk_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=120)
        if chunk_path.exists() and chunk_path.stat().st_size > 0:
            chunks.append(chunk_path)

    return chunks


def _transcribe_with_heartbeat(
    audio_path: Path,
    language: str,
    progress_callback: Callable[[int, int, int], None],
    chunk_idx: int,
    total_chunks: int,
) -> tuple[str, list[dict]]:
    """
    呼叫 Whisper API，同時用背景執行緒每 5 秒發送一次心跳進度更新。
    因為 Whisper 不支援 streaming，用時間估算進度（上限 90%，完成後推到 100%）。
    """
    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    # 32kbps MP3：1 MB ≈ 4 分鐘音頻；Whisper 通常耗時約音頻長度的 5-10%
    estimated_audio_sec = file_size_mb * 1024 * 8 / 32
    estimated_wait_sec = max(20.0, estimated_audio_sec * 0.08)

    result_holder: list[tuple[str, list[dict]]] = []
    error_holder: list[Exception] = []
    stop_event = threading.Event()
    start_time = time.time()

    def heartbeat():
        while not stop_event.is_set():
            stop_event.wait(timeout=5)
            if stop_event.is_set():
                break
            elapsed = time.time() - start_time
            # 最高推到 90%，留最後 10% 給完成
            sub_pct = min(90, int(elapsed / estimated_wait_sec * 85))
            base = int((chunk_idx - 1) / total_chunks * 100)
            chunk_share = int(sub_pct / total_chunks)
            progress_callback(base + chunk_share, chunk_idx, total_chunks)

    t = threading.Thread(target=heartbeat, daemon=True)
    t.start()

    try:
        text, segments = _transcribe_single(audio_path, language)
        result_holder.append((text, segments))
    except Exception as e:
        error_holder.append(e)
    finally:
        stop_event.set()
        t.join(timeout=3)

    if error_holder:
        raise error_holder[0]
    return result_holder[0]


@retry(
    retry=retry_if_exception_type(
        (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
    ),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _transcribe_single(audio_path: Path, language: str) -> tuple[str, list[dict]]:
    """對單一音頻檔案呼叫 Whisper API，回傳 (text, segments)。"""
    client = _get_client()
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=settings.AZURE_OPENAI_WHISPER_DEPLOYMENT,
            file=f,
            language=language,
            response_format="verbose_json",
        )
    text = response.text
    segments = [
        {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
        for s in (response.segments or [])  # type: ignore[attr-defined]
    ]
    return text, segments


def transcribe(
    audio_path: str | Path,
    language: str = "zh",
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> tuple[str, list[dict]]:
    """Transcribe audio file to text using OpenAI Whisper API.

    Args:
        audio_path: Path to the MP3 audio file to transcribe.
        language: BCP-47 language code, defaults to "zh" (Chinese).
        progress_callback: Optional callable(percent: int, chunk_idx: int, total_chunks: int)
            for progress updates.

    Returns:
        Tuple of (transcript_text, segments) where segments is a list of
        dicts with 'start', 'end', and 'text' keys.

    Raises:
        FileNotFoundError: If audio_path does not exist.
        ValueError: If Whisper API credentials are not configured.
        RuntimeError: If transcription fails after retries.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"音頻檔案不存在: {audio_path}")

    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    logger.info(f"開始轉錄: {audio_path.name} ({file_size_mb:.1f} MB)")

    chunks = _split_audio(audio_path)
    total = len(chunks)
    chunk_dir = chunks[0].parent if total > 1 else None

    try:
        if total == 1:
            if progress_callback:
                progress_callback(0, 1, 1)
                text, segments = _transcribe_with_heartbeat(
                    chunks[0], language, progress_callback, 1, 1
                )
            else:
                text, segments = _transcribe_single(chunks[0], language)
            if progress_callback:
                progress_callback(100, 1, 1)
            transcript = text
        else:
            chunk_duration = _get_audio_duration(audio_path) / total
            all_parts: list[str] = []
            all_segments: list[dict] = []
            for idx, chunk in enumerate(chunks, 1):
                if progress_callback:
                    progress_callback(int((idx - 1) / total * 100), idx, total)
                    logger.info(f"轉錄片段 {idx}/{total}: {chunk.name}")
                    chunk_text, chunk_segs = _transcribe_with_heartbeat(
                        chunk, language, progress_callback, idx, total
                    )
                else:
                    logger.info(f"轉錄片段 {idx}/{total}: {chunk.name}")
                    chunk_text, chunk_segs = _transcribe_single(chunk, language)
                chunk_offset = (idx - 1) * chunk_duration
                for seg in chunk_segs:
                    all_segments.append(
                        {
                            "start": seg["start"] + chunk_offset,
                            "end": seg["end"] + chunk_offset,
                            "text": seg["text"],
                        }
                    )
                all_parts.append(chunk_text)
            if progress_callback:
                progress_callback(100, total, total)
            transcript = " ".join(all_parts)
            segments = all_segments
    finally:
        # 清理 chunk 暫存目錄
        if chunk_dir and chunk_dir.exists():
            for c in chunk_dir.iterdir():
                c.unlink(missing_ok=True)
            chunk_dir.rmdir()

    logger.info(f"轉錄完成: {len(transcript)} 字元，{len(segments)} 個片段")
    return transcript, segments
