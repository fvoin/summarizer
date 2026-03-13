#!/usr/bin/env python3
"""Generate a PDF user guide for the Summarizer app."""

import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white, Color, transparent
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping
import math

W, H = A4

pdfmetrics.registerFont(TTFont("Arial", "/System/Library/Fonts/Supplemental/Arial.ttf"))
pdfmetrics.registerFont(TTFont("ArialBd", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("ArialIt", "/System/Library/Fonts/Supplemental/Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("ArialBI", "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"))
addMapping("Arial", 0, 0, "Arial")
addMapping("Arial", 1, 0, "ArialBd")
addMapping("Arial", 0, 1, "ArialIt")
addMapping("Arial", 1, 1, "ArialBI")

F = "Arial"
FB = "ArialBd"

ICON_PATH = os.path.join(os.path.dirname(__file__), "summarizer", "icon.png")

PRIMARY = HexColor("#4A90D9")
ACCENT = HexColor("#7B68EE")
DANGER = HexColor("#D94A4A")
SUCCESS = HexColor("#2D8A4E")
BG = HexColor("#ECECEC")
BORDER = HexColor("#D1D1D6")
TEXT = HexColor("#1D1D1F")
TEXT2 = HexColor("#6E6E73")
MUTED = HexColor("#AEAEB2")

OUT = "Summarizer_Guide.pdf"


def rrect(c, x, y, w, h, r=4, fill=None, stroke=None, sw=0.5):
    c.saveState()
    if fill:
        c.setFillColor(fill)
    if stroke:
        c.setStrokeColor(stroke)
        c.setLineWidth(sw)
    p = c.beginPath()
    p.roundRect(x, y, w, h, r)
    c.drawPath(p, fill=1 if fill else 0, stroke=1 if stroke else 0)
    c.restoreState()


def arr(c, x1, y1, x2, y2, color=DANGER, w=1.2, hs=5):
    c.saveState()
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(w)
    c.line(x1, y1, x2, y2)
    a = math.atan2(y2 - y1, x2 - x1)
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - hs * math.cos(a - 0.4), y2 - hs * math.sin(a - 0.4))
    p.lineTo(x2 - hs * math.cos(a + 0.4), y2 - hs * math.sin(a + 0.4))
    p.close()
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()


def dbtn(c, x, y, w, h, label, fill=PRIMARY, tc=white, fs=10):
    rrect(c, x, y, w, h, r=6, fill=fill)
    c.saveState()
    c.setFillColor(tc)
    c.setFont(FB, fs)
    tw = c.stringWidth(label, FB, fs)
    c.drawString(x + (w - tw) / 2, y + (h - fs) / 2 + 1, label)
    c.restoreState()


def field(c, x, y, w, h, text=""):
    rrect(c, x, y, w, h, r=4, fill=white, stroke=BORDER, sw=0.5)
    if text:
        c.saveState()
        c.setFillColor(MUTED)
        c.setFont(F, 8)
        c.drawString(x + 6, y + (h - 8) / 2 + 1, text)
        c.restoreState()


def combo(c, x, y, w, h, label="(none)"):
    rrect(c, x, y, w, h, r=4, fill=white, stroke=BORDER, sw=0.5)
    c.saveState()
    c.setFillColor(TEXT)
    c.setFont(F, 8)
    c.drawString(x + 6, y + (h - 8) / 2 + 1, label)
    cx = x + w - 12
    cy = y + h / 2 + 2
    c.setStrokeColor(TEXT2)
    c.setLineWidth(1)
    c.line(cx - 3, cy, cx, cy - 4)
    c.line(cx, cy - 4, cx + 3, cy)
    c.restoreState()


def circnum(c, x, y, num, color=PRIMARY):
    c.saveState()
    c.setFillColor(color)
    c.circle(x, y + 4, 10, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont(FB, 10)
    tw = c.stringWidth(str(num), FB, 10)
    c.drawString(x - tw / 2, y + 0.5, str(num))
    c.restoreState()


# ─── Cover ──────────────────────────────────────────────────────────

def page_cover(c):
    steps = 50
    for i in range(steps):
        t = i / steps
        r = 0.29 * (1 - t) + 0.48 * t
        g = 0.56 * (1 - t) + 0.41 * t
        b = 0.85 * (1 - t) + 0.93 * t
        c.setFillColor(Color(r, g, b))
        bh = H / steps
        c.rect(0, H - (i + 1) * bh, W, bh + 1, fill=1, stroke=0)

    # Actual app icon
    isz = 100
    if os.path.exists(ICON_PATH):
        c.drawImage(ICON_PATH, W / 2 - isz / 2, H / 2 + 65, isz, isz,
                     preserveAspectRatio=True, mask="auto")
    else:
        rrect(c, W / 2 - isz / 2, H / 2 + 65, isz, isz, r=22,
              fill=Color(1, 1, 1, 0.2))

    c.setFillColor(white)
    c.setFont(FB, 38)
    c.drawCentredString(W / 2, H / 2 + 16, "Summarizer")

    c.setFont(F, 16)
    c.drawCentredString(W / 2, H / 2 - 16, "User Guide")

    c.setFont(F, 12)
    c.setFillColor(Color(1, 1, 1, 0.7))
    c.drawCentredString(W / 2, H / 2 - 55, "Record, transcribe and summarize meetings with AI")
    c.drawCentredString(W / 2, H / 2 - 75, "macOS  /  Whisper  /  Gemini  /  GPT-5  /  Claude")


# ─── Installation ───────────────────────────────────────────────────

def page_install(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Installation")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "One-time setup — takes about a minute.")

    # Steps
    steps = [
        ("Download Summarizer.dmg",
         "Go to github.com/fvoin/summarizer/releases and download the latest DMG file."),
        ("Open the DMG",
         "Double-click the downloaded file. A window opens showing Summarizer and an Applications folder."),
        ("Drag to Applications",
         "Drag the Summarizer icon into the Applications folder shortcut."),
        ("Launch and allow",
         "Open Summarizer from Applications (Launchpad or Finder).\n"
         "macOS will say the app is from an unidentified developer — open\n"
         "System Settings → Privacy & Security → scroll down → Open Anyway."),
        ("Set up an AI model",
         "Click the gear icon → Models tab.\n"
         "Cloud: enter your API key (free Gemini key at aistudio.google.com/apikey)\n"
         "Local: click Pull on any Ollama model — no API key, fully offline."),
    ]

    y = H - 110
    for i, (title, desc) in enumerate(steps):
        circnum(c, 55, y, i + 1)
        c.setFillColor(TEXT)
        c.setFont(FB, 11)
        c.drawString(72, y, title)
        y -= 6
        for line in desc.split("\n"):
            c.setFont(F, 9.5)
            c.setFillColor(TEXT2)
            c.drawString(72, y - 13, line)
            y -= 14
        y -= 14

    # DMG mockup
    mx = 105
    my = 145
    mw = 270
    mh = 115

    rrect(c, mx, my, mw, mh, r=8, fill=BG, stroke=BORDER, sw=0.8)

    # Traffic lights
    for i, col in enumerate([HexColor("#FF5F57"), HexColor("#FFBD2E"), HexColor("#28C940")]):
        c.setFillColor(col)
        c.circle(mx + 12 + i * 13, my + mh - 12, 4, fill=1, stroke=0)
    c.setFillColor(TEXT)
    c.setFont(FB, 8)
    c.drawCentredString(mx + mw / 2, my + mh - 16, "Summarizer")

    # App icon
    isz = 48
    ix = mx + mw / 2 - 70
    if os.path.exists(ICON_PATH):
        c.drawImage(ICON_PATH, ix, my + 24, isz, isz, preserveAspectRatio=True, mask="auto")
    else:
        rrect(c, ix, my + 24, isz, isz, r=12, fill=PRIMARY)
    c.setFillColor(TEXT)
    c.setFont(F, 8)
    c.drawCentredString(ix + isz / 2, my + 16, "Summarizer")

    # Arrow
    arr(c, mx + mw / 2 - 10, my + 48, mx + mw / 2 + 10, my + 48, color=ACCENT, w=2, hs=6)

    # Applications folder
    ax2 = mx + mw / 2 + 22
    rrect(c, ax2, my + 24, isz, isz, r=12, fill=HexColor("#C8D8F0"))
    c.setFillColor(PRIMARY)
    c.setFont(FB, 7)
    c.drawCentredString(ax2 + isz / 2, my + 38, "Applications")
    c.setFillColor(TEXT)
    c.setFont(F, 8)
    c.drawCentredString(ax2 + isz / 2, my + 16, "Applications")

    # "Open Anyway" note
    rrect(c, 60, 55, W - 120, 50, r=6, fill=Color(0.29, 0.56, 0.85, 0.07))
    c.setFillColor(PRIMARY)
    c.setFont(FB, 9)
    c.drawString(75, 90, "First launch only:")
    c.setFont(F, 9)
    c.setFillColor(TEXT)
    c.drawString(75, 76, "System Settings → Privacy & Security → Open Anyway")
    c.drawString(75, 63, "This is required once for any app not from the App Store.")


# ─── What Is ────────────────────────────────────────────────────────

def page_what_is(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "What is Summarizer?")

    bs = ParagraphStyle("b", fontName=F, fontSize=11, leading=16, textColor=TEXT, spaceAfter=8)
    hs = ParagraphStyle("h", fontName=FB, fontSize=13, leading=18, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (bs, "<b>Summarizer</b> is a macOS application that automatically records, "
             "transcribes, and summarizes meetings and audio recordings."),
        (bs, "It uses <b>Whisper</b> for local speech recognition (audio never leaves "
             "your machine) and LLM models (Gemini, Claude, OpenAI) to generate "
             "structured summaries."),
        (hs, "Key Features"),
        (bs, "<b>Audio recording</b> — record from your microphone with automatic "
             "silence detection and auto-stop"),
        (bs, "<b>Local transcription</b> — Whisper models (tiny through large-v3) "
             "run directly on your Mac, no cloud needed"),
        (bs, "<b>AI summarization</b> — structured output: Overview, Key Decisions, "
             "Action Items, Discussion Points, Risks, and a Meeting Score with cost estimate"),
        (bs, "<b>Fully offline mode</b> — use local LLM models (Llama, Gemma, Qwen) via Ollama "
             "for 100% offline operation — nothing ever leaves your machine"),
        (bs, "<b>Instruction profiles</b> — create multiple prompt profiles and switch "
             "between them for different meeting types (standup, review, 1-on-1...)"),
        (bs, "<b>Context</b> — accumulate meeting history for more accurate summaries "
             "across recurring meetings"),
        (bs, "<b>Slack-ready</b> — Copy Summary pastes with bold/italic formatting "
             "that works directly in Slack"),
    ]

    fr = Frame(40, 320, W - 80, H - 120 - 320, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # Flow
    fy = 270
    c.setFont(FB, 12)
    c.setFillColor(PRIMARY)
    c.drawCentredString(W / 2, fy + 20, "Workflow")

    steps = [
        ("Record", PRIMARY),
        ("Transcribe", ACCENT),
        ("Summarize", SUCCESS),
        ("Copy", PRIMARY),
    ]
    bw, bh = 105, 34
    gap = 20
    total = len(steps) * bw + (len(steps) - 1) * gap
    sx = (W - total) / 2
    for i, (label, color) in enumerate(steps):
        bx = sx + i * (bw + gap)
        rrect(c, bx, fy - 40, bw, bh, r=8, fill=color)
        c.setFillColor(white)
        c.setFont(FB, 10)
        tw = c.stringWidth(label, FB, 10)
        c.drawString(bx + (bw - tw) / 2, fy - 27, label)
        if i < len(steps) - 1:
            arr(c, bx + bw + 3, fy - 23, bx + bw + gap - 3, fy - 23,
                color=TEXT2, w=1, hs=4)

    c.setFillColor(TEXT2)
    c.setFont(F, 9)
    c.drawCentredString(W / 2, fy - 56, "The entire process takes from a few seconds to a couple of minutes")

    # Privacy note
    rrect(c, 50, 82, W - 100, 105, r=8, fill=Color(0.29, 0.56, 0.85, 0.07))
    c.setFillColor(PRIMARY)
    c.setFont(FB, 10)
    c.drawString(65, 168, "Privacy")
    c.setFont(F, 9.5)
    c.setFillColor(TEXT)
    lines = [
        "Audio is processed LOCALLY by Whisper — it never leaves your machine.",
        "With cloud models, only the text transcript is sent for summarization.",
        "With local models (Ollama), everything stays on your Mac — fully offline.",
        "No data is collected. No accounts required. You own all your data.",
    ]
    ly = 150
    for line in lines:
        c.drawString(65, ly, line)
        ly -= 16


# ─── Main Window ────────────────────────────────────────────────────

def page_main_window(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Main Window")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "Everything is accessible from a single window.")

    # Mockup
    ox, oy = 55, 130
    ww, wh = 300, 380

    rrect(c, ox, oy, ww, wh, r=8, fill=BG, stroke=BORDER, sw=0.8)

    # Traffic lights
    for i, col in enumerate([HexColor("#FF5F57"), HexColor("#FFBD2E"), HexColor("#28C940")]):
        c.setFillColor(col)
        c.circle(ox + 14 + i * 14, oy + wh - 14, 4, fill=1, stroke=0)

    ty = oy + wh - 36
    c.setFillColor(PRIMARY)
    c.setFont(FB, 12)
    c.drawString(ox + 14, ty, "Summarizer")

    # Gear
    gx, gy = ox + ww - 22, ty + 5
    c.setFillColor(ACCENT)
    c.circle(gx, gy, 7, fill=1, stroke=0)
    c.setFillColor(BG)
    c.circle(gx, gy, 3, fill=1, stroke=0)

    # Context
    ct = ty - 14
    ch = 48
    cy = ct - ch
    rrect(c, ox + 8, cy, ww - 16, ch, r=5, fill=Color(1, 1, 1, 0.4), stroke=BORDER, sw=0.3)
    c.setFillColor(TEXT2)
    c.setFont(F, 7)
    c.drawString(ox + 14, cy + ch - 10, "Context")
    c.drawString(ox + 14, cy + ch - 24, "Named:")
    combo(c, ox + 50, cy + ch - 28, 170, 14)
    c.setFillColor(PRIMARY)
    c.setFont(FB, 11)
    c.drawString(ox + 228, cy + ch - 26, "+")
    field(c, ox + 14, cy + 4, ww - 36, 14, "Quick context...")

    # Record
    ry = cy - 10
    rh = 28
    ry -= rh
    dbtn(c, ox + 8, ry, ww - 16, rh, "Start Recording", PRIMARY, white, 10)

    # File buttons
    fby = ry - 28
    c.setFillColor(PRIMARY)
    c.setFont(F, 8)
    c.drawString(ox + 30, fby + 6, "Summarize Audio File")
    c.drawString(ox + 165, fby + 6, "Summarize Transcript")

    # Drop hint
    dry = fby - 14
    c.setFillColor(MUTED)
    c.setFont(F, 7)
    c.drawCentredString(ox + ww / 2, dry, "or drag & drop audio / transcript files here")

    # Status
    sty = dry - 18
    rrect(c, ox + 10, sty - 2, 36, 13, r=6, fill=Color(0.18, 0.54, 0.31, 0.12))
    c.setFillColor(SUCCESS)
    c.setFont(FB, 7)
    c.drawString(ox + 16, sty + 1, "Done")

    # Summary
    smt = sty - 10
    smh = smt - oy - 32
    smy = smt - smh
    rrect(c, ox + 8, smy, ww - 16, smh, r=5, fill=white, stroke=BORDER, sw=0.3)
    lines = [
        ("\U0001f5d2\ufe0f Overview", True),
        ("  Sync on Q3 roadmap; approved new dashboard.", False),
        ("", False),
        ("\U0001f3af Key Decisions", True),
        ("  Dashboard redesign approved for v2.4", False),
        ("", False),
        ("\u2705 Action Items", True),
        ("  Masha \u2014 prototype \u2014 Friday", False),
        ("  Pete \u2014 API review \u2014 next sprint", False),
        ("", False),
        ("\U0001f4ca Meeting Score", True),
        ("  Efficiency: 7/10  Cost: ~300 EUR", False),
    ]
    ly = smy + smh - 12
    for text, bold in lines:
        c.setFont(FB if bold else F, 7)
        c.setFillColor(TEXT if bold else TEXT2)
        c.drawString(ox + 16, ly, text)
        ly -= 10

    # Bottom
    boty = oy + 10
    c.setFillColor(PRIMARY)
    c.setFont(F, 8)
    c.drawString(ox + 14, boty, "Copy Summary")
    c.drawString(ox + 120, boty, "Open Transcript")

    # Annotations
    ax = ox + ww + 16

    def ann(label, desc, to_x, to_y, ty):
        c.setFillColor(TEXT)
        c.setFont(FB, 8.5)
        c.drawString(ax + 6, ty, label)
        c.setFillColor(TEXT2)
        c.setFont(F, 8)
        c.drawString(ax + 6, ty - 12, desc)
        arr(c, ax, ty + 1, to_x, to_y, color=DANGER, w=1, hs=4)

    ann("Settings", "LLM, Whisper, API keys",
        gx - 8, gy, oy + wh - 40)
    ann("Context", "Meeting history + quick notes",
        ox + ww - 8, cy + ch / 2, cy + ch / 2 + 6)
    ann("Record", "Click to start recording",
        ox + ww - 8, ry + rh / 2, ry + rh / 2 + 6)
    ann("Import Files", "Audio or transcript file",
        ox + ww - 8, fby + 10, fby + 10)
    ann("Status", "Color-coded state indicator",
        ox + 48, sty + 4, sty + 4)
    ann("Result", "AI summary with formatting",
        ox + ww - 8, smy + smh / 2, smy + smh / 2 + 6)
    ann("Actions", "Copy to clipboard / open file",
        ox + ww - 8, boty + 4, boty)


# ─── Recording ──────────────────────────────────────────────────────

def page_recording(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Recording Audio")

    y = H - 95

    steps = [
        ("Press Start Recording",
         "The button turns red and shows a timer. The app records "
         "audio from the selected input device (configured in Settings).",
         True),
        ("Automatic Stop",
         "Recording stops automatically after a period of silence "
         "(configurable in Settings, default 30 seconds). "
         "You can also stop manually by pressing the red button.",
         False),
        ("Transcription",
         "After stopping, Whisper automatically recognizes the speech. "
         "The model runs locally — audio never leaves your machine. "
         "Progress is shown with a color-coded status indicator.",
         False),
        ("Summary & Result",
         "The LLM generates a structured summary. Use Copy Summary "
         "to copy with formatting that works in Slack. "
         "The transcript is saved to a file you can open.",
         False),
    ]

    for i, (title, desc, show_btns) in enumerate(steps):
        circnum(c, 55, y, i + 1)
        c.setFillColor(TEXT)
        c.setFont(FB, 12)
        c.drawString(72, y, title)
        y -= 4
        st = ParagraphStyle("p", fontName=F, fontSize=10, leading=14, textColor=TEXT2)
        p = Paragraph(desc, st)
        pw, ph = p.wrap(W - 130, 200)
        p.drawOn(c, 72, y - ph)
        y -= ph + 4
        if show_btns:
            dbtn(c, 80, y - 24, 140, 24, "Start Recording", PRIMARY, white, 9)
            arr(c, 224, y - 12, 240, y - 12, color=TEXT2, w=1, hs=4)
            dbtn(c, 244, y - 24, 140, 24, "Stop  1:23", DANGER, white, 9)
            y -= 32
        y -= 18

    # Tips
    th = 70
    ty = y - th - 10
    rrect(c, 40, ty, W - 80, th, r=8, fill=Color(0.29, 0.56, 0.85, 0.07))
    c.setFillColor(PRIMARY)
    c.setFont(FB, 10)
    c.drawString(55, ty + th - 16, "Tips")
    c.setFont(F, 9)
    c.setFillColor(TEXT)
    tips = [
        "- Whisper runs locally — audio is never sent to the cloud",
        "- For better transcription quality, use the medium or large-v3 model",
        "- Saving audio files can be enabled in Settings (off by default)",
    ]
    ly = ty + th - 32
    for tip in tips:
        c.drawString(63, ly, tip)
        ly -= 14


# ─── Settings helpers ───────────────────────────────────────────────

def _settings_frame(c, title, active_tab):
    """Draw Settings window chrome with tab bar. Returns (sx, content_top_y, sw)."""
    sx, sy = 80, 85
    sw, sh = 360, 620
    rrect(c, sx, sy, sw, sh, r=8, fill=BG, stroke=BORDER, sw=0.8)

    # Title
    c.setFillColor(TEXT)
    c.setFont(FB, 10)
    c.drawCentredString(sx + sw / 2, sy + sh - 16, "Settings")

    # Tab bar
    tab_y = sy + sh - 24
    tabs = ["Models", "Instructions", "General"]
    tw = sw / len(tabs)
    for i, label in enumerate(tabs):
        is_active = label == active_tab
        tx = sx + i * tw
        rrect(c, tx, tab_y - 18, tw, 18, r=0,
              fill=white if is_active else Color(0.93, 0.93, 0.95))
        c.saveState()
        c.setFillColor(PRIMARY if is_active else TEXT2)
        c.setFont(FB if is_active else F, 8)
        lw = c.stringWidth(label, FB if is_active else F, 8)
        c.drawString(tx + (tw - lw) / 2, tab_y - 13, label)
        c.restoreState()

    # Save/Cancel
    dbtn(c, sx + sw - 108, sy + 10, 48, 18, "Save", PRIMARY, white, 8)
    c.setFillColor(TEXT2)
    c.setFont(F, 8)
    c.drawString(sx + sw - 50, sy + 15, "Cancel")

    return sx, tab_y - 30, sw, sy + 34


# ─── Settings: Models tab ──────────────────────────────────────────

def page_settings_models(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Settings — Models")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "Choose between cloud and local AI models for summarization.")

    sx, ry, sw, bottom = _settings_frame(c, "Settings", "Models")

    # ── Cloud ──
    c.setFillColor(HexColor("#6e6e73"))
    c.setFont(FB, 8)
    c.drawString(sx + 14, ry, "\u2601  Cloud")
    ry -= 16

    cloud_models = [
        ("Gemini 3 Flash Preview", True),
        ("Gemini 2.5 Pro", False),
        ("GPT-5 mini", False),
        ("GPT-5.4", False),
        ("Custom:", False),
    ]
    for label, selected in cloud_models:
        c.saveState()
        c.setStrokeColor(PRIMARY if selected else BORDER)
        c.setLineWidth(1)
        c.circle(sx + 24, ry + 3, 4.5, fill=0, stroke=1)
        if selected:
            c.setFillColor(PRIMARY)
            c.circle(sx + 24, ry + 3, 2.5, fill=1, stroke=0)
        c.setFillColor(TEXT if selected else TEXT2)
        c.setFont(FB if selected else F, 8.5)
        c.drawString(sx + 34, ry, label)
        c.restoreState()
        ry -= 15

    # Custom text field on same line as "Custom:"
    ry += 15
    field(c, sx + 80, ry - 4, sw - 105, 14, "model name…")
    ry -= 20

    # API Key + Base URL
    c.setFillColor(TEXT)
    c.setFont(FB, 8)
    c.drawString(sx + 14, ry, "API Key:")
    field(c, sx + 60, ry - 5, 120, 14, "your API key")
    c.drawString(sx + 192, ry, "Base URL:")
    field(c, sx + 240, ry - 5, sw - 260, 14, "(optional)")
    ry -= 26

    # ── Local ──
    c.setFillColor(HexColor("#6e6e73"))
    c.setFont(FB, 8)
    c.drawString(sx + 14, ry, "\u26a1  Local (Ollama)")
    ry -= 16

    local_models = [
        ("GLM-4 9B", "Good", "5.5 GB", False),
        ("Gemma 3 12B", "Better", "8.1 GB", False),
        ("DeepSeek R1 14B", "Best reasoning", "9.0 GB", False),
    ]
    for name, quality, size, selected in local_models:
        c.saveState()
        c.setStrokeColor(PRIMARY if selected else BORDER)
        c.setLineWidth(1)
        c.circle(sx + 24, ry + 3, 4.5, fill=0, stroke=1)
        c.setFillColor(TEXT)
        c.setFont(FB, 8.5)
        c.drawString(sx + 34, ry, name)
        c.setFont(F, 8)
        c.setFillColor(TEXT2)
        c.drawString(sx + 120, ry, f"— {quality} ({size})")
        c.setFillColor(PRIMARY)
        c.setFont(F, 8)
        c.drawString(sx + sw - 50, ry, "Pull")
        c.restoreState()
        ry -= 15

    ry -= 10

    # Divider
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.4)
    c.line(sx + 10, ry + 6, sx + sw - 10, ry + 6)
    ry -= 4

    # ── Whisper ──
    c.setFillColor(TEXT)
    c.setFont(FB, 8)
    c.drawString(sx + 14, ry, "Whisper Model (speech recognition)")
    ry -= 16

    whisper_models = [
        ("tiny", "75 MB", "Basic", False, False),
        ("base", "145 MB", "Good", True, True),
        ("small", "465 MB", "Better", False, False),
        ("medium", "1.5 GB", "Great", False, False),
        ("large-v3", "3.1 GB", "Best", False, False),
    ]
    for name, size, quality, selected, downloaded in whisper_models:
        c.saveState()
        c.setStrokeColor(PRIMARY if selected else BORDER)
        c.setLineWidth(1)
        c.circle(sx + 24, ry + 3, 4.5, fill=0, stroke=1)
        if selected:
            c.setFillColor(PRIMARY)
            c.circle(sx + 24, ry + 3, 2.5, fill=1, stroke=0)
        c.setFillColor(TEXT)
        c.setFont(FB, 8.5)
        c.drawString(sx + 34, ry, name)
        c.setFont(F, 8)
        c.setFillColor(TEXT2)
        c.drawString(sx + 82, ry, f"— {quality} ({size})")
        if downloaded:
            c.setFillColor(SUCCESS)
            c.setFont(FB, 8)
            c.drawString(sx + sw - 55, ry, "Ready")
        else:
            c.setFillColor(PRIMARY)
            c.setFont(F, 8)
            c.drawString(sx + sw - 70, ry, "Download")
        c.restoreState()
        ry -= 15

    # ── Annotations ──
    nx = sx + sw + 20

    def ann(label, desc, ay):
        c.setFillColor(TEXT)
        c.setFont(FB, 9)
        c.drawString(nx, ay, label)
        for j, line in enumerate(desc.split("\n")):
            c.setFillColor(TEXT2)
            c.setFont(F, 8)
            c.drawString(nx, ay - 13 - j * 12, line)

    ann("Cloud presets", "Select a model or enter\na custom model name", H - 150)
    ann("API credentials", "Key for the selected\ncloud provider", H - 245)
    ann("Local models (Ollama)", "Run AI on your Mac —\n100% offline, no API key.\nClick Pull to download.", H - 320)
    ann("Whisper models", "Speech-to-text (offline).\nLarger = more accurate\nbut slower.", H - 440)


# ─── Settings: Instructions tab ────────────────────────────────────

def page_settings_instructions(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Settings — Instructions")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "Customize the AI prompt. Create profiles for different meeting types.")

    sx, ry, sw, bottom = _settings_frame(c, "Settings", "Instructions")

    # Profile row
    c.setFillColor(TEXT)
    c.setFont(FB, 9)
    c.drawString(sx + 14, ry, "Profile:")
    combo(c, sx + 60, ry - 5, 160, 18, "Default")

    c.setFillColor(PRIMARY)
    c.setFont(F, 9)
    c.drawString(sx + 232, ry, "New")
    c.setFillColor(DANGER)
    c.drawString(sx + 264, ry, "Delete")
    ry -= 30

    # Large text area
    th = ry - bottom - 10
    rrect(c, sx + 12, bottom + 5, sw - 24, th, r=5, fill=white, stroke=BORDER, sw=0.4)

    prompt_lines = [
        "You are a professional meeting analyst. Produce a structured,",
        "actionable summary of the transcript below.",
        "",
        "Output exactly these sections in order:",
        "",
        "\U0001f5d2\ufe0f *Overview*",
        "\u2022 One sentence: meeting purpose and main outcome.",
        "",
        "\U0001f3af *Key Decisions*",
        "\u2022 Each confirmed decision, stated as a fact.",
        "\u2022 If none \u2014 omit this section entirely.",
        "",
        "\u2705 *Action Items*",
        "\u2022 Format: *Owner* \u2014 task \u2014 _deadline if mentioned_",
        "\u2022 If owner is unclear, write _unassigned_.",
        "",
        "\U0001f4ac *Key Discussion Points*",
        "\u2022 Important topics discussed, options considered.",
        "",
        "\u26a0\ufe0f *Risks & Open Questions*",
        "\u2022 Unresolved issues, blockers, follow-ups.",
        "",
        "\U0001f4ca *Meeting Score*",
        "\u2022 *Efficiency*: X/10 \u2014 one-line reason",
        "\u2022 *Cost estimate*: [duration]h \u00d7 [N] \u00d7 50 EUR = ~X EUR",
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500",
        "FORMATTING: \u2022 only, *bold*, _italic_, no # markdown",
    ]
    ly = bottom + th - 4
    for line in prompt_lines:
        ly -= 11
        if ly < bottom + 10:
            break
        bold = line.startswith(("\U0001f5d2", "\U0001f3af", "\u2705", "\U0001f4ac", "\u26a0", "\U0001f4ca", "\u2500", "FORMATTING"))
        c.setFillColor(TEXT if bold else TEXT2)
        c.setFont(FB if bold else F, 7.5)
        c.drawString(sx + 20, ly, line)

    # Annotations
    nx = sx + sw + 20

    def ann(label, desc, ay):
        c.setFillColor(TEXT)
        c.setFont(FB, 9)
        c.drawString(nx, ay, label)
        for j, line in enumerate(desc.split("\n")):
            c.setFillColor(TEXT2)
            c.setFont(F, 8)
            c.drawString(nx, ay - 13 - j * 12, line)

    ann("Profiles", "Create separate prompts for\nstandups, reviews, 1-on-1s.\nSwitch with the dropdown.", H - 150)
    ann("Default prompt", "Structured meeting summary\nwith sections: Overview,\nDecisions, Actions, Score.\nEdit freely or replace.", H - 260)
    ann("Formatting rules", "Controls how the LLM\nformats output — bullets,\nbold, italic, no markdown.", H - 400)


# ─── Settings: General tab ─────────────────────────────────────────

def page_settings_general(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Settings — General")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "Audio, recording, and storage preferences.")

    sx, ry, sw, bottom = _settings_frame(c, "Settings", "General")

    rows = [
        ("Context Limit:", "5000 chars",
         "Max characters loaded from context file.\nOlder content is trimmed automatically."),
        ("Silence Timeout:", "30 sec",
         "Stop recording after this much silence.\nRange: 5–300 seconds."),
        ("Input Device:", "Default",
         "Choose your microphone.\nDefault uses the system input device."),
        ("Save Audio:", "off",
         "When on, saves WAV recordings to disk.\nOff by default — files are temporary."),
        ("Recordings Dir:", "~/.summarizer/recordings",
         "Where transcripts and context files\nare stored."),
    ]

    for label, value, note in rows:
        c.setFillColor(TEXT)
        c.setFont(FB, 10)
        c.drawString(sx + 14, ry, label)
        field(c, sx + 130, ry - 6, sw - 150, 18, value)
        ry -= 28

        c.setFillColor(TEXT2)
        c.setFont(F, 8)
        for line in note.split("\n"):
            c.drawString(sx + 14, ry, line)
            ry -= 12
        ry -= 16


# ─── Context ────────────────────────────────────────────────────────

def page_context(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Working with Context")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    hs = ParagraphStyle("h", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (hs, "What is Context?"),
        (bs, "Context lets Summarizer take previous meetings into account when "
             "generating summaries. This is useful for recurring meetings (standups, "
             "1-on-1s) where tracking progress and action items matters."),
        (hs, "Named Context"),
        (bs, "Create a named context with the <b>+</b> button next to the dropdown. "
             "Each time a summary is generated, previous summaries are automatically "
             "loaded from the context file, and the new summary is appended."),
        (bs, "Files stored at: <b>~/.summarizer/recordings/name_context.txt</b>"),
        (hs, "Quick Context"),
        (bs, "The text field in the main window for one-off notes — it is <b>always</b> "
             "included in the prompt, even if a named context is selected. "
             "Example: 'meeting with client X', 'focus on backend tasks'."),
        (bs, "Quick context is also saved to the named context file if one is selected."),
        (hs, "Context Limit"),
        (bs, "Settings lets you configure the maximum number of characters loaded from "
             "the context file (default 5000). When exceeded, the last N characters are "
             "taken, trimmed at a line boundary."),
    ]

    fr = Frame(40, 260, W - 80, H - 120 - 260, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # Diagram
    dy = 225
    c.setFont(FB, 11)
    c.setFillColor(PRIMARY)
    c.drawCentredString(W / 2, dy, "Context Accumulation")

    boxes = ["Meeting 1", "Meeting 2", "Meeting 3", "..."]
    bw, bh = 100, 40
    gap = 16
    total = len(boxes) * bw + (len(boxes) - 1) * gap
    bx = (W - total) / 2
    for i, label in enumerate(boxes):
        x = bx + i * (bw + gap)
        color = PRIMARY if i < 3 else MUTED
        rrect(c, x, dy - 60, bw, bh, r=6, fill=color)
        c.setFillColor(white)
        c.setFont(FB, 9)
        tw = c.stringWidth(label, FB, 9)
        c.drawString(x + (bw - tw) / 2, dy - 48, label)
        c.setFont(F, 7)
        c.drawCentredString(x + bw / 2, dy - 56, "summary")
        if i < len(boxes) - 1:
            arr(c, x + bw + 3, dy - 40, x + bw + gap - 3, dy - 40,
                color=TEXT2, w=0.8, hs=4)

    c.setFillColor(TEXT2)
    c.setFont(F, 9)
    c.drawCentredString(W / 2, dy - 78,
                        "Each new summary is appended to the context and used for the next one")

    # File structure
    fy = dy - 110
    rrect(c, 60, fy - 60, W - 120, 55, r=6, fill=Color(0, 0, 0, 0.04))
    c.setFillColor(TEXT2)
    c.setFont(FB, 9)
    c.drawString(75, fy - 12, "~/.summarizer/")
    c.setFont(F, 9)
    c.drawString(90, fy - 26, "recordings/standup_context.txt    - standup context")
    c.drawString(90, fy - 40, "recordings/client_x_context.txt   - client X context")
    c.drawString(90, fy - 54, "models/base/                      - Whisper models")


# ─── FAQ ────────────────────────────────────────────────────────────

def page_faq(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "FAQ & Tips")

    bs = ParagraphStyle("b", fontName=F, fontSize=10, leading=14.5, textColor=TEXT, spaceAfter=6)
    qs = ParagraphStyle("q", fontName=FB, fontSize=11, leading=15, textColor=TEXT,
                        spaceBefore=12, spaceAfter=3)

    qa = [
        ("Where do I get an API key?",
         "Gemini: aistudio.google.com - Create API Key. "
         "Claude: console.anthropic.com - API Keys. "
         "OpenAI: platform.openai.com - API Keys."),
        ("Formatting doesn't work when pasting to Slack?",
         "Use the <b>Copy Summary</b> button — it copies text with HTML markup, "
         "so bold and italic render correctly. Regular Cmd+C copies plain text only."),
        ("Which Whisper model should I choose?",
         "<b>base</b> (145 MB) — fast, good enough for clear speech. "
         "<b>medium</b> (1.5 GB) — best balance of speed and accuracy. "
         "<b>large-v3</b> (3.1 GB) — maximum accuracy, but slower."),
        ("Where is data stored?",
         "Config: ~/.summarizer/config.json. "
         "Contexts &amp; transcripts: ~/.summarizer/recordings/. "
         "Whisper models: ~/.summarizer/models/. "
         "Recorder logs: ~/.summarizer/recorder.log"),
        ("Is it safe?",
         "Audio is always processed <b>locally</b> by Whisper — it never leaves your Mac. "
         "With cloud models, only the text transcript is sent to the LLM. "
         "With <b>local models (Ollama)</b>, everything stays on your Mac — fully offline, "
         "no data ever leaves your machine."),
        ("Can I use a custom LLM endpoint?",
         "Yes — set the <b>Base URL</b> field in Settings to point to any "
         "OpenAI-compatible API endpoint."),
    ]

    fr = Frame(40, 60, W - 80, H - 120 - 60, showBoundary=0)
    story = []
    for question, answer in qa:
        story.append(Paragraph(question, qs))
        story.append(Paragraph(answer, bs))
    fr.addFromList(story, c)


# ─── Build ──────────────────────────────────────────────────────────

def main():
    c = canvas.Canvas(OUT, pagesize=A4)
    c.setTitle("Summarizer - User Guide")
    c.setAuthor("Summarizer")

    for fn in [page_cover, page_install, page_what_is, page_main_window,
               page_recording, page_settings_models, page_settings_instructions,
               page_settings_general, page_context, page_faq]:
        fn(c)
        c.showPage()

    c.save()
    print(f"Generated: {OUT}")


if __name__ == "__main__":
    main()
