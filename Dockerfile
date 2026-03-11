# ============================================================
#  Dockerfile — Video Analyzer
#  Python 3.11 + FFmpeg，同時用於 web server 和 worker
# ============================================================
FROM python:3.11-slim

# 系統依賴：FFmpeg（影片處理）+ 必要工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先複製 requirements，利用 Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY . .

# 建立必要目錄（volumes 掛載後仍會保留）
RUN mkdir -p data uploads logs data/audio_temp

# 預設啟動 web server（docker-compose 中 worker 會覆寫此指令）
CMD ["python", "main.py"]
