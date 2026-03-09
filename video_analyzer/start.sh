#!/bin/bash
# ============================================================
#  start.sh — 啟動 Video Analyzer（Web Server + Worker）
#  適用：macOS (開發 / 部署到 iMac)
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 虛擬環境
VENV="$SCRIPT_DIR/venv"
if [ ! -f "$VENV/bin/activate" ]; then
  echo "❌ 虛擬環境不存在，請先執行 setup.sh"
  exit 1
fi
source "$VENV/bin/activate"

# 確認 .env 存在
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "⚠ 找不到 .env 檔案，請複製 .env.example 並填入 API Key"
  echo "   cp .env.example .env && nano .env"
  exit 1
fi

mkdir -p "$SCRIPT_DIR/data" "$SCRIPT_DIR/logs"

PID_WEB="$SCRIPT_DIR/data/web.pid"
PID_WORKER="$SCRIPT_DIR/data/worker.pid"

# ── 停止舊進程 ──
if [ -f "$PID_WEB" ]; then
  OLD=$(cat "$PID_WEB")
  kill "$OLD" 2>/dev/null && echo "🛑 停止舊 Web Server (PID $OLD)" || true
  rm -f "$PID_WEB"
fi
if [ -f "$PID_WORKER" ]; then
  OLD=$(cat "$PID_WORKER")
  kill "$OLD" 2>/dev/null && echo "🛑 停止舊 Worker (PID $OLD)" || true
  rm -f "$PID_WORKER"
fi

sleep 1

# ── 啟動 Web Server ──
echo "🚀 啟動 Web Server..."
nohup python main.py > "$SCRIPT_DIR/logs/web.log" 2>&1 &
echo $! > "$PID_WEB"
echo "   Web Server PID: $(cat $PID_WEB)"
echo "   Log: logs/web.log"

sleep 2

# ── 啟動 Worker ──
echo "🚀 啟動 Worker..."
nohup python worker.py > "$SCRIPT_DIR/logs/worker.log" 2>&1 &
echo $! > "$PID_WORKER"
echo "   Worker PID: $(cat $PID_WORKER)"
echo "   Log: logs/worker.log"

sleep 1

# ── 確認啟動 ──
WEB_PID=$(cat "$PID_WEB")
WORKER_PID=$(cat "$PID_WORKER")

if kill -0 "$WEB_PID" 2>/dev/null; then
  echo "✅ Web Server 已啟動 → http://localhost:8000"
else
  echo "❌ Web Server 啟動失敗，請查看 logs/web.log"
fi

if kill -0 "$WORKER_PID" 2>/dev/null; then
  echo "✅ Worker 已啟動（背景執行，關閉終端機後繼續運作）"
else
  echo "❌ Worker 啟動失敗，請查看 logs/worker.log"
fi

echo ""
echo "停止服務：bash stop.sh"
echo "查看 Worker 日誌：tail -f logs/worker.log"
echo "掃描影片目錄：python cli.py scan /path/to/videos"
