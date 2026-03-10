"""使用 Azure OpenAI Whisper 進行語音轉文字"""
import logging
from pathlib import Path

from openai import AzureOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AzureOpenAI | None = None


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
            raise ValueError("AZURE_OPENAI_API_KEY 或 AZURE_OPENAI_ENDPOINT 未設定，請在 .env 中配置")
        _client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
    return _client


def transcribe(audio_path: str | Path, language: str = "zh") -> str:
    """
    使用 Azure OpenAI Whisper 將音頻轉為文字。

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

    client = _get_client()
    file_size_mb = audio_path.stat().st_size / 1024 / 1024
    logger.info(f"開始轉錄: {audio_path.name} ({file_size_mb:.1f} MB)")

    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model=settings.AZURE_OPENAI_WHISPER_DEPLOYMENT,
            file=f,
            language=language,
            response_format="text",
        )

    # Azure Whisper API 回傳的是純文字字串
    transcript = response if isinstance(response, str) else response.text
    logger.info(f"轉錄完成: {len(transcript)} 字元")
    return transcript
