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

# 版本資訊：由 CI 在 build 時注入 git SHA 與建置時間
# 本地直接 build 時預設顯示 "dev"
ARG GIT_SHA=dev
ARG BUILD_DATE=unknown
ENV APP_VERSION=${GIT_SHA}
ENV BUILD_DATE=${BUILD_DATE}

# 預設啟動 web server（docker-compose 中 worker 會覆寫此指令）
CMD ["python", "main.py"]
