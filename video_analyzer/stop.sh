#!/bin/bash
# ============================================================
#  stop.sh — 停止 Video Analyzer
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_WEB="$SCRIPT_DIR/data/web.pid"
PID_WORKER="$SCRIPT_DIR/data/worker.pid"

if [ -f "$PID_WEB" ]; then
  PID=$(cat "$PID_WEB")
  if kill "$PID" 2>/dev/null; then
    echo "🛑 Web Server 已停止 (PID $PID)"
  else
    echo "⚠ Web Server 未在運行"
  fi
  rm -f "$PID_WEB"
else
  echo "⚠ 找不到 Web Server PID 檔案"
fi

if [ -f "$PID_WORKER" ]; then
  PID=$(cat "$PID_WORKER")
  if kill "$PID" 2>/dev/null; then
    echo "🛑 Worker 已停止 (PID $PID)（Worker 會完成當前任務後退出）"
  else
    echo "⚠ Worker 未在運行"
  fi
  rm -f "$PID_WORKER"
else
  echo "⚠ 找不到 Worker PID 檔案"
fi
