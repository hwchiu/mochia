#!/usr/bin/env bash
# ============================================================
#  update.sh — 升級到最新版本
#
#  使用方式：bash update.sh
#  效果：拉取最新 image，滾動重啟（資料不會遺失）
# ============================================================
set -e

echo "🔄 Pulling latest images from Docker Hub..."
docker compose pull

echo "🚀 Restarting services with new images..."
docker compose up -d

echo "✅ Update complete! Running versions:"
docker compose ps
