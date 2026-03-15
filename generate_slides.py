from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

# ── Theme ─────────────────────────────────────────────────────────────────────
BG_COLOR     = RGBColor(0x0D, 0x1B, 0x2A)   # deep navy background
ACCENT_BLUE  = RGBColor(0x00, 0xBF, 0xFF)   # electric blue
ACCENT_GREEN = RGBColor(0x39, 0xFF, 0x14)   # neon green
ACCENT_AMBER = RGBColor(0xFF, 0xBF, 0x00)   # amber
TEXT_PRIMARY = RGBColor(0xE8, 0xED, 0xF2)   # off-white
TEXT_DIM     = RGBColor(0x8F, 0xA3, 0xBF)   # dimmed subtext
CARD_BG      = RGBColor(0x1E, 0x2D, 0x3D)   # card background
CARD_BORDER  = RGBColor(0x00, 0x5F, 0x8A)   # card border

FONT_TITLE = "JetBrains Mono"
FONT_BODY  = "Inter"
SLIDE_W    = Inches(13.33)
SLIDE_H    = Inches(7.5)

PART_COLORS = {
    1: ACCENT_BLUE,
    2: RGBColor(0x7B, 0x2F, 0xFF),
    3: RGBColor(0x00, 0xE5, 0xFF),
    4: RGBColor(0xFF, 0x6B, 0x35),
    5: ACCENT_GREEN,
    6: ACCENT_AMBER,
}


def new_slide(prs, layout_idx=6):
    """Add blank slide and paint background."""
    layout = prs.slide_layouts[layout_idx]
    slide = prs.slides.add_slide(layout)
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = BG_COLOR
    return slide


