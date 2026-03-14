# UI/UX Redesign Design Spec
**Date**: 2026-03-14  
**Scope**: Full visual + interaction redesign of Video Analyzer  
**Status**: Design — awaiting user approval before implementation

---

## 1. 問題診斷（現狀分析）

### 1.1 配色系統缺陷

| 問題 | 現狀 | 影響 |
|------|------|------|
| 顏色過於散亂 | 40+ 硬編碼 hex 值，無完整設計規範 | 維護困難，視覺不一致 |
| 主色調太跳 | `#4f46e5` 靛藍對知識型工具偏強烈 | 長期使用眼睛疲勞 |
| 無暗色模式 | 雖有 CSS 變數架構卻未實作 | 夜間工作體驗差 |
| key points 用 12 色 | 彩虹配色無規律 | 視覺噪音，難區分語義 |

### 1.2 排版系統缺陷

| 問題 | 現狀 | 影響 |
|------|------|------|
| 字型大小過多 | 14 個不同 px 值（10px–40px） | 無清晰層級感 |
| 使用系統字體 | `-apple-system` 在不同 OS 表現不同 | 跨平台一致性差 |
| 行高不統一 | 1.5–2.1 散落各處 | 閱讀節奏不穩定 |

### 1.3 圖示系統缺陷

| 問題 | 現狀 | 影響 |
|------|------|------|
| 純 emoji 圖示 | 100% unicode emoji | 無障礙問題，跨平台渲染差異大 |
| 無語義一致性 | 🔍 用在 tab 也用在按鈕 | 視覺語言混亂 |

### 1.4 互動模式缺陷

| 問題 | 現狀 | 影響 |
|------|------|------|
| 無載入骨架 | 空白頁直接出現內容 | 感知效能差 |
| 單一響應斷點 | 只有 700px | 平板體驗失當 |
| Sidebar 靜態 | 固定寬度，無法收合 | 小螢幕浪費空間 |
| Toast 缺乏層次 | 所有 type 視覺相同 | 錯誤與成功難以區分 |

---

## 2. 設計方向定位

### 2.1 目標風格：**知識型暗沉工具（Knowledge Dark Tool）**

參考對象：Linear、Raycast、Obsidian、Vercel Dashboard  
核心關鍵字：**克制、精準、沉穩、高效**

> 這不是一個社群媒體或行銷頁面，而是一個每天長時間使用的分析工具。  
> 色彩要退到背景，讓**內容本身**成為主角。

### 2.2 設計原則

1. **Content First** — 任何裝飾都不能比內容更搶眼
2. **Spatial Rhythm** — 一致的 8px 空間系統，讓排版有呼吸感
3. **Semantic Color** — 色彩只用來傳遞語義（成功/警告/錯誤），不用於裝飾
4. **Progressive Disclosure** — 次要資訊隱藏，需要時才出現
5. **Keyboard First** — 所有功能都可鍵盤操作

---

## 3. 新配色系統

### 3.1 設計決策

**放棄**：靛藍 `#4f46e5`（飽和度過高）  
**採用**：中性藍灰 `#2563EB`（Tailwind Blue-600，更收斂，更專業）  
**理由**：Blue-600 在明亮背景上的對比度符合 WCAG AA，視覺比 Indigo 更「清醒」

### 3.2 Light Mode 色板

