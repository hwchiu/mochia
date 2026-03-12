## 測試現況（基於 `pytest` 全套測試）

- **執行結果**：`pytest` 全部 **281** 個測試 **通過**，但出現 **663** 則警告（主要是 Pydantic/SQLAlchemy/FastAPI 的棄用警告與 `datetime.utcnow()` 使用）。
- **測試類型分佈**：
  - 單元 / 服務層：SM-2 間隔重複演算法、分析服務、搜尋、筆記、統計等。
  - 整合 / API：影片上傳、分析流程、搜尋、NotebookLM、複習、統計等 FastAPI 端點。
  - CLI：掃描、排程、狀態、重試、列表。
  - 資料庫：約束、關聯、級聯刪除、FTS5。
  - Worker：任務處理與恢復流程。
- **測試環境**：以 in-memory SQLite + `StaticPool` 共享連線，全面 mock 外部 GPT/Whisper/FFmpeg 交互。

## CI 管線的測試與檢查範圍（.github/workflows/ci.yml）

- **Lint**：`ruff check .` + `ruff format --check .`
- **型別**：`mypy app/ --ignore-missing-imports --no-error-summary`
- **安全**：`bandit -r app/ worker.py -c pyproject.toml`
- **單元/整合測試**：`pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=60`，於 Python 3.10/3.11/3.12 矩陣執行，並在 3.11 上上傳 coverage.xml。
- **Docker 整合測試**：以 `Dockerfile.test` 建置，環境注入虛擬 AZURE_OPENAI 參數後執行內含測試。
- **E2E 煙測**：以正式 `Dockerfile` 建置容器並啟動服務，執行 `smoke-test.sh`（HTTP 8000）。
- **發佈門檻**：`publish` job 僅在 main 分支 push 觸發，需全部 lint/type/security/test/docker/smoke 成功。
- **仍未涵蓋**：並發/負載/安全穿透測試、真實 GPT/Whisper/FFmpeg 整合、前端互動 UI、自動化遷移驗證。

---

## 做得好的地方

- **核心功能覆蓋完整**：影片生命週期、NotebookLM（Mindmap/FAQ/筆記/對話）、搜尋、複習統計、CLI 全部有測。
- **整合路徑有驗證**：API 端到端（排隊 → 轉錄 → 分析 → NotebookLM → 查詢）與 worker 恢復流程均有測。
- **資料品質與格式驗證**：舊/新 `key_points` 格式、Unicode/CJK、空值/缺值、Markdown 保留、FTS 重建。
- **邊界條件**：影片格式白名單、缺檔/錯誤檔案、重複掃描、限制筆數/分頁、超長筆記與截斷行為。
- **測試夾具設計完善**：多個狀態的影片、筆記、聊天紀錄、SM-2 狀態、假檔案等，便於快速組裝案例。

---

## 不足與風險（SDLC 視角）

1. **技術債警告**：大量棄用警告（Pydantic `config`、SQLAlchemy `declarative_base`、`datetime.utcnow()` 等）未解決，未來升級有破壞風險。
2. **真實整合不足**：GPT/Whisper/FFmpeg 全部 mock，缺少對雲端 API、媒體解碼失敗、網路異常的實際驗證。
3. **並發與韌性**：未驗證多任務併發、隊列鎖衝突、重試節流、長任務超時、半途失敗的補償行為。
4. **安全性測試缺位**：未涵蓋檔案路徑穿越/符號連結、超大檔/壓縮炸彈、SQL 注入、速率限制、(未來) 身份驗證/授權。
5. **效能與容量**：未有大型逐字稿/關鍵字/多影片批次的壓力或退化測試；FTS5 在大資料量與持久化 SQLite 的表現未知。
6. **資料遷移與相容性**：缺少 migration/schema 變更驗證；`datetime.utcnow()` 時區相容性與夏令時間行為未測。
7. **前端/模板**：僅 2 個頁面 smoke 測試，缺少模板變數完整性、XSS 輸出編碼與前端互動流程測試。

---

## 改進建議與優先順序

### 短期（1-2 週，快速穩定度提升）
- **修復棄用警告**：改用 `ConfigDict`、`sqlalchemy.orm.declarative_base()`、`datetime.now(timezone.utc)`；可同時清除測試噪音並降低升級風險。
- **新增負向案例**：影片路徑穿越/符號連結、超大檔案/格式錯誤、分析 API 4xx/5xx 重試、FTS rebuild 失敗處理。
- **最小實流測試**：以小型樣本啟動一次實際 ffmpeg 音訊擷取與 Whisper API（可用 sandbox key），驗證序列流程與錯誤訊息。
- **CI 報告**：在 CI 輸出 pytest warnings summary、測試覆蓋率（`pytest --cov`）並對警告採取 fail-on-warn 選項（逐步導入）。

### 中期（1-2 個月，韌性與安全）
- **併發與鎖測試**：模擬多工作執行緒/進程處理同一隊列、重複排程、長任務超時與補償；驗證任務狀態遷移不重複/不遺漏。
- **安全性測試**：檔案上傳大小/副檔名/內容型別驗證、路徑穿越、速率限制、(預期) API 金鑰/權限驗證；新增 SQL 注入與 XSS 輸出編碼測試。
- **資料持久化情境**：在真實 SQLite 檔案（非 in-memory）與較大資料集下的 FTS5、索引重建、清除/重建流程測試。
- **前端模板檢查**：對主要頁面進行模板渲染測試，確保必填變數存在、輸出有適當 escaping。

### 長期（>2 個月，產品成熟度）
- **契約與相容性**：為主要 API 定義 schema 契約（OpenAPI/JSON Schema），加入回溯相容性測試，避免破壞既有客戶端。
- **效能/負載**：逐字稿與搜尋在大資料量下的延遲與記憶體基準；排程與 worker 的吞吐量與重試成本評估。
- **混沌工程/韌性**：注入網路抖動、服務降級、資料庫鎖、磁碟寫入失敗等情境，驗證自動恢復與告警。
- **可觀測性驗證**：為關鍵路徑加入日誌/指標/追蹤的測試（例如：關鍵錯誤必須產生告警事件）。

---

## 結論
現有測試在核心功能與整合路徑上覆蓋度高，能有效防止主要回歸；但在 **升級兼容性（棄用警告）、實體外部依賴、並發韌性、安全性、效能** 等面向仍有明顯缺口。建議先處理棄用警告與高風險負向案例，再逐步導入併發、安全與效能測試，以符合 SDLC 各階段的品質門檻。
