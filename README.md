# 🎬 Video Analyzer

本地影片批量分析系統，針對擁有大量影片（數百支）的使用場景設計。整合 OpenAI Whisper 語音轉文字與 Azure OpenAI GPT 進行深度內容分析，並提供完整的複習管理功能。

---

## 功能特色

### 分析能力
- 🎙️ **自動逐字稿** — Whisper API 語音辨識，支援超長影片自動分段（>25MB）
- 🤖 **GPT 智能分析** — 自動生成摘要、條列式重點整理（依主題分類）、領域自動分類
- 🧠 **心智圖生成** — Markmap 互動式心智圖，支援縮放、拖曳、全螢幕、下載 PNG
- ❓ **FAQ 生成** — 自動產生影片內容問答
- 💬 **影片對話** — 基於逐字稿的 Q&A 對話

### 批量管理
- 📁 **目錄掃描** — macOS 原生資料夾選擇器，遞迴掃描所有支援格式（不複製檔案）
- ⚙️ **背景 Worker** — 獨立進程持續處理佇列，網頁關閉後繼續分析
- 🔄 **斷點續傳** — Worker 重啟自動恢復，重試時若逐字稿已存在可跳過 Whisper
- 📊 **即時進度** — 分步驟進度條（音頻提取 → Whisper → GPT → 生成摘要功能）

### 複習系統
- 🏷️ **自定義標籤** — 自由輸入標籤，GPT 自動建議，12 色調色盤
- 🔍 **標籤篩選** — 複習中心多選 AND 邏輯篩選，卡片式瀏覽
- 🔬 **分析中心** — 管理分析佇列、重試失敗任務
- 📚 **複習中心** — 已完成影片卡片瀏覽，搜尋與標籤篩選

---

## 系統架構

```
├── app/
│   ├── __init__.py          # FastAPI 應用入口
│   ├── config.py            # 環境設定
│   ├── database.py          # SQLAlchemy 模型（含自動 migration）
│   ├── routers/
│   │   ├── videos.py        # 影片 CRUD API
│   │   ├── analysis.py      # 分析 API（佇列、狀態、結果）
│   │   ├── batch.py         # 批量操作、目錄掃描
│   │   └── labels.py        # 標籤管理 API
│   └── services/
│       ├── audio_extractor.py   # FFmpeg 音頻提取
│       ├── transcriber.py       # Whisper 語音轉文字（含分段、心跳進度）
│       └── analyzer.py          # Azure OpenAI GPT 分析
├── static/                  # CSS / JavaScript
├── templates/               # HTML 頁面（index + detail）
├── tests/                   # pytest 測試（112 個）
├── worker.py                # 背景 Worker 進程
├── cli.py                   # CLI 工具
├── main.py                  # 啟動入口
├── setup.sh                 # 首次部署一鍵設定
├── start.sh                 # 啟動服務（app + worker）
└── stop.sh                  # 停止服務
```

---

## 快速開始

### 環境需求
- macOS（使用 osascript 原生資料夾選擇器）
- Python 3.11+
- FFmpeg（`brew install ffmpeg`）
- Azure OpenAI API Key（GPT + Whisper）

### 首次部署（含 iMac）

```bash
# 1. Clone 專案
git clone <repo-url>
cd mochia

# 2. 一鍵設定（建立 venv、安裝依賴、建立目錄）
bash setup.sh

# 3. 填入 API Key
cp .env.example .env
nano .env

# 4. 啟動服務
bash start.sh
```

訪問：`http://localhost:8000`

### 手動啟動

```bash
source venv/bin/activate

# 啟動 Web App
python main.py

# 另開終端，啟動 Worker
python worker.py
```

---

## 環境變數（.env）

```env
# Azure OpenAI（GPT 摘要分析）
AZURE_OPENAI_API_KEY=your_key
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o

# OpenAI Whisper（語音轉文字）
OPENAI_API_KEY=your_key

# 選填
DATA_DIR=./data
UPLOAD_DIR=./uploads
LOG_DIR=./logs
```