```css
:root {
  /* ── Brand ─────────────────────────── */
  --color-brand-50:   #eff6ff;   /* 超淺藍，hover bg */
  --color-brand-100:  #dbeafe;   /* 淺藍，active bg */
  --color-brand-500:  #3b82f6;   /* 中藍，icon / link */
  --color-brand-600:  #2563eb;   /* 主色，primary button */
  --color-brand-700:  #1d4ed8;   /* 深藍，pressed state */

  /* ── Semantic ───────────────────────── */
  --color-success-bg: #f0fdf4;
  --color-success:    #16a34a;
  --color-warning-bg: #fffbeb;
  --color-warning:    #d97706;
  --color-danger-bg:  #fef2f2;
  --color-danger:     #dc2626;
  --color-info-bg:    #eff6ff;
  --color-info:       #2563eb;

  /* ── Neutrals ───────────────────────── */
  --color-gray-0:   #ffffff;
  --color-gray-25:  #fafafa;   /* page background */
  --color-gray-50:  #f5f5f5;   /* sidebar bg */
  --color-gray-100: #e5e5e5;   /* border light */
  --color-gray-200: #d4d4d4;   /* border */
  --color-gray-300: #a3a3a3;   /* placeholder text */
  --color-gray-500: #737373;   /* muted text */
  --color-gray-700: #404040;   /* secondary text */
  --color-gray-900: #171717;   /* primary text */

  /* ── Mapped Design Tokens ───────────── */
  --bg:       var(--color-gray-25);
  --surface:  var(--color-gray-0);
  --surface-2: var(--color-gray-50);
  --border:   var(--color-gray-200);
  --border-subtle: var(--color-gray-100);
  --text:     var(--color-gray-900);
  --text-secondary: var(--color-gray-700);
  --muted:    var(--color-gray-500);
  --placeholder: var(--color-gray-300);
  --primary:  var(--color-brand-600);
  --primary-hover: var(--color-brand-700);
  --focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.25);

  /* ── Layout ─────────────────────────── */
  --radius-sm:  4px;
  --radius:     8px;
  --radius-lg:  12px;
  --radius-xl:  16px;
  --shadow-xs:  0 1px 2px rgba(0,0,0,.05);
  --shadow-sm:  0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md:  0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.05);
  --shadow-lg:  0 10px 15px rgba(0,0,0,.1), 0 4px 6px rgba(0,0,0,.05);
  --sidebar-w:  240px;
  --sidebar-w-collapsed: 60px;
}
```

### 3.3 Dark Mode 色板

```css
[data-theme="dark"] {
  --bg:       #0a0a0a;
  --surface:  #141414;
  --surface-2: #1e1e1e;
  --border:   #2a2a2a;
  --border-subtle: #1f1f1f;
  --text:     #fafafa;
  --text-secondary: #a3a3a3;
  --muted:    #737373;
  --placeholder: #525252;
  --primary:  #3b82f6;
  --primary-hover: #2563eb;
  --focus-ring: 0 0 0 3px rgba(59, 130, 246, 0.35);

  /* Semantic dark variants */
  --color-success-bg: #052e16;
  --color-success:    #4ade80;
  --color-warning-bg: #451a03;
  --color-warning:    #fbbf24;
  --color-danger-bg:  #450a0a;
  --color-danger:     #f87171;
  --color-info-bg:    #0c1a2e;
  --color-info:       #60a5fa;
}
```

### 3.4 顏色使用規則

- **主色（Brand Blue）** → 只用於：主要按鈕、選中狀態、超連結、進度條
- **Neutral Gray** → 用於：背景、邊框、一般文字
- **Semantic** → 只用於傳達狀態：green=完成, amber=進行中, red=失敗, blue=資訊
- **禁止**：將色彩用作純裝飾用途（如彩虹 key points）

---

## 4. 新排版系統

### 4.1 字型選擇

**採用 Inter（Google Fonts CDN）**  
理由：
- 為螢幕閱讀優化設計，中等字重清晰度極高
- 數字等寬（tabular figures），表格對齊完美
- 全平台渲染一致
- 免費開源

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

```css
body { font-family: 'Inter', -apple-system, sans-serif; }
code, pre, .path { font-family: 'JetBrains Mono', 'Fira Code', monospace; }
```

### 4.2 型別層級（6階段）

