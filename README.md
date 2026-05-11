# 🎬 Video Analyzer

本地影片批量分析系統，針對擁有大量影片（數百支）的使用場景設計。整合 OpenAI Whisper 語音轉文字與 Azure OpenAI GPT 進行深度內容分析，並提供完整的複習管理功能。

---

## 🖥️ 支援架構

| 平台 | 架構 | 支援狀態 |
|---|---|---|
| Mac Mini / MacBook (Apple Silicon M1/M2/M3) | `linux/arm64` | ✅ 原生支援 |
| Mac Intel | `linux/amd64` | ✅ 原生支援 |
| Linux x86_64 | `linux/amd64` | ✅ 原生支援 |
| Linux ARM64（AWS Graviton、Raspberry Pi 等） | `linux/arm64` | ✅ 原生支援 |

Docker image 為 **multi-arch manifest**，`docker pull` 時自動選擇符合本機 CPU 的版本，**無需手動指定架構**。

---

## 🐳 快速啟動（Docker，推薦）

不需安裝 Python、FFmpeg 等任何依賴，所有環境皆封裝在 container 中。支援 Apple Silicon 與 Intel 架構。

```bash
# 1. Clone 專案
git clone https://github.com/hwchiu/mochia.git
cd mochia

# 2. 填入 API Key
cp .env.example .env
nano .env   # 填入 AZURE_OPENAI_API_KEY、OPENAI_API_KEY

# 3. 設定影片目錄（支援最多 5 個來源）
# 在 .env 加入：
#   VIDEO_DIR_1=/Users/yourname/Movies
#   VIDEO_DIR_2=/Volumes/ExternalDrive/Videos   （外接硬碟，選填）
nano .env

# 4. 啟動（Docker 自動偵測並使用符合本機架構的 image）
docker compose up -d

# 5. 開啟瀏覽器
open http://localhost:8000

# 6. 掃描影片目錄（點選側欄「📁 掃描目錄」→ Modal 自動列出來源 → 點選掃描）
#    或用 CLI：
docker compose exec web python cli.py scan /videos/source1
```

### 日常操作

```bash
docker compose up -d           # 啟動
docker compose down            # 停止
docker compose logs -f web     # 查看 web 日誌
docker compose logs -f worker  # 查看 worker 日誌
bash update.sh                 # 升級到最新版本
```

---

## 📖 完整使用教學（Step-by-Step）

### 第一步：掃描影片目錄（登錄影片）

系統**不複製影片**，只記錄路徑。掃描後影片進入 `videos` 表，狀態為 `pending`。

**方式 A：網頁操作**

1. 開啟 `http://localhost:8000`
2. 點側欄左下角 **📁 掃描目錄** 按鈕
3. Modal 自動列出 `.env` 設定的 `VIDEO_DIR_1 ~ VIDEO_DIR_5` 來源
4. 點選來源旁的 **「掃描」** 按鈕
5. 掃描完成後，影片清單出現在「分析中心」

**方式 B：CLI 指令**

```bash
# Docker 部署
docker compose exec web python cli.py scan /videos/source1

# 本地開發
python cli.py scan /path/to/videos
```

---

### 第二步：加入分析佇列

掃描後影片狀態為 `pending`，需手動或批量加入佇列才會開始分析。

**方式 A：網頁操作**

1. 前往 **分析中心**（側欄「🔬 分析中心」）
2. 點選 **「🚀 全部加入佇列」** 一次處理所有待分析影片
3. 或點單支影片右側的 **「加入佇列」** 個別加入

**方式 B：CLI 指令**

```bash
# 掃描同時直接加入佇列（--queue 旗標）
docker compose exec web python cli.py scan /videos/source1 --queue

# 查看目前佇列狀態
docker compose exec web python cli.py status
```

---

### 第三步：Worker 自動處理（Pipeline 說明）

加入佇列後，背景 Worker 自動依序執行以下步驟，並即時更新 DB：

```
影片加入佇列
    │
    ▼
[Step 1] FFmpeg 提取音頻（MP3）
    │   寫入：videos.duration
    │
    ▼
[Step 2] Azure Whisper 語音轉文字
    │   寫入：transcripts.content（全文）
    │          transcripts.segments（時間戳 JSON：[{start, end, text}, ...]）
    │
    ▼
[Step 3] GPT 合併分析（摘要 + 分類 + FAQ）
    │   寫入：summaries.summary（摘要）
    │          summaries.key_points（重點 JSON）
    │          summaries.faq（FAQ JSON）
    │          classifications.category（分類名稱）
    │          classifications.confidence（信心值）
    │
    ▼
[Step 4] GPT 深度內容（學習筆記 + 案例分析）
    │   寫入：summaries.study_notes（學習筆記 Markdown）
    │          summaries.case_analysis（案例分析，含 [MM:SS] 時間戳）
    │
    ▼
[Step 5] 建立全文搜尋索引（FTS）
    │   寫入：video_fts（影片層：標題 + 摘要 + 逐字稿 + 重點）
    │          segment_fts（片段層：每句含 start_sec / end_sec）
    │
    ▼
[Step 6] 抽取知識點（M2）
        寫入：concepts（知識點名稱 + 描述）
               concept_relations（概念之間關係：related / prerequisite / part_of）
               segment_concepts（概念 → 影片 → 時間點，可追溯）
```

