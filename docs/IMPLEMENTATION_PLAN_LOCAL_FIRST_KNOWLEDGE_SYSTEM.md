# Local-First 影片知識系統實作總計畫（Agent 協作版）

> 目的：作為後續所有 agent 的共同目標文件，確保多方協作時方向一致、切分清楚、交付可驗證。  
> 原則：**本地優先、少燒 token、時間戳可追溯、可持續增量擴充**。

---

## 0) 目標定義（Definition of Done）

### 核心能力
1. 所有影片可轉為「逐字稿 + 時間戳 segments」。
2. 使用者可透過關鍵字/主題找到**精確片段**並跳轉影片時間點。
3. 建立可複習的知識系統（主題關聯、題目、間隔複習）。

### KPI（持續追蹤）
- 搜尋命中可用片段時間 < 10 秒
- 搜尋結果可跳轉時間戳命中率 > 90%
- 每週複習完成率與答題正確率持續提升

---

## 1) 技術策略（Local-First + Token 控制）

### 本地優先（預設）
- ASR：faster-whisper / whisper.cpp（本地）
- Embedding：BGE 類模型（本地）
- Reranker：本地模型（可選）
- 佇列：本地 worker（現有 worker 流程延伸）

### 雲端 LLM 僅用於高價值任務
- 高品質摘要潤飾
- 複雜推理與題目語句改善
- 先本地規則過濾再送雲端，限制輸入長度與次數

### 成本控制
- 分段摘要（segment 級）
- 增量更新（只重算受影響資料）
- 快取分析結果
- 版本化重算（僅重跑變更模型或變更段落）

---

## 2) 資料庫選型與演進

### Phase A（現階段）
- SQLite + FTS5
- 先把功能閉環做完整（ ingestion / search / review ）

### Phase B（規模成長）
- PostgreSQL + pgvector + JSONB + GIN
- 保留相同 schema 概念，做平滑遷移

### 核心資料層（目標）
- `videos`：影片主檔、狀態、來源
- `transcripts`：全文、segments JSON（短期）或正規化 segments（中期）
- `transcript_segments`（中期正規化表）
- `concepts` / `concept_relations` / `segment_concepts`
- `quizzes` / `quiz_items` / `attempts`
- `reviews`（SM-2/FSRS 排程）

---

## 3) 全量舊影片流程（Backfill）

1. 掃描影片庫建索引  
2. 音訊提取與正規化  
3. 本地 ASR 產生 segments  
4. 段落清洗（合併/去贅詞）  
5. FTS + 向量索引  
6. 主題抽取、知識點與關係建模  
7. 摘要/重點/案例（必要時雲端）  
8. 題目生成（規則題優先，雲端潤飾可選）

### Backfill 要求
- 可重跑（idempotent）
- 可中斷續跑
- 每一步可回報狀態與錯誤碼

---

## 4) 新影片增量流程（持續營運）

`uploaded -> processing -> indexed -> analyzed -> review_ready -> failed`

Pipeline：
`ingest -> ASR -> segment index -> analysis -> quiz/review seed`

### 增量原則
- 只更新該影片關聯資料
- 分類體系變更時，背景重建，不阻塞前台
- 任務可重試、可追蹤、可取消

---

## 5) 知識框架與關係呈現

### 三層模型
1. 主題樹（課程/章節/主題）
2. 知識圖譜（concept node + relation edge）
3. 證據片段（segment + timestamp + 原文）

### 呈現原則
- 每個知識點都可追溯回原始片段
- 點知識點可看到：關聯影片、關聯片段、重點摘要、複習題

---

## 6) 搜尋體驗（How to Use）

### 搜尋模式
- 關鍵字搜尋（FTS）
- 語意搜尋（向量）
- 混合搜尋（FTS + 向量 + rerank）

### 結果呈現
- 先顯示「片段命中」（含 `[MM:SS]`）
- 再聚合到影片層
- 一鍵跳轉播放器到對應秒數

### 使用流程
輸入問題 -> 命中片段 -> 跳轉回看 -> 收藏/加入複習

---

## 7) 複習系統（題目 + 間隔重複）

### 題型
- 單選、是非、填空、簡答、情境題

### 出題來源
- segment + concept 作為可追溯依據
- 每題附原片段時間戳

### 排程
- SM-2（現況）或 FSRS（升級）
- 錯題優先、弱點主題加權

### 複習頁必要模組
- 今日待複習
- 錯題本
- 熟練度熱圖
- 題目回看原片段

---

## 8) UI/UX 藍圖（核心頁）

- Dashboard：進度/待複習/弱點/推薦
- Library：影片列表、狀態、分類、搜尋
- Video Detail：播放器、時間軸逐字稿、重點、關聯知識
- Knowledge Map：互動式知識圖譜
- Review Center：題目練習、錯題本、複習日曆
- Admin/Ops：佇列、重跑、模型切換、成本監控

---

## 9) 品質監控與風險控制

### 指標
- ASR：WER/CER（抽樣）
- 搜尋：NDCG / Recall@K
- 題目：正確率分布、鑑別度

### 主要風險與對策
- 專有名詞誤辨 -> 術語詞典 + 人工修正入口
- 概念抽取泛化 -> 人工審核 + 可回報機制
- 題目偏離原文 -> 強制附證據片段 + 回看鏈接

---

## 10) 分階段交付（Milestones）

### M1（最小可用，優先）
- ingestion
- timestamp segment 索引
- 片段搜尋 + 一鍵跳轉

### M2
- 知識點抽取
- 關係圖譜
- 混合搜尋

### M3
- 題庫與答題紀錄
- 間隔複習與學習儀表板

### M4
- 成本優化
- PostgreSQL/pgvector 遷移（必要時）

---

## 11) Agent 協作規範（務必遵守）

1. 先做 M1 關鍵路徑，再擴展 M2/M3。  
2. 每次任務都要標註「影響層」（ingest/search/review/ui/db）。  
3. 變更需附測試（至少覆蓋新增行為）。  
4. API 新欄位需向後相容。  
5. 若使用雲端 LLM，需說明為何不可本地化。  
6. 所有知識與題目輸出必須可追溯到 segment。

---

## 12) 目前優先工作（Current Focus）

- 以「時間戳片段為中心」完成 M1 閉環：
  - 影片 -> segments 入庫 -> FTS/向量索引 -> 片段命中 -> 一鍵跳轉
- M1 完成後再疊加知識圖譜與複習題系統。