| Token | Size | Weight | Line-height | 用途 |
|-------|------|--------|-------------|------|
| `--text-xs`   | 11px | 400/500 | 1.4 | badge, caption |
| `--text-sm`   | 12px | 400/500 | 1.5 | 表格欄位, metadata |
| `--text-base` | 14px | 400     | 1.6 | 主要內文 |
| `--text-md`   | 15px | 500/600 | 1.5 | 卡片標題, button |
| `--text-lg`   | 17px | 600/700 | 1.4 | 區段標題 |
| `--text-xl`   | 20px | 700     | 1.3 | 頁面標題 |

**從 14 個字型大小 → 6 個有語義的層級**

---

## 5. 圖示系統

### 5.1 從 Emoji 遷移到 SVG 圖示

**採用 Lucide Icons（MIT License）**  
理由：
- 輕量 SVG（每個 icon ~500 bytes）
- 風格統一（2px stroke，圓角端點）
- 無障礙友好（aria-hidden + title）
- 可用 CSS 控制顏色和大小

```html
<!-- 使用方式：內聯 SVG sprite 或 CDN -->
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<i data-lucide="play" class="icon"></i>
```

### 5.2 圖示對應表

| 現在（emoji） | 替換 | Lucide icon |
|-------------|------|------------|
| 🎬 | Video Analyzer logo | `clapperboard` |
| 🔬 | Analysis Center | `microscope` |
| 📚 | Review Center | `book-open` |
| 🔍 | Full-Text Search | `search` |
| 📊 | Stats | `bar-chart-2` |
| 🏷️ | Labels | `tag` |
| ▶ | Play | `play` |
| 🎵 | Audio Extract | `music` |
| 🎙️ | Speech-to-Text | `mic` |
| 🤖 | GPT Analysis | `cpu` |
| 📝 | Summary tab | `file-text` |
| 🧠 | Mindmap tab | `network` |
| ❓ | FAQ tab | `help-circle` |
| 🔍 | Case Analysis tab | `search` |
| 💬 | QA Chat tab | `message-circle` |
| 📓 | Notes tab | `notebook` |
| 📄 | Transcript tab | `scroll-text` |

---

## 6. 佈局與導航重設計

### 6.1 Sidebar 改為可收合

**現狀問題**：240px 固定 sidebar，小螢幕浪費空間  
**方案**：可收合 sidebar，收合後只顯示 icon（60px）

```
展開狀態（240px）       收合狀態（60px）
┌─────────────────┐    ┌────┐
│ 🎬 Video Analyzer│    │ 🎬 │
│ ≡               │    │ ≡  │
│ ┌─────────────┐ │    │ ── │
│ │🔬 Analysis  │ │    │ 🔬 │
│ │📚 Review    │ │    │ 📚 │
│ │🔍 Search    │ │    │ 🔍 │
│ │📊 Stats     │ │    │ 📊 │
│ │🏷️ Labels    │ │    │ 🏷️ │
│ └─────────────┘ │    │ ── │
│ ── Status ────  │    │    │
│ Total: 42       │    │    │
└─────────────────┘    └────┘
```

- 收合/展開按鈕（`⇤` / `⇥`）在 sidebar 頂端
- 狀態存 `localStorage`
- 收合時 sidebar item 只顯示 icon，hover 顯示 tooltip

### 6.2 響應式斷點系統

```css
/* 三個斷點 */
@media (max-width: 1100px) { /* 平板橫式：sidebar 收合 */ }
@media (max-width: 768px)  { /* 平板直式：sidebar 隱藏，hamburger 顯示 */ }
@media (max-width: 480px)  { /* 手機：全螢幕 */ }
```

### 6.3 Detail Page 佈局優化

```
┌─────────────────────────────────────────────────────┐
│  [← Back]  影片標題                [Queue][Review]  │  ← Header row
├───────────────────────────┬─────────────────────────┤
│  基本資訊 card             │  ┌──────────────────┐  │
│  標籤 card                │  │  VIDEO PLAYER    │  │  ← Sticky right
│  任務進度 card             │  │  [播放控制列]     │  │
│                           │  │  ⌨️ J K L M F   │  │
│                           │  └──────────────────┘  │
├───────────────────────────┴─────────────────────────┤
│  [Summary][Mindmap][FAQ][Cases][Chat][Notes][Script] │  ← Tab bar
├─────────────────────────────────────────────────────┤
│  Tab 內容區                                          │
└─────────────────────────────────────────────────────┘
```

