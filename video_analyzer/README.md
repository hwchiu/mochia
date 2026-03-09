# Video Analyzer

本地影片批量分析系統，整合 OpenAI Whisper（語音轉文字）和 Azure OpenAI GPT（摘要、分類）。

## 功能特色

- 🔍 **目錄掃描**：遞迴掃描本地目錄，登錄影片路徑（不複製檔案）
- ⚙️ **持久化 Worker**：獨立背景進程，網頁關閉後繼續分析
- 📊 **Web Dashboard**：即時進度監控、批量操作
- 🔄 **斷點續傳**：Worker 重啟後自動恢復未完成任務
- 🎙️ **自動逐字稿**：Whisper API 語音轉文字
- 🤖 **智能分析**：GPT 自動摘要、重點提取、玄學領域分類

## 快速開始（iMac 首次部署）

```bash
# 1. 克隆或複製專案到目標機器
# 2. 進入專案目錄
cd video_analyzer

# 3. 執行一鍵設定（安裝 Python 依賴、建立目錄、生成 .env）
bash setup.sh

# 4. 填入 API Key
nano .env

# 5. 啟動服務
bash start.sh
```

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
