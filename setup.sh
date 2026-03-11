#!/bin/bash
# ============================================================
#  setup.sh — 在新電腦（iMac）上首次安裝與設定
#
#  執行方式：bash setup.sh
# ============================================================
set -e

# 檢查 Python 版本
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
  echo "❌ Python $PYTHON_VERSION 不支援。需要 Python 3.10 或以上版本。"
  echo "   推薦使用 Python 3.11：https://www.python.org/downloads/"
  exit 1
elif [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 13 ]; then
  echo "⚠️  Python $PYTHON_VERSION 為實驗性支援，可能有套件相容性問題。"
  echo "   推薦使用 Python 3.11 或 3.12。繼續安裝中..."
else
  echo "✅ Python $PYTHON_VERSION — 支援"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Video Analyzer - 初始化設定"
echo "============================================"

# ── 1. 檢查 Python ──
if ! command -v python3 &>/dev/null; then
  echo "❌ 找不到 Python 3，請先安裝："
  echo "   brew install python"
  exit 1
fi
PY_VER=$(python3 --version 2>&1)
echo "✅ $PY_VER"

# ── 2. 檢查 FFmpeg ──
if ! command -v ffmpeg &>/dev/null; then
  echo ""
  echo "⚠ 找不到 FFmpeg，正在嘗試安裝..."
  if command -v brew &>/dev/null; then
    brew install ffmpeg
  else
    echo "❌ 請先安裝 Homebrew 或手動安裝 FFmpeg："
    echo "   https://ffmpeg.org/download.html"
    exit 1
  fi
fi
echo "✅ FFmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"

# ── 3. 建立虛擬環境 ──
if [ ! -d "$SCRIPT_DIR/venv" ]; then
  echo ""
  echo "📦 建立 Python 虛擬環境..."
  python3 -m venv venv
fi
source venv/bin/activate

# ── 4. 安裝依賴 ──
echo ""
echo "📦 安裝 Python 依賴..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ 依賴安裝完成"

# ── 5. 建立目錄 ──
mkdir -p uploads data logs data/audio_temp
echo "✅ 目錄建立完成"

# ── 6. 建立 .env ──
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  echo ""
  echo "📝 已建立 .env 檔案，請填入 API Key："
  echo "   nano .env"
  echo ""
  echo "需要設定的項目："
  echo "  - AZURE_OPENAI_API_KEY"
  echo "  - AZURE_OPENAI_ENDPOINT"
  echo "  - AZURE_OPENAI_DEPLOYMENT"
  echo "  - OPENAI_API_KEY"
else
  echo "✅ .env 已存在"
fi

# ── 7. 設定可執行權限 ──
chmod +x start.sh stop.sh

echo ""
echo "============================================"
echo "  設定完成！"
echo "============================================"
echo ""
echo "下一步："
echo "  1. 編輯 .env 填入 API Key：   nano .env"
echo "  2. 啟動服務：                  bash start.sh"
echo "  3. 掃描影片目錄：              python cli.py scan /path/to/videos"
echo "  4. 開啟瀏覽器：                http://localhost:8000"
