#!/usr/bin/env bash
# ============================================================
#  update.sh — 升級到最新版本
#
#  使用方式：bash update.sh
#  效果：
#    1. git pull — 拉取最新 docker-compose.yml 設定（含新環境變數、volume 等）
#    2. docker compose pull — 拉取最新 image（hwchiu/mochia:latest）
#    3. docker compose up -d — 滾動重啟
#  資料（SQLite、逐字稿）存在 Docker named volume，不受影響
# ============================================================
set -e

echo "📥 Pulling latest config from git..."
# 只更新非使用者自訂的檔案（.env、docker-compose.override.yml 不在 git 中，不受影響）
git pull --ff-only origin main || {
  echo "⚠️  git pull failed (local uncommitted changes?). Skipping git pull."
  echo "   若要強制更新設定檔，請先 git stash 後重試。"
}

echo "🔄 Pulling latest image from Docker Hub (hwchiu/mochia:latest)..."
docker compose pull

echo "🚀 Restarting services with new image..."
docker compose up -d

echo "✅ Update complete! Running versions:"
docker compose ps