**監看進度：**

```bash
# 即時看 worker 日誌
docker compose logs -f worker

# 或在網頁「分析中心」看每支影片的進度條
```

---

### 第四步：查看分析結果（網頁操作）

分析完成後（狀態變為 `completed`），點擊任一影片進入**詳情頁**：

| Tab | 說明 |
|-----|------|
| 📝 **逐字稿** | 全文逐字稿，含時間戳，點擊任一段落跳轉播放器 |
| 📋 **摘要與重點** | GPT 摘要 + 條列式重點 |
| 🧠 **心智圖** | Markmap 互動式心智圖（縮放 / 拖曳 / 全螢幕 / 下載 PNG）|
| ❓ **FAQ** | 折疊式問答 |
| 📓 **學習筆記** | Markdown 格式學習筆記 |
| 🔍 **案例分析** | 含時間戳的案例分析 |
| 💡 **知識點** | 概念卡片，點時間戳一鍵跳轉播放器 |
| 💬 **對話** | 基於逐字稿的 GPT 問答 |
| 📌 **個人筆記** | Markdown 編輯器，個人筆記儲存 |

---

### 第五步：全文搜尋（片段跳轉）

1. 點側欄 **🔍 全文搜尋**
2. 輸入關鍵字（支援中文）
3. 結果分兩層：
   - **片段命中**：顯示逐字稿片段，含 `[MM:SS]` 時間戳
   - **影片層**：聚合命中片段所屬的影片
4. 點擊時間戳 → 自動跳轉到影片對應秒數播放

---

### 其他 CLI 指令

```bash
# 查看佇列狀態（每支影片的 status / step / 錯誤訊息）
docker compose exec web python cli.py status

# 重試所有失敗任務
docker compose exec web python cli.py retry

# 查看特定影片詳情
docker compose exec web python cli.py show <video_id>
```

---

### 斷點續跑說明

| 情況 | Worker 行為 |
|------|-------------|
| Worker 中途重啟 | 自動將中斷任務重設為 `pending`，重新處理 |
| 逐字稿已存在 | **跳過 Step 1–2**（省 Whisper API 費用），直接從 GPT 分析繼續 |
| 任務失敗 | 自動重試，最多 3 次（設定 `WORKER_MAX_RETRIES`）|

### 升級版本

```bash
bash update.sh
# 執行順序：
#   1. git pull --ff-only origin main  （拉取最新 docker-compose.yml 設定）
#   2. docker compose pull             （拉取最新 image hwchiu/mochia:latest）
#   3. docker compose up -d            （滾動重啟）
# 資料（SQLite、逐字稿）完整保留，不受影響
```

---

## 🔄 跨機器遷移

資料存放在 Docker named volumes，遷移時只需搬移 volumes 與設定檔，**不需複製整個專案資料夾**。

### 舊機器（備份）

```bash
# 備份 SQLite 資料庫
docker run --rm \
  -v mochia_mochia-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/mochia-data-backup.tar.gz -C /data .

# 備份上傳的附件（如有）
docker run --rm \
  -v mochia_mochia-uploads:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/mochia-uploads-backup.tar.gz -C /data .
```

### 新機器（還原）

```bash
# 1. Clone 專案並設定 .env
git clone https://github.com/hwchiu/mochia.git
cd mochia
cp .env.example .env && nano .env

# 2. 建立 volumes 並還原資料
docker compose up --no-start   # 建立 volumes（不啟動）

docker run --rm \
  -v mochia_mochia-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/mochia-data-backup.tar.gz -C /data

docker run --rm \
  -v mochia_mochia-uploads:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/mochia-uploads-backup.tar.gz -C /data

# 3. 啟動
docker compose up -d
```

> **影片檔案本身不在 volume 內**（系統只存路徑，不複製檔案），需確認新機器上影片路徑相同，或更新 `.env` 的 `VIDEO_DIR_1`~`VIDEO_DIR_5`。

---

## 🐍 Python 版本相容性

| Python 版本 | 支援狀態 | 測試方式 | 備註 |
|------------|---------|---------|------|
| 3.10 | ✅ 完整支援 | CI Docker | |
| 3.11 | ✅ 完整支援（推薦）| CI Docker | 主要開發版本 |
| 3.12 | ✅ 完整支援 | CI Docker | |
| 3.13 | ⚠️ 實驗性 | 未測試 | 部分套件尚無 wheel |
| 3.14 | ❌ 不支援 | 未測試 | 套件相容性問題 |
| 3.9 | ⚠️ 部分支援 | 未測試 | 需 `from __future__ import annotations` |
| < 3.9 | ❌ 不支援 | — | — |

