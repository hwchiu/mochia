# Agent-Specific Instructions for Video Analyzer

## 針對不同 Agent 的最佳實踐

### Explore Agent
當使用 explore agent 時，指定以下任務：
- 「探索 `app/` 目錄結構，理解當前的 API 端點和數據庫模型」
- 「檢查 `requirements.txt` 中的依賴版本，確保兼容性」
- 「找出所有使用 Azure OpenAI 的地方，了解配置需求」

### Task Agent
使用 task agent 進行自動化任務：
- 「運行 `pip install -r requirements.txt` 安裝依賴」
- 「執行 `python main.py` 啟動開發服務器」
- 「運行測試套件檢查代碼質量」

### Code-Review Agent
使用 code-review agent 檢查：
- API 端點的錯誤處理是否完整
- 數據庫查詢是否效率高
- 安全漏洞（如 SQL 注入、路徑遍歷）
- 類型註解的完整性

### General-Purpose Agent
使用 general-purpose agent 進行複雜任務：
- 「實現完整的音頻提取和轉錄流程」
- 「設計並實現分類引擎」
- 「構建前端 UI 並集成後端 API」

## 使用 Prompts 加速開發

### 快速添加新模塊
```
prompt: /new-module [module-name]
```
自動生成模塊骨架、測試文件和文檔。

### API 端點生成
```
prompt: /add-api [method] [path] [description]
```
快速生成標準 FastAPI 端點。

### 前端組件開發
```
prompt: /add-component [component-name] [type: form|display|list]
```
生成 HTML、CSS 和 JavaScript 組件。

## 常用命令速記

### 查看項目狀態
```bash
# 查看待辦任務
sql SELECT * FROM todos WHERE status != 'done';

# 查看項目結構
task: explore agent: 探索項目目錄結構
```

### 快速開發迭代
```bash
# 1. 修改代碼
# 2. 測試變更
# 3. 運行代碼審查
/review

# 4. Commit 並推送
/git commit -m "描述"
```

## 文件修改模板

### 添加新的 API 路由
1. 在 `app/routers/` 中創建或修改文件
2. 定義 Pydantic 模型（在 `app/models.py`）
3. 在主應用文件中註冊路由
4. 添加單元測試
5. 運行 `/review` 檢查代碼

### 實現新服務
1. 在 `app/services/` 中創建 service 類
2. 使用 async/await 進行異步操作
3. 添加適當的錯誤處理
4. 在路由中調用服務
5. 編寫測試確保功能正確

### 前端開發
1. 創建 HTML 模板（`templates/`）
2. 添加 CSS 樣式（`static/css/`）
3. 實現 JavaScript 邏輯（`static/js/`）
4. 使用 Fetch API 與後端通訊
5. 測試响应式設計和跨瀏覽器兼容性

## 代碼質量檢查清單

在提交前確保：
- [ ] 所有函數都有 type hints
- [ ] 所有公共方法都有 docstrings
- [ ] 錯誤處理完整（try-except, HTTPException）
- [ ] 數據庫查詢使用參數化避免注入
- [ ] 敏感信息不在代碼中硬編碼
- [ ] 異步函數使用 async/await
- [ ] API 端點有適當的 HTTP 狀態碼
- [ ] 前端代碼兼容現代瀏覽器

## 環境變量檢查

確保在本地開發前：
1. 複製 `.env.example`（如果存在）為 `.env`
2. 填入必要的 API 密鑰
3. 驗證 `config.py` 能正確讀取環境變量
4. **不要 commit `.env` 文件**

## Git 工作流

```bash
# 創建特性分支
git checkout -b feature/[feature-name]

# 定期提交
git commit -m "簡短描述"

# 推送前運行代碼審查
/review

# 推送並創建 PR（如適用）
git push origin feature/[feature-name]
```

## 常見問題快速解決

| 問題 | 解決方案 |
|------|--------|
| FFmpeg 找不到 | 安裝系統 FFmpeg：`brew install ffmpeg` |
| API 密鑰無效 | 檢查 `.env` 文件，確認密鑰正確 |
| 數據庫鎖定 | 刪除 `data/video_analyzer.db` 重建 |
| 導入錯誤 | 確保虛擬環境激活：`source venv/bin/activate` |
| 端口已佔用 | 修改 `config.py` 中的端口配置 |
