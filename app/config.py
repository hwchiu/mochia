from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    APP_NAME: str = "Video Analyzer"
    APP_VERSION: str = "dev"   # overridden by Docker build-arg GIT_SHA at build time
    BUILD_DATE: str = "unknown"  # overridden by Docker build-arg BUILD_DATE at build time

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 文件路徑
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    UPLOAD_DIR: Path = PROJECT_ROOT / "uploads"
    DATA_DIR: Path = PROJECT_ROOT / "data"
    AUDIO_TEMP_DIR: Path = PROJECT_ROOT / "data" / "audio_temp"

    # Azure OpenAI 配置
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-35-turbo"
    AZURE_OPENAI_API_VERSION: str = "2024-02-01"

    # Azure OpenAI Whisper 配置（語音轉文字）
    # 若 Whisper 部署在不同資源，填入專屬的 Key/Endpoint；
    # 若留空，則自動沿用上方的 AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT
    AZURE_OPENAI_WHISPER_DEPLOYMENT: str = "whisper"
    AZURE_OPENAI_WHISPER_API_KEY: str = ""
    AZURE_OPENAI_WHISPER_ENDPOINT: str = ""
    AZURE_OPENAI_WHISPER_API_VERSION: str = ""  # 留空則沿用 AZURE_OPENAI_API_VERSION
    WHISPER_TIMEOUT: int = 600  # Whisper API 逾時秒數（預設 10 分鐘）

    @field_validator("PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"PORT must be between 1 and 65535, got {v}")
        return v

    @model_validator(mode="after")
    def warn_if_api_keys_empty(self) -> "Settings":
        import logging

        _logger = logging.getLogger(__name__)
        if not self.AZURE_OPENAI_API_KEY:
            _logger.warning("AZURE_OPENAI_API_KEY is not set. GPT analysis features will not work.")
        if not self.AZURE_OPENAI_ENDPOINT:
            _logger.warning(
                "AZURE_OPENAI_ENDPOINT is not set. GPT analysis features will not work."
            )
        return self

    @property
    def whisper_api_key(self) -> str:
        return self.AZURE_OPENAI_WHISPER_API_KEY or self.AZURE_OPENAI_API_KEY

    @property
    def whisper_endpoint(self) -> str:
        return self.AZURE_OPENAI_WHISPER_ENDPOINT or self.AZURE_OPENAI_ENDPOINT

    @property
    def whisper_api_version(self) -> str:
        return self.AZURE_OPENAI_WHISPER_API_VERSION or self.AZURE_OPENAI_API_VERSION

    # Worker 設定
    WORKER_CONCURRENCY: int = 1  # 同時處理任務數（避免 API 超頻）
    WORKER_POLL_INTERVAL: int = 5  # 輪詢間隔（秒）
    WORKER_TASK_DELAY: int = 2  # 任務間延遲（秒）
    WORKER_MAX_RETRIES: int = 3  # 最大重試次數
    WORKER_RETRY_DELAY: int = 30  # 重試延遲（秒）

    # 掃描支援的影片格式
    SUPPORTED_VIDEO_EXTENSIONS: list[str] = [
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".m4v",
        ".wmv",
        ".flv",
        ".webm",
        ".ts",
        ".mts",
    ]

    # 預設分類類別
    CATEGORIES: list[str] = [
        "占星學 (Astrology)",
        "風水 (Feng Shui)",
        "奇門遁甲 (Qimen Dunjia)",
        "東方玄學 (Eastern Metaphysics)",
        "實踐技巧 (Practical Techniques)",
        "案例分析 (Case Studies)",
        "綜合討論 (General Discussion)",
        "未分類 (Uncategorized)",
    ]

    # 影片來源目錄（對應 docker-compose.yml 的 VIDEO_DIR_1~5）
    # 未設定時預設為空字串，由 docker-compose 自動掛載 .docker-empty 佔位
    VIDEO_DIR_1: str = ""
    VIDEO_DIR_2: str = ""
    VIDEO_DIR_3: str = ""
    VIDEO_DIR_4: str = ""
    VIDEO_DIR_5: str = ""


settings = Settings()

# 確保必要的目錄存在
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.AUDIO_TEMP_DIR.mkdir(parents=True, exist_ok=True)