---

## 7. 元件系統重設計

### 7.1 按鈕層級

```
Tier 1 - Primary     背景藍色，白色文字        →  主要行動（Queue, Analyze）
Tier 2 - Secondary   白色背景，藍色邊框文字    →  次要行動（Export, Copy）
Tier 3 - Ghost       透明背景，灰色文字        →  低優先行動（Cancel, Dismiss）
Tier 4 - Destructive 紅色背景或紅色文字        →  危險行動（Delete, Reset）
Tier 5 - Icon        圓形，只有圖示            →  工具列動作
```

### 7.2 Badge 改進

從 `PENDING` 全大寫 badge → 改為小字搭配顏色點（color dot）

```
現在：  ● PROCESSING（黃底全大寫）
改為：  ◉ 分析中（點 + 中文，柔和色調）
```

### 7.3 Card 改進

```
現在：  20px padding，1px border，8px radius
改為：  
  - 無邊框版：只用 shadow（去掉 border，用 shadow 區分層次）
  - 有邊框版：border-subtle（用更淡的邊框 #e5e5e5）
  - Hover 態：shadow 加深 + 輕微上移（translateY -1px）
  - 內部間距：統一 24px padding（更寬鬆）
```

### 7.4 Tab 改進

```
現在：  方形 tab，filled 背景表示選中
改為：  
  - 底線風格（underline tabs）
  - 選中：藍色底線 2px + 藍色文字
  - 未選：灰色文字，hover 深灰
  - 無背景填充，視覺更輕盈
```

### 7.5 進度條重設計

```
現在：  4 個 emoji step + connector line
改為：
  ① ──────── ② ──────── ③ ──────── ④
  音訊    語音轉文字    GPT分析    生成摘要
  ✓ 完成    ● 進行中    ○ 等待      ○ 等待
  
  - 數字圈圈（非 emoji）
  - Connector line 顏色跟隨狀態
  - 完成 = solid blue circle with checkmark
  - 進行中 = pulse animation blue ring
  - 等待 = gray empty circle
```

### 7.6 Toast 通知重設計

```
現在：  黑底白字，右上角，無分類視覺差異
改為：
  ✅ Success  綠色左邊線，白底，圖示 + 文字
  ❌ Error    紅色左邊線，白底，圖示 + 文字
  ⚠️ Warning  黃色左邊線，白底，圖示 + 文字
  ℹ Info     藍色左邊線，白底，圖示 + 文字
  
  位置：右上角，堆疊顯示（最多 5 條），slide-in-right 動畫
```

### 7.7 Skeleton Loader

各主要區域加入骨架載入：
- 影片列表 → 5 行灰色漸層骨架
- 分析結果（摘要/逐字稿等）→ 段落骨架
- Stats 數字 → 圓角矩形骨架

---

## 8. 逐字稿與時間軸體驗優化

### 8.1 逐字稿 Speaker-style 排版

```
現在：  [00:12] 文字內容一直串下去...
改為：
  ┌──────────────────────────────────────┐
  │  00:12  文字內容，清楚的換行，        │
  │         字型稍大 (15px)，行高 1.8    │
  │         ← 當前播放段落：左邊藍線 +   │
  │            淺藍背景                  │
  └──────────────────────────────────────┘
  
  [00:45]  下一個段落的文字...
```

- Timestamp badge 固定在左側（不在文字流中）
- 點擊任何段落直接跳轉
- 當前播放段落全段高亮（非僅 border-left）

### 8.2 案例分析時間戳記連結