---

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/api/videos/` | 列出影片（支援狀態、來源、標籤篩選） |
| `POST` | `/api/batch/scan` | 掃描目錄登錄影片 |
| `GET` | `/api/batch/pick-directory` | macOS 原生資料夾選擇器 |
| `POST` | `/api/analysis/{id}/queue` | 加入分析佇列 |
| `GET` | `/api/analysis/{id}/status` | 取得分析進度 |
| `GET` | `/api/analysis/{id}/results` | 取得分析結果 |
| `POST` | `/api/analysis/{id}/reanalyze` | 重新 GPT 分析（保留逐字稿） |
| `POST` | `/api/analysis/{id}/suggest-labels` | GPT 建議標籤 |
| `GET` | `/api/labels/` | 列出所有標籤 |
| `POST` | `/api/labels/videos/{id}` | 為影片新增標籤 |

---

## CLI 工具

```bash
# 查看佇列狀態
python cli.py status

# 掃描目錄並加入佇列
python cli.py scan /path/to/videos --queue

# 重試失敗任務
python cli.py retry

# 查看特定影片詳情
python cli.py show <video_id>
```

---

## 開發

```bash
# 執行測試
venv/bin/python -m pytest tests/ -v

# 測試數量：112 個
```

---

## 支援的影片格式

`.mp4` `.mkv` `.avi` `.mov` `.wmv` `.flv` `.webm` `.m4v`


瀏覽器開啟 http://localhost:8000

## 日常使用

### 掃描影片目錄
```bash
# 透過 CLI
python cli.py scan /Volumes/MyDisk/Videos

# 或透過網頁右上角「掃描目錄」按鈕
```

### 啟動 / 停止服務
```bash
bash start.sh    # 啟動 Web Server + Worker
bash stop.sh     # 停止服務
```

### 查看狀態
```bash
python cli.py status
```

### CLI 完整指令
```
python cli.py scan <目錄>        掃描目錄登錄影片
python cli.py queue-all          全部加入分析佇列
python cli.py queue <video_id>   單支影片加入佇列
python cli.py status             顯示統計
python cli.py retry              重試失敗任務
python cli.py list [--status S]  列出影片
python cli.py worker             啟動 Worker
```

### 查看 Worker 日誌
```bash
tail -f logs/worker.log
```

## 專案結構

```
video_analyzer/
├── app/
│   ├── __init__.py          FastAPI 應用
│   ├── config.py            設定管理
│   ├── database.py          SQLAlchemy 模型
│   ├── routers/
│   │   ├── videos.py        影片管理 API
│   │   ├── analysis.py      分析狀態/結果 API
│   │   └── batch.py         批量操作 API
│   └── services/
│       ├── audio_extractor.py  FFmpeg 音頻提取
│       ├── transcriber.py      Whisper 轉錄
│       └── analyzer.py         GPT 分析
├── static/                  CSS / JS
├── templates/               HTML 頁面
├── uploads/                 上傳的影片
├── data/                    SQLite 資料庫 + 暫存音頻
├── logs/                    服務日誌
├── main.py                  Web Server 入口
├── worker.py                背景 Worker
├── cli.py                   CLI 工具
├── start.sh                 啟動腳本
├── stop.sh                  停止腳本
├── setup.sh                 首次安裝腳本
├── .env.example             環境變數範本
└── requirements.txt         Python 依賴
```

## 環境需求

- macOS（開發與部署）
- Python 3.10+
- FFmpeg（`brew install ffmpeg`）
- Azure OpenAI API
- OpenAI API（Whisper）

## 資料庫

SQLite 位於 `data/video_analyzer.db`，包含：
- `videos`：影片清單（支援本地路徑，不複製檔案）
- `transcripts`：逐字稿
- `summaries`：摘要與重點
- `classifications`：分類結果
- `task_queue`：分析任務佇列（Worker 持久化狀態）

## 跨機器遷移

只需複製整個 `video_analyzer/` 資料夾到新機器，執行 `bash setup.sh`，
重新設定 `.env` 中的 API Key，影片路徑需確認在新機器上存在。