> **推薦使用 Python 3.11**。或直接使用 Docker 部署，完全不需要考慮版本問題。

## 🐳 Docker 快速啟動（推薦）

最簡單的跨平台啟動方式，不需安裝 Python、FFmpeg 等依賴：

    # 1. 複製 env 設定
    cp .env.example .env
    # 編輯 .env，填入 Azure OpenAI API Key

    # 2. 設定影片目錄（支援最多 5 個來源）
    # 在 .env 加入 VIDEO_DIR_1, VIDEO_DIR_2 ... 最多 VIDEO_DIR_5
    echo 'VIDEO_DIR_1=/path/to/your/videos' >> .env

    # 3. 啟動
    docker compose up -d

    # 4. 開啟瀏覽器
    open http://localhost:8000

    # 5. 掃描影片（點選側欄「📁 掃描目錄」→ Modal 列出來源 → 點選掃描）
    #    或用 CLI：
    docker compose exec web python cli.py scan /videos/source1

---

## 📸 截圖

### 分析中心
管理影片分析任務，掌握佇列狀態

![分析中心](docs/screenshots/01-analysis-center.png)

### 複習中心
已完成影片的卡片式瀏覽，支援搜尋與標籤篩選

![複習中心](docs/screenshots/02-review-center.png)

### 全文搜尋
跨影片逐字稿全文搜尋

![全文搜尋](docs/screenshots/03-search.png)

### 學習統計
追蹤學習進度、複習量與信心分布

![學習統計](docs/screenshots/04-stats.png)

### 標籤管理
自訂標籤，12 色調色盤

![標籤管理](docs/screenshots/05-labels.png)

### 影片詳情
摘要、重點、心智圖、FAQ、對話

![影片詳情](docs/screenshots/06-video-detail.png)

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

> **推薦使用 Docker**，見上方「快速啟動」章節。以下為本地開發（不使用 Docker）的方式。

### 環境需求（本地開發）
- macOS
- Python 3.11+
- FFmpeg（`brew install ffmpeg`）
- Azure OpenAI API Key

### 首次設定

```bash
# 1. Clone 專案
git clone https://github.com/hwchiu/mochia.git
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
AZURE_OPENAI_API_VERSION=2024-02-01

# Azure OpenAI Whisper（語音轉文字）
# 若 Whisper 與 GPT 在同一個資源，下面兩行留空即可
AZURE_OPENAI_WHISPER_DEPLOYMENT=whisper
AZURE_OPENAI_WHISPER_API_KEY=      # 留空沿用上方 AZURE_OPENAI_API_KEY
AZURE_OPENAI_WHISPER_ENDPOINT=     # 留空沿用上方 AZURE_OPENAI_ENDPOINT

# 影片來源目錄（最多 5 個）
VIDEO_DIR_1=/path/to/your/videos
VIDEO_DIR_2=                       # 選填（外接硬碟等）
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
```

---

## 支援的影片格式

`.mp4` `.mkv` `.avi` `.mov` `.wmv` `.flv` `.webm` `.m4v`

---

## 資料庫

SQLite 位於 Docker volume `mochia_mochia-data`，包含：

| 資料表 | 說明 | 寫入時機 |
|--------|------|---------|
| `videos` | 影片清單（存路徑，不複製影片檔案） | 掃描目錄 / 上傳時 |
| `task_queue` | 分析任務佇列（Worker 持久化狀態） | 加入佇列時 |
| `transcripts` | 逐字稿全文（`content`）+ 時間戳片段（`segments` JSON） | Whisper 完成後 |
| `summaries` | 摘要、重點、FAQ、學習筆記、案例分析 | GPT Step 3 & Step 4 完成後 |
| `classifications` | 分類結果（`category` + `confidence`） | GPT Step 3 完成後 |
| `video_fts` | 影片層全文搜尋索引（FTS5 虛擬表） | 分析完成後自動建立 |
| `segment_fts` | 片段層全文搜尋索引（含時間戳，FTS5 虛擬表） | 分析完成後自動建立 |
| `concepts` | 知識點節點（名稱 + 描述） | M2 知識點抽取完成後 |
| `concept_relations` | 概念之間的關係邊（related / prerequisite / part_of）| M2 知識點抽取完成後 |
| `segment_concepts` | 概念 → 影片 → 時間點的追溯連結 | M2 知識點抽取完成後 |
| `labels` / `video_labels` | 使用者自訂標籤 | 使用者手動操作時 |
| `review_records` | 複習紀錄 | 使用者複習時 |
| `video_notes` | 個人筆記 | 使用者編輯筆記時 |
| `chat_messages` | 影片對話紀錄 | 使用者使用對話功能時 |
