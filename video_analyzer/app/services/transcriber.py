"""使用 Azure OpenAI Whisper 進行語音轉文字"""
import logging
import math
import subprocess
import tempfile
from pathlib import Path

from openai import AzureOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AzureOpenAI | None = None

# Whisper API 單次最大 25MB，保留 1MB 安全緩衝
WHISPER_MAX_BYTES = 24 * 1024 * 1024


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        if not settings.whisper_api_key or not settings.whisper_endpoint:
            raise ValueError("AZURE_OPENAI_API_KEY 或 AZURE_OPENAI_ENDPOINT 未設定，請在 .env 中配置")
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
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


def _split_audio(audio_path: Path) -> list[Path]:
    """
    若音頻超過 WHISPER_MAX_BYTES，用 FFmpeg 切割成多個 chunk。
    回傳 chunk 路徑列表；若未超限則回傳 [audio_path]。
    """
    file_size = audio_path.stat().st_size
    if file_size <= WHISPER_MAX_BYTES:
        return [audio_path]

    duration = _get_audio_duration(audio_path)
    n_chunks = math.ceil(file_size / WHISPER_MAX_BYTES) + 1
    chunk_duration = duration / n_chunks

    logger.info(f"音頻 {file_size / 1024 / 1024:.1f} MB 超過限制，切割為 {n_chunks} 個片段（每段 {chunk_duration:.0f}s）")

    chunk_dir = audio_path.parent / f"{audio_path.stem}_chunks"
    chunk_dir.mkdir(exist_ok=True)
    chunks: list[Path] = []

    for i in range(n_chunks):
        start = i * chunk_duration
        chunk_path = chunk_dir / f"chunk_{i:03d}.mp3"
        cmd = [
            "ffmpeg", "-i", str(audio_path),
            "-ss", str(start), "-t", str(chunk_duration),
            "-c", "copy", "-y", str(chunk_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=120)
        if chunk_path.exists() and chunk_path.stat().st_size > 0:
            chunks.append(chunk_path)

    return chunks


def _transcribe_single(audio_path: Path, language: str) -> str:
    """對單一音頻檔案呼叫 Whisper API"""
    client = _get_client()
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=settings.AZURE_OPENAI_WHISPER_DEPLOYMENT,
            file=f,
            language=language,
            response_format="text",
        )
    return response if isinstance(response, str) else response.text


def transcribe(audio_path: str | Path, language: str = "zh") -> str:
    """
    使用 Azure OpenAI Whisper 將音頻轉為文字。
    超過 25MB 的檔案會自動切割後分段轉錄再合併。

    Args:
        audio_path: 音頻檔案路徑（MP3/WAV/M4A 等）
        language: 語言代碼，預設 "zh"（中文）

    Returns:
        轉錄文字

    Raises:
        FileNotFoundError: 音頻檔案不存在
        ValueError: API Key 或 Endpoint 未設定
        Exception: API 呼叫失敗
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"音頻檔案不存在: {audio_path}")

    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    logger.info(f"開始轉錄: {audio_path.name} ({file_size_mb:.1f} MB)")

    chunks = _split_audio(audio_path)
    chunk_dir = chunks[0].parent if len(chunks) > 1 else None

    try:
        if len(chunks) == 1:
            transcript = _transcribe_single(chunks[0], language)
        else:
            parts: list[str] = []
            for idx, chunk in enumerate(chunks, 1):
                logger.info(f"轉錄片段 {idx}/{len(chunks)}: {chunk.name}")
                parts.append(_transcribe_single(chunk, language))
            transcript = " ".join(parts)
    finally:
        # 清理 chunk 暫存目錄
        if chunk_dir and chunk_dir.exists():
            for c in chunk_dir.iterdir():
                c.unlink(missing_ok=True)
            chunk_dir.rmdir()

    logger.info(f"轉錄完成: {len(transcript)} 字元")
    return transcript
