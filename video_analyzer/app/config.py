from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "Video Analyzer"
    APP_VERSION: str = "0.1.0"

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

    # OpenAI Whisper 配置
    OPENAI_API_KEY: str = ""
    WHISPER_MODEL: str = "whisper-1"

    # Worker 設定
    WORKER_CONCURRENCY: int = 1          # 同時處理任務數（避免 API 超頻）
    WORKER_POLL_INTERVAL: int = 5        # 輪詢間隔（秒）
    WORKER_TASK_DELAY: int = 2           # 任務間延遲（秒）
    WORKER_MAX_RETRIES: int = 3          # 最大重試次數
    WORKER_RETRY_DELAY: int = 30         # 重試延遲（秒）

    # 掃描支援的影片格式
    SUPPORTED_VIDEO_EXTENSIONS: List[str] = [
        ".mp4", ".mkv", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".webm", ".ts", ".mts"
    ]

    # 預設分類類別
    CATEGORIES: List[str] = [
        "占星學 (Astrology)",
        "風水 (Feng Shui)",
        "奇門遁甲 (Qimen Dunjia)",
        "東方玄學 (Eastern Metaphysics)",
        "實踐技巧 (Practical Techniques)",
        "案例分析 (Case Studies)",
        "綜合討論 (General Discussion)",
        "未分類 (Uncategorized)"
    ]

    class Config:
        env_file = ".env"

settings = Settings()

# 確保必要的目錄存在
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.AUDIO_TEMP_DIR.mkdir(parents=True, exist_ok=True)