```
現在：  [10:25] 描述文字（純文字或需點擊小 badge）
改為：  
  ◀ 10:25  描述文字
  
  - 藍色底線時間連結，hover 顯示 "跳到影片"
  - 點擊後同時：①影片 seek ②主頁面滾動到逐字稿對應位置
```

---

## 9. 暗色模式實作策略

### 9.1 切換機制

```javascript
// 系統偏好優先，可手動覆寫
function initTheme() {
  const saved = localStorage.getItem('theme');
  const preferred = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  setTheme(saved || preferred);
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('theme', theme);
}
```

### 9.2 切換按鈕位置

sidebar 底部 → 太陽 ☀ / 月亮 🌙 icon 按鈕

---

## 10. 動畫與互動改進

### 10.1 統一過渡時間

```css
:root {
  --transition-fast:   0.1s ease;
  --transition-base:   0.2s ease;
  --transition-slow:   0.35s ease;
}
```

### 10.2 新增互動動畫

| 元件 | 動畫 | 時長 |
|------|------|------|
| Card hover | shadow 加深 + translateY(-1px) | 0.15s |
| Button click | scale(0.97) | 0.1s |
| Tab 切換 | 內容 fade-in | 0.15s |
| Toast 出現 | slide-in-right | 0.2s |
| Toast 消失 | fade-out + slide-right | 0.2s |
| Modal 開啟 | scale(0.95→1) + fade | 0.2s |
| Sidebar 收合 | width transition | 0.25s |
| Skeleton | shimmer gradient animation | 1.5s loop |

---

## 11. 無障礙（Accessibility）改進

| 問題 | 修正 |
|------|------|
| Emoji icon 無 alt | 用 `aria-hidden="true"` + 文字 label |
| SVG icon 無標籤 | 加 `aria-label` 或 `<title>` |
| Focus ring 不明顯 | 全站統一 `--focus-ring` 藍色光暈 |
| 色彩對比不足 | 確保 `--muted` 文字在白底 WCAG AA ≥ 4.5:1 |
| 無 skip to main | 加 `<a href="#main" class="skip-link">` |

---

## 12. 實作優先順序

### Phase 1（高優先 — 視覺衝擊最大）
1. CSS 變數系統遷移（新色板 + 排版 token）
2. Inter 字型導入
3. Sidebar 可收合 + 圖示替換
4. Toast 分類視覺
5. Badge / Status 顯示優化

### Phase 2（中優先 — 使用體驗）
6. Dark mode 完整實作
7. Skeleton loaders
8. Card hover 動畫
9. Tab underline 風格
10. 進度條重設計

### Phase 3（低優先 — 精修）
11. 逐字稿排版優化
12. 按鈕層級系統
13. 響應式第二/第三斷點
14. Accessibility 修正

---

## 13. 技術決策摘要

| 決策 | 選擇 | 理由 |
|------|------|------|
| Icon library | Lucide Icons (CDN) | MIT, 統一風格, SVG, 0 build |
| Web font | Inter (Google Fonts) | 螢幕閱讀優化, 免費, 廣泛使用 |
| CSS framework | 繼續自定義 CSS | 現有架構完整，引入 Tailwind 成本太高 |
| Dark mode 切換 | `data-theme` attribute | 不需 JS-in-CSS，純 CSS 變數覆寫即可 |
| Animation | CSS transitions only | 不引入 GSAP/Framer，保持輕量 |
| Skeleton | CSS `@keyframes shimmer` | 不依賴第三方庫 |

---

## 14. 設計原則總結

```
Less Color → More Space → Better Hierarchy

現在：  40+ 顏色  ×  擁擠  ×  emoji 圖示
目標：  8 語義色  ×  8px 呼吸感  ×  SVG 圖示
```

這個設計方向的核心是：**減法設計**。  
不是加更多功能或更多顏色，而是把現有的元素整理得更清晰、更有層次。  
讓使用者每次打開工具時，眼睛不需要花力氣「找」東西，資訊自然流向視線。

---

*Spec reviewed and ready for implementation planning.*
