# GitHub Copilot Instructions for Video Analyzer

## 項目概述
本地影片分析系統，集成 Azure OpenAI 和 OpenAI Whisper，支持：
- 影片上傳和管理
- 自動語音轉文字（逐字稿）
- LLM 驅動的摘要和重點提取
- 占星、風水、奇門等領域的自動分類

## 技術棧
- **後端**: Python FastAPI
- **前端**: HTML/CSS/JavaScript
- **數據庫**: SQLite
- **LLM**: Azure OpenAI (GPT)
- **語音**: OpenAI Whisper API
- **影片處理**: FFmpeg

## 項目結構
```
video_analyzer/
├── app/
│   ├── __init__.py          # FastAPI 應用入口
│   ├── config.py            # 配置管理
│   ├── database.py          # SQLAlchemy 模型
│   ├── models.py            # Pydantic 模型
│   ├── routers/
│   │   ├── videos.py        # 影片 API
│   │   └── analysis.py      # 分析 API
│   └── services/
│       ├── audio_extractor.py      # FFmpeg 音頻提取
│       ├── transcriber.py          # Whisper 轉錄
│       └── analyzer.py             # LLM 分析
├── static/                  # 靜態文件
│   ├── css/
│   └── js/
├── templates/               # HTML 模板
├── uploads/                 # 已上傳的影片
├── data/                    # SQLite 數據庫
├── main.py                  # 應用入口點
├── requirements.txt         # Python 依賴
└── .env                     # 環境變量 (敏感信息)
```

## API 端點概覽

### 影片管理
- `POST /api/videos/upload` - 上傳影片
- `GET /api/videos/` - 列出所有影片
- `GET /api/videos/{video_id}` - 獲取影片詳情
- `DELETE /api/videos/{video_id}` - 刪除影片

### 分析操作
- `POST /api/analysis/{video_id}/analyze` - 啟動分析（異步）
- `GET /api/analysis/{video_id}/status` - 獲取分析進度
- `GET /api/analysis/{video_id}/results` - 獲取分析結果

## 環境變量配置

創建 `.env` 文件（**不要 commit**）：
```
# Azure OpenAI
AZURE_OPENAI_API_KEY=xxx
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-35-turbo

# OpenAI Whisper
OPENAI_API_KEY=xxx
```

## 預設分類類別

```python
[
    "占星學 (Astrology)",
    "風水 (Feng Shui)",
    "奇門遁甲 (Qimen Dunjia)",
    "東方玄學 (Eastern Metaphysics)",
    "實踐技巧 (Practical Techniques)",
    "案例分析 (Case Studies)",
    "綜合討論 (General Discussion)",
    "未分類 (Uncategorized)"
]
```

## 開發指南

### 添加新的 API 端點
1. 在 `app/routers/` 中創建新的路由文件
2. 使用 `APIRouter` 定義端點
3. 在 `app/__init__.py` 中注冊路由
4. 在 `app/models.py` 中定義 Pydantic 模型

### 添加新的後台任務
1. 在 `app/services/` 中創建服務類
2. 使用異步函數進行操作
3. 在路由中調用服務並更新數據庫

### 前端開發
1. HTML 模板放在 `templates/`
2. CSS 放在 `static/css/`
3. JavaScript 放在 `static/js/`
4. 使用 Fetch API 與後端通訊

## 運行項目

```bash
# 進入項目目錄
cd video_analyzer

# 激活虛擬環境
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 創建 .env 文件並配置 API 密鑰

# 運行服務器
python main.py
```

訪問：`http://localhost:8000`

## 常見 Agent 任務

### 1. 添加 API 端點
任務：「添加一個 GET `/api/categories` 端點，返回所有預設分類」

預期：
- 在 `app/routers/videos.py` 添加新端點
- 返回 JSON 格式的分類列表
- 包含分類 ID 和名稱

### 2. 實現文件處理
任務：「實現 `AudioExtractor` 類，使用 FFmpeg 從影片提取 MP3」

預期：
- 創建 `app/services/audio_extractor.py`
- 使用 `ffmpeg-python` 庫
- 返回提取的音頻文件路徑

### 3. 前端開發
任務：「創建上傳表單頁面，支持拖放和進度顯示」

預期：
- HTML 表單和拖放區
- JavaScript 用於文件上傳
- 進度條顯示
- 上傳完成後重定向到詳情頁

## 代碼風格

- 使用 **type hints** 註解所有函數
- 遵循 **PEP 8** 代碼風格
- 為所有 API 端點添加 **docstrings**
- 使用 **async/await** 進行異步操作
- 適當添加註釋，但代碼應該清晰自解釋

## 安全注意事項

- ✅ 驗證上傳的文件類型和大小
- ✅ 使用環境變量存儲敏感信息
- ✅ 實現身份驗證（當前為 localhost only）
- ✅ 驗證用戶輸入
- ✅ 限制並發上傳

## 測試

- 編寫單元測試以驗證服務函數
- 使用 pytest 進行測試
- 在 commit 前運行測試

## 常見問題解決

### FFmpeg 未安裝
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt-get install ffmpeg

# 驗證安裝
ffmpeg -version
```

### API 密鑰配置
確保 `.env` 文件在項目根目錄，不要 commit 此文件！

### 數據庫問題
如需重置數據庫，刪除 `data/video_analyzer.db` 文件，應用啟動時會自動重建。
