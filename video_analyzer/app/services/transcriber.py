"""使用 OpenAI Whisper API 進行語音轉文字"""
import logging
from pathlib import Path

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未設定，請在 .env 中配置")
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def transcribe(audio_path: str | Path, language: str = "zh") -> str:
    """
    使用 Whisper API 將音頻轉為文字。

    Args:
        audio_path: 音頻檔案路徑（MP3/WAV/M4A 等）
        language: 語言代碼，預設 "zh"（中文）

    Returns:
        轉錄文字

    Raises:
        FileNotFoundError: 音頻檔案不存在
        ValueError: API Key 未設定
        Exception: API 呼叫失敗
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"音頻檔案不存在: {audio_path}")

    client = _get_client()
    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    logger.info(f"開始轉錄: {audio_path.name} ({file_size_mb:.1f} MB)")

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=f,
            language=language,
            response_format="text",
        )

    # Whisper API 回傳的是純文字字串
    transcript = response if isinstance(response, str) else response.text
    logger.info(f"轉錄完成: {len(transcript)} 字元")
    return transcript
