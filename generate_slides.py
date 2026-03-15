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


if __name__ == "__main__":
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # Smoke test: create 1 slide using all helpers
    slide = new_slide(prs)
    add_slide_title(slide, "Test Slide — Theme Smoke Test", "Verifying all helpers work")
    add_part_label(slide, 1, "傳統部署的演進")
    add_page_number(slide, 1)
    add_card(slide, Inches(0.5), Inches(2.0), Inches(4.0), Inches(2.5),
             title="Card Title", body_lines=["Line 1 content", "Line 2 content", "Line 3 content"])
    add_card(slide, Inches(5.0), Inches(2.0), Inches(4.0), Inches(2.5),
             title="No-border card test", body_lines=["Test"], accent=ACCENT_GREEN)
    add_callout(slide, "This is a tip callout message", Inches(0.5), Inches(5.0), Inches(5.5), Inches(0.6), "tip")
    add_callout(slide, "This is a warning message", Inches(6.5), Inches(5.0), Inches(5.5), Inches(0.6), "warning")

    prs.save("cloud_native_slides_v2.pptx")
    print(f"✅ Smoke test passed: {len(prs.slides)} slide(s) generated → cloud_native_slides_v2.pptx")
