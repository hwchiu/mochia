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


if __name__ == "__main__":
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    slide_01_cover(prs)
    slide_02_agenda(prs)

    prs.save("cloud_native_slides_v2.pptx")
    print(f"✅ Generated {len(prs.slides)} slides → cloud_native_slides_v2.pptx")