def add_rect(slide, l, t, w, h, fill_color, border_color=None, border_width=Pt(1)):
    """Add a filled rectangle shape. MSO_SHAPE_TYPE 1 = rectangle."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    shape = slide.shapes.add_shape(1, l, t, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = border_width
    else:
        shape.line.fill.background()
    return shape


def add_text(slide, text, l, t, w, h, font_name=FONT_BODY, font_size=Pt(14),
             color=TEXT_PRIMARY, bold=False, align=PP_ALIGN.LEFT, italic=False):
    """Add a text box with a single paragraph."""
    txBox = slide.shapes.add_textbox(l, t, w, h)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = font_size
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    return txBox


def add_multiline_text(slide, lines, l, t, w, h, font_name=FONT_BODY,
                       font_size=Pt(13), color=TEXT_PRIMARY):
    """Add a textbox with multiple paragraphs.
    lines: list of (text, opts_dict) where opts can have: align, font, size, color, bold, italic
    """
    txBox = slide.shapes.add_textbox(l, t, w, h)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, (text, opts) in enumerate(lines):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.alignment = opts.get("align", PP_ALIGN.LEFT)
        run = p.add_run()
        run.text = text
        run.font.name = opts.get("font", font_name)
        run.font.size = opts.get("size", font_size)
        run.font.color.rgb = opts.get("color", color)
        run.font.bold = opts.get("bold", False)
        run.font.italic = opts.get("italic", False)
    return txBox


def add_part_label(slide, part_num, part_title):
    """Top-left Part badge with colored background."""
    color = PART_COLORS.get(part_num, ACCENT_BLUE)
    add_rect(slide, Inches(0.3), Inches(0.15), Inches(1.5), Inches(0.32), color)
    add_text(slide, f"PART {part_num}", Inches(0.3), Inches(0.15), Inches(1.5), Inches(0.32),
             font_name=FONT_TITLE, font_size=Pt(9),
             color=RGBColor(0x0D, 0x1B, 0x2A), bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, part_title, Inches(1.9), Inches(0.18), Inches(8), Inches(0.28),
             font_name=FONT_BODY, font_size=Pt(9), color=TEXT_DIM)


def add_page_number(slide, num):
    """Bottom-right page number."""
    add_text(slide, f"{num:02d} / 50", Inches(12.0), Inches(7.1), Inches(1.1), Inches(0.28),
             font_size=Pt(9), color=TEXT_DIM, align=PP_ALIGN.RIGHT)


def add_slide_title(slide, title, subtitle=None):
    """Standard slide title with blue underline rule."""
    add_text(slide, title, Inches(0.5), Inches(0.55), Inches(12.3), Inches(0.7),
             font_name=FONT_TITLE, font_size=Pt(26), color=ACCENT_BLUE, bold=True)
    add_rect(slide, Inches(0.5), Inches(1.25), Inches(12.3), Inches(0.025), ACCENT_BLUE)
    if subtitle:
        add_text(slide, subtitle, Inches(0.5), Inches(1.3), Inches(10), Inches(0.35),
                 font_size=Pt(12), color=TEXT_DIM)


def add_card(slide, l, t, w, h, title=None, body_lines=None, accent=ACCENT_BLUE):
    """Dark card with colored border and optional title bar + body lines."""
    add_rect(slide, l, t, w, h, CARD_BG, accent, Pt(1.5))
    y_offset = t
    if title:
        add_rect(slide, l, t, w, Inches(0.35), accent)
        add_text(slide, title, l + Inches(0.1), t + Inches(0.03),
                 w - Inches(0.2), Inches(0.3),
                 font_name=FONT_TITLE, font_size=Pt(10),
                 color=RGBColor(0x0D, 0x1B, 0x2A), bold=True)
        y_offset = t + Inches(0.42)
    else:
        y_offset = t + Inches(0.1)

    if body_lines:
        y = y_offset
        for line in body_lines:
            add_text(slide, line, l + Inches(0.12), y,
                     w - Inches(0.24), Inches(0.28),
                     font_size=Pt(11), color=TEXT_PRIMARY)
            y += Inches(0.3)


def add_callout(slide, text, l, t, w, h, style="tip"):
    """Callout box. style: 'tip' (green), 'warning' (amber), 'danger' (red)."""
    configs = {
        "tip":     (RGBColor(0x00, 0x1A, 0x0A), ACCENT_GREEN),
        "warning": (RGBColor(0x1A, 0x10, 0x00), ACCENT_AMBER),
        "danger":  (RGBColor(0x1A, 0x00, 0x00), RGBColor(0xFF, 0x4A, 0x4A)),
    }
    bg_c, border_c = configs.get(style, configs["tip"])
    add_rect(slide, l, t, w, h, bg_c, border_c, Pt(1.5))
    prefix = {"tip": "💡  ", "warning": "⚠   ", "danger": "❌  "}.get(style, "")
    add_text(slide, prefix + text, l + Inches(0.12), t + Inches(0.08),
             w - Inches(0.24), h - Inches(0.16),
             font_size=Pt(12), color=TEXT_PRIMARY)


def slide_01_cover(prs):
    slide = new_slide(prs)

    # Full-width top accent line
    add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.06), ACCENT_BLUE)

    # Decorative vertical accent bar on left
    add_rect(slide, Inches(0), Inches(0.06), Inches(0.06), SLIDE_H - Inches(0.06), ACCENT_BLUE)

    # Background grid pattern (subtle horizontal lines)
    for i in range(8):
        y = Inches(1.0 + i * 0.8)
        add_rect(slide, Inches(0.3), y, SLIDE_W - Inches(0.3), Inches(0.005),
                 RGBColor(0x1E, 0x2D, 0x3D))

    # Main title: CLOUD NATIVE
    add_text(slide, "CLOUD NATIVE", Inches(1.2), Inches(1.5), Inches(11), Inches(1.4),
             font_name=FONT_TITLE, font_size=Pt(64), color=ACCENT_BLUE, bold=True,
             align=PP_ALIGN.LEFT)

    # Subtitle
    add_text(slide, "系統部署實務", Inches(1.2), Inches(2.9), Inches(10), Inches(0.85),
             font_name=FONT_TITLE, font_size=Pt(36), color=TEXT_PRIMARY, bold=False,
             align=PP_ALIGN.LEFT)

    # Underline rule
    add_rect(slide, Inches(1.2), Inches(3.8), Inches(10), Inches(0.04), ACCENT_BLUE)

    # Tagline
    add_text(slide, "從單體部署到 Cloud Native 的完整演進之路",
             Inches(1.2), Inches(3.9), Inches(10), Inches(0.45),
             font_size=Pt(16), color=TEXT_DIM, align=PP_ALIGN.LEFT)

    # Bottom info bar background
    add_rect(slide, Inches(0), Inches(6.5), SLIDE_W, Inches(1.0), CARD_BG)

    # Bottom left: course info
    add_text(slide, "碩士課程  ·  系統架構設計",
             Inches(0.5), Inches(6.62), Inches(6), Inches(0.35),
             font_size=Pt(13), color=TEXT_DIM)

    # Bottom right: stats
    add_text(slide, "預計課程時間：2.5 小時  ·  投影片：50 頁",
             Inches(7.0), Inches(6.62), Inches(6.0), Inches(0.35),
             font_size=Pt(13), color=TEXT_DIM, align=PP_ALIGN.RIGHT)

    # Small decorative dot cluster (top right)
    for row in range(4):
        for col in range(4):
            x = Inches(11.5) + col * Inches(0.22)
            y = Inches(1.0) + row * Inches(0.22)
            sz = Inches(0.08)
            add_rect(slide, x, y, sz, sz, CARD_BORDER)

    return slide


def slide_02_agenda(prs):
    slide = new_slide(prs)

    # Title
    add_slide_title(slide, "課程大綱", "Agenda — 完整演進之路")
    add_page_number(slide, 2)

    # 6 Part cards in 2 rows × 3 columns
    parts = [
        (1, "PART 1", "傳統部署演進",    "單機 → 三層架構，了解部署的起點"),
        (2, "PART 2", "Scale Out 挑戰",  "LB / Session / DB 擴展的真實難題"),
        (3, "PART 3", "Container 革命",  "Docker / Compose / Registry"),
        (4, "PART 4", "12-Factor App",   "Cloud-Ready 應用的設計原則"),
        (5, "PART 5", "DevOps 整合",     "大規模生產環境的團隊協作"),
        (6, "PART 6", "SDLC 閉環",       "從 Code 到維運的完整旅程"),
    ]

    card_w = Inches(4.0)
    card_h = Inches(1.9)
    x_starts = [Inches(0.4), Inches(4.6), Inches(8.8)]
    y_starts  = [Inches(1.55), Inches(3.65)]

    for i, (part_num, label, title, desc) in enumerate(parts):
        col = i % 3
        row = i // 3
        x = x_starts[col]
        y = y_starts[row]
        color = PART_COLORS[part_num]

        # Card background
        add_rect(slide, x, y, card_w, card_h, CARD_BG, color, Pt(1.5))

        # Top colored header strip
        add_rect(slide, x, y, card_w, Inches(0.4), color)

        # Part label in header
        add_text(slide, label, x + Inches(0.1), y + Inches(0.05),
                 card_w - Inches(0.2), Inches(0.32),
                 font_name=FONT_TITLE, font_size=Pt(11),
                 color=RGBColor(0x0D, 0x1B, 0x2A), bold=True)

        # Title
        add_text(slide, title, x + Inches(0.12), y + Inches(0.46),
                 card_w - Inches(0.24), Inches(0.4),
                 font_name=FONT_TITLE, font_size=Pt(14),
                 color=TEXT_PRIMARY, bold=True)

        # Description
        add_text(slide, desc, x + Inches(0.12), y + Inches(0.92),
                 card_w - Inches(0.24), Inches(0.85),
                 font_size=Pt(11), color=TEXT_DIM)

    # Bottom note
    add_text(slide, "課程目標：理解真實世界如何從零設計可擴展系統，體會各種設計決策背後的取捨",
             Inches(0.4), Inches(5.7), Inches(12.5), Inches(0.4),
             font_size=Pt(11), color=TEXT_DIM, align=PP_ALIGN.CENTER)

    return slide


def slide_03(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "起點：最簡單的部署架構")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 3)

    # Left side: Architecture diagram
    add_card(slide, Inches(0.5), Inches(1.8), Inches(5.5), Inches(0.7),
             title="使用者 Browser", accent=ACCENT_BLUE)
    add_text(slide, "→", Inches(0.5), Inches(2.55), Inches(5.5), Inches(0.4),
             font_size=Pt(22), color=TEXT_DIM, align=PP_ALIGN.CENTER, bold=True)
    add_card(slide, Inches(0.5), Inches(3.0), Inches(5.5), Inches(0.9),
             title="Linux Server :8080 (my-app)", accent=ACCENT_BLUE)

    # Right side: Two cards stacked
    add_card(slide, Inches(6.5), Inches(1.8), Inches(6.3), Inches(1.5),
             title="✅ 優點", accent=ACCENT_GREEN,
             body_lines=["設定簡單、維運容易", "適合初期開發與 PoC 驗證", "開發環境 ≈ 生產環境"])
    add_card(slide, Inches(6.5), Inches(3.5), Inches(6.3), Inches(1.5),
             title="⚠  問題", accent=ACCENT_AMBER,
             body_lines=["單點故障 (SPOF)", "無法應付高流量", "資料存記憶體 → 重啟即遺失"])

    # Callout tip
    add_callout(slide, "課堂 PoC 常用這種架構，但真實產品幾乎不會停在這裡",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="tip")
    return slide


def slide_04(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "請求的旅程：一個 HTTP Request 經歷什麼？")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 4)

    steps = [
        ("① DNS 解析", "查詢域名 → 取得 Server IP"),
        ("② TCP 握手", "三次握手 → 建立可靠連線"),
        ("③ HTTP Request", "GET /api/data → 發送請求"),
        ("④ App 處理", "業務邏輯 → 查 DB / 計算"),
        ("⑤ DB Query", "執行 SQL → 取得資料"),
        ("⑥ HTTP Response", "JSON 回傳 → Client 收到"),
    ]

    x_positions = [Inches(0.4), Inches(6.9)]
    y_start = Inches(1.6)
    y_spacing = Inches(1.7)

    for i, (title, desc) in enumerate(steps):
        col = i % 2
        row = i // 2
        x = x_positions[col]
        y = y_start + row * y_spacing
        add_card(slide, x, y, Inches(5.8), Inches(1.4),
                 title=title, body_lines=[desc], accent=ACCENT_BLUE)

    add_callout(slide, "理解這條路徑，才知道瓶頸藏在哪一層",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="tip")
    return slide


def slide_05(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "第一步擴展：分離資料庫 Server")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 5)

    # Left side: Architecture diagram
    add_card(slide, Inches(0.5), Inches(2.0), Inches(5.5), Inches(0.9),
             title="App Server  (my-app :8080)", accent=ACCENT_BLUE)
    add_text(slide, "→ SQL →", Inches(0.5), Inches(2.95), Inches(5.5), Inches(0.4),
             font_size=Pt(16), color=TEXT_DIM, align=PP_ALIGN.CENTER, bold=True)
    add_card(slide, Inches(0.5), Inches(3.3), Inches(5.5), Inches(0.9),
             title="DB Server  (PostgreSQL :5432)", accent=PART_COLORS[4])

    # Right side
    add_card(slide, Inches(6.5), Inches(2.0), Inches(6.3), Inches(1.7),
             title="為什麼要把 DB 獨立出來？",
             body_lines=[
                 "① App Server 可以無狀態重啟，不影響資料",
                 "② DB 資源需求不同，可以獨立調整規格",
                 "③ 資料可以被多個 App 共用",
             ],
             accent=ACCENT_BLUE)

    add_callout(slide, "新問題：網路連線延遲增加、DB 成為效能瓶頸、兩台機器各別維護",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="warning")
    return slide


def slide_06(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "三層架構：Frontend + Backend + Database")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 6)

    tiers = [
        (Inches(0.4),  PART_COLORS[3], "Presentation Tier",
         ["Frontend Server", "React / Vue", "Nginx : 80", "", "職責：UI 呈現、", "靜態資源服務"]),
        (Inches(4.7),  ACCENT_BLUE,    "Application Tier",
         ["Backend Server", "FastAPI / Node.js", ": 8080", "", "職責：業務邏輯、", "API 處理"]),
        (Inches(9.0),  PART_COLORS[4], "Data Tier",
         ["Database Server", "PostgreSQL", ": 5432", "", "職責：資料持久化、", "查詢處理"]),
    ]

    for x, accent, title, body in tiers:
        add_card(slide, x, Inches(1.6), Inches(3.8), Inches(3.8),
                 title=title, body_lines=body, accent=accent)

    # Arrows between cards
    add_text(slide, "→", Inches(4.2), Inches(3.0), Inches(0.5), Inches(0.5),
             font_size=Pt(22), color=TEXT_DIM, align=PP_ALIGN.CENTER, bold=True)
    add_text(slide, "→", Inches(8.5), Inches(3.0), Inches(0.5), Inches(0.5),
             font_size=Pt(22), color=TEXT_DIM, align=PP_ALIGN.CENTER, bold=True)

    add_callout(slide, "3 台機器 = 3 倍維運工作量，且任何一台掛掉都影響整個服務",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="warning")
    return slide


def slide_07(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "三層架構的真實挑戰")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 7)

    danger_color = RGBColor(0xFF, 0x4A, 0x4A)
    cards = [
        (Inches(0.4), Inches(1.6), "① 部署順序地雷",
         ["前後端必須依序更新", "Frontend v2 + Backend v1 = API 不相容", "任一步驟失敗，整體需回滾"]),
        (Inches(6.9), Inches(1.6), "② 版本相依性地獄",
         ["Frontend 假設 API 回傳格式", "Backend 改動 response 結構", "雙方沒有明確合約 → 上線即爆炸"]),
        (Inches(0.4), Inches(3.8), "③ 開發環境差異",
         ["本地 macOS → 測試 Ubuntu 20 → 生產 Ubuntu 22", "套件版本不同 → 行為不一致", "「我這裡跑得好好的...」"]),
        (Inches(6.9), Inches(3.8), "④ 單點故障",
         ["任何一層掛掉 → 整個服務中斷", "Frontend 掛 → 用戶看不到頁面", "DB 掛 → 全站 500 Error"]),
    ]

    for x, y, title, body in cards:
        add_card(slide, x, y, Inches(5.8), Inches(2.0),
                 title=title, body_lines=body, accent=danger_color)

    add_callout(slide, "這些問題在小團隊可以忍受，但隨著規模成長會爆炸",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="warning")
    return slide


def slide_08(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "如何找出系統瓶頸？")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 8)

    bottlenecks = [
        ("CPU 瓶頸",      "症狀: top/htop CPU 100%  |  工具: perf, flame graph"),
        ("Memory 瓶頸",   "症狀: OOM Kill, Swap 滿  |  工具: free, valgrind"),
        ("Disk I/O 瓶頸", "症狀: iowait 高, 寫入慢  |  工具: iostat, iotop"),
        ("Network 瓶頸",  "症狀: 封包遺失, 延遲高  |  工具: netstat, tcpdump"),
        ("DB Query 瓶頸", "症狀: 慢查詢, Lock 等待  |  工具: EXPLAIN ANALYZE"),
    ]

    y = Inches(1.6)
    for title, desc in bottlenecks:
        add_card(slide, Inches(0.4), y, Inches(7.5), Inches(0.85),
                 title=title, body_lines=[desc], accent=ACCENT_BLUE)
        y += Inches(0.9)

    # Right card
    add_card(slide, Inches(8.2), Inches(1.6), Inches(4.8), Inches(4.5),
             title="解讀監控訊號",
             body_lines=[
                 "P50 / P95 / P99 Latency",
                 "Request per Second (RPS)",
                 "Error Rate (%)",
                 "CPU / Memory 使用率",
                 "DB Connection Pool 使用量",
             ],
             accent=ACCENT_BLUE)

    add_callout(slide, "先量測，再優化。不要猜，要看數據。沒有監控就沒有優化的依據",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="tip")
    return slide


def slide_09(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "何時需要開始思考 Scale？")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 9)

    indicators = [
        (Inches(0.4), RGBColor(0xFF, 0x4A, 0x4A), "CPU 持續 > 70%",
         ["計算資源不足", "壓力測試時先觸頂", "Scale Up 或 Scale Out", "加 Cache 降低計算量"]),
        (Inches(4.6), ACCENT_AMBER, "Response P99 > 1s",
         ["用戶體驗明顯下降", "長尾延遲影響轉換率", "查慢查詢 / 優化邏輯", "若已優化 → 需 Scale"]),
        (Inches(8.8), ACCENT_BLUE, "Error Rate > 0.1%",
         ["服務不穩定訊號", "可能是 OOM / DB 連線耗盡", "先找根因，再決定是否 Scale"]),
    ]

    for x, accent, title, body in indicators:
        add_card(slide, x, Inches(1.6), Inches(3.9), Inches(2.8),
                 title=title, body_lines=body, accent=accent)

    add_card(slide, Inches(0.4), Inches(4.65), Inches(12.5), Inches(1.3),
             title="常見錯誤：過早 Scale",
             body_lines=[
                 "需求還沒穩定就急著上 K8s",
                 "單機能搞定的問題別引入分散式複雜度",
                 "先用單機撐到真正需要的時候再 Scale",
             ],
             accent=ACCENT_AMBER)

    add_callout(slide, "過早優化是萬惡之源 — Donald Knuth。先讓產品活下來，再考慮 Scale",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="tip")
    return slide


def slide_10(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "Scale Up vs Scale Out：兩種擴展思路")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 10)

    # Left: Scale Up
    add_card(slide, Inches(0.4), Inches(1.9), Inches(5.8), Inches(0.5),
             title="Scale Up  垂直擴展", accent=ACCENT_AMBER)
    add_card(slide, Inches(0.4), Inches(2.6), Inches(5.8), Inches(3.5),
             body_lines=[
                 "舊機器: 4 Core / 16GB",
                 "    ↓",
                 "新機器: 64 Core / 512GB",
                 "",
                 "✅ 架構不用改，快速",
                 "✅ 無需修改程式碼",
                 "⚠  成本指數級成長",
                 "⚠  硬體有上限",
                 "⚠  升級需要停機",
             ],
             accent=ACCENT_AMBER)

    # Right: Scale Out
    add_card(slide, Inches(7.0), Inches(1.9), Inches(5.8), Inches(0.5),
             title="Scale Out  水平擴展", accent=ACCENT_GREEN)
    add_card(slide, Inches(7.0), Inches(2.6), Inches(5.8), Inches(3.5),
             body_lines=[
                 "Server 1 (4C/16GB)",
                 "Server 2 (4C/16GB)",
                 "Server 3 (4C/16GB)  + N 台",
                 "",
                 "✅ 成本線性成長，彈性",
                 "✅ 零停機，滾動更新",
                 "✅ 理論上無上限",
                 "⚠  架構需要重新設計",
             ],
             accent=ACCENT_GREEN)

    # Center VS label
    add_text(slide, "VS", Inches(6.0), Inches(3.5), Inches(0.8), Inches(0.8),
             font_size=Pt(28), color=TEXT_DIM, align=PP_ALIGN.CENTER, bold=True)

    add_callout(slide, "Scale Out 是 Cloud Native 的核心，但需要應用程式支援 Stateless 設計",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="tip")
    return slide


def slide_11(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "Stateless 設計：Scale Out 的先決條件")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 11)

    # Left: Stateful (bad)
    add_card(slide, Inches(0.4), Inches(1.6), Inches(5.8), Inches(3.5),
             title="❌ Stateful（有問題）",
             body_lines=[
                 "Session 存在 App Server 記憶體",
                 "Request #1 → Server A (登入成功)",
                 "Request #2 → Server B (找不到 Session!)",
                 "→ 用戶被強制登出！",
                 "",
                 "問題：Server 之間 Session 無法共用",
             ],
             accent=RGBColor(0xFF, 0x4A, 0x4A))

    # Right: Stateless (good)
    add_card(slide, Inches(7.0), Inches(1.6), Inches(5.8), Inches(3.5),
             title="✅ Stateless（正確）",
             body_lines=[
                 "Session 外部化存入 Redis",
                 "Request #1 → Server A → Redis 取 Session",
                 "Request #2 → Server B → Redis 取 Session",
                 "→ 任一台 Server 都能處理！",
                 "",
                 "原則：App Server 不存任何特定狀態",
             ],
             accent=ACCENT_GREEN)

    # Center arrow
    add_text(slide, "→", Inches(6.0), Inches(3.0), Inches(0.8), Inches(0.6),
             font_size=Pt(28), color=ACCENT_BLUE, align=PP_ALIGN.CENTER, bold=True)

    add_callout(slide, "每個 Request 都應該可以被任何一台 Server 處理 — 這是 Scale Out 的核心前提",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="tip")
    return slide


def slide_12(prs):
    slide = new_slide(prs)
    add_slide_title(slide, "Part 1 小結：架構演進路線圖")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 12)

    # Timeline baseline
    add_rect(slide, Inches(0.5), Inches(3.15), Inches(12.3), Inches(0.04), ACCENT_BLUE)

    stages = ["單機部署", "DB 分離", "三層架構", "需要 Scale Out"]
    pains = [
        "✅ 快速上線\n⚠ SPOF，無擴展性",
        "✅ 資料持久化\n⚠ 2台機器，網路延遲",
        "✅ 職責清晰\n⚠ 3台機器，部署複雜",
        "✅ 高可用潛力\n⚠ Session / LB 挑戰",
    ]

    node_xs = [0.6, 3.8, 7.0, 10.2]

    for i, (stage, pain) in enumerate(zip(stages, pains)):
        nx = Inches(node_xs[i])
        # Dot
        add_rect(slide, nx, Inches(3.0), Inches(0.32), Inches(0.32), ACCENT_BLUE)
        # Above line: stage title
        add_text(slide, stage, nx - Inches(1.0), Inches(1.85), Inches(2.8), Inches(1.0),
                 font_size=Pt(13), color=TEXT_PRIMARY, align=PP_ALIGN.CENTER, bold=True)
        # Below line: pain points
        add_text(slide, pain, nx - Inches(1.0), Inches(3.35), Inches(2.8), Inches(1.5),
                 font_size=Pt(11), color=TEXT_DIM, align=PP_ALIGN.CENTER)

    add_callout(slide, "下一步 → Part 2：如何 Scale Out，以及隨之而來的新挑戰",
                Inches(0.4), Inches(6.6), Inches(12.5), Inches(0.55), style="tip")
    return slide


if __name__ == "__main__":
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    slide_01_cover(prs)
    slide_02_agenda(prs)
    for fn in [slide_03, slide_04, slide_05, slide_06, slide_07,
               slide_08, slide_09, slide_10, slide_11, slide_12]:
        fn(prs)

    prs.save("cloud_native_slides_v2.pptx")
    print(f"✅ Generated {len(prs.slides)} slides → cloud_native_slides_v2.pptx")
