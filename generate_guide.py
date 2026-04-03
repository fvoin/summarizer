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
    c.drawCentredString(W / 2, H / 2 - 75, "macOS  /  Whisper  /  Gemini  /  GPT-5  /  Ollama")

    c.setFont(F, 9)
    c.setFillColor(Color(1, 1, 1, 0.45))
    c.drawCentredString(W / 2, H / 2 - 105, "v1.18.4")


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
         "macOS will block it — right-click the app → Open → click Open again.\n"
         "Or: System Settings → Privacy & Security → scroll down → Open Anyway."),
        ("Set up an AI model",
         "Click the gear icon → Models tab.\n"
         "Cloud: enter your API key (free Gemini key at aistudio.google.com/apikey)\n"
         "Local: click Download on any Ollama model — no API key, fully offline."),
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
    rrect(c, 60, 42, W - 120, 68, r=6, fill=Color(0.29, 0.56, 0.85, 0.07))
    c.setFillColor(PRIMARY)
    c.setFont(FB, 9)
    c.drawString(75, 95, "First launch only (bypass macOS quarantine):")
    c.setFont(F, 9)
    c.setFillColor(TEXT)
    c.drawString(75, 81, "Option A:  Right-click the app → Open → click Open in the dialog")
    c.drawString(75, 67, "Option B:  System Settings → Privacy & Security → Open Anyway")
    c.drawString(75, 53, "This is required once for any app not from the App Store.")


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
        (bs, "<b>Meeting series</b> — accumulate meeting history for more accurate summaries "
             "across recurring meetings"),
        (bs, "<b>Meeting history</b> — SQLite database stores all transcripts, summaries, "
             "and contexts with browsable history"),
        (bs, "<b>Meeting series chat</b> — ask questions about your meeting history "
             "using any configured LLM"),
        (bs, "<b>Menu bar mode</b> — access recording controls from the macOS menu bar, "
             "app hides from Dock"),
        (bs, "<b>Recording Agent</b> — auto-record meetings from a web calendar backend"),
        (bs, "<b>Theme support</b> — Light, Dark, and Nord color schemes"),
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

    # History icon (clock)
    hx, hy = ox + ww - 40, ty + 5
    c.setFillColor(TEXT2)
    c.circle(hx, hy, 7, fill=0, stroke=1)
    c.setLineWidth(0.8)
    c.line(hx, hy, hx, hy + 3)
    c.line(hx, hy, hx + 2.5, hy)

    # Gear
    gx, gy = ox + ww - 22, ty + 5
    c.setFillColor(ACCENT)
    c.circle(gx, gy, 7, fill=1, stroke=0)
    c.setFillColor(BG)
    c.circle(gx, gy, 3, fill=1, stroke=0)

    # Meeting series row
    ct = ty - 12
    c.setFillColor(TEXT2)
    c.setFont(F, 7)
    c.drawString(ox + 14, ct, "Meeting series:")
    combo(c, ox + 72, ct - 4, 130, 14)
    c.setFillColor(PRIMARY)
    c.setFont(FB, 11)
    c.drawString(ox + 206, ct - 2, "+")
    # Edit pencil icon (drawn)
    c.saveState()
    c.setStrokeColor(HexColor("#b08800"))
    c.setLineWidth(1.2)
    px, py = ox + 226, ct + 1
    c.line(px, py - 6, px + 5, py + 1)
    c.line(px - 1, py - 7, px, py - 6)
    c.restoreState()
    # Chat bubble icon (drawn)
    c.saveState()
    c.setStrokeColor(PRIMARY)
    c.setFillColor(transparent)
    c.setLineWidth(0.8)
    bx, by = ox + 239, ct - 1
    p = c.beginPath()
    p.roundRect(bx, by, 8, 6, 1.5)
    c.drawPath(p, fill=0, stroke=1)
    c.line(bx + 2, by, bx + 1, by - 2)
    c.restoreState()
    # Delete X
    c.setFillColor(DANGER)
    c.setFont(FB, 11)
    c.drawString(ox + 254, ct - 2, "\u00d7")

    # This meeting context field
    mc_y = ct - 20
    c.setFillColor(TEXT2)
    c.setFont(F, 6.5)
    c.drawString(ox + 14, mc_y, "This meeting context")
    field(c, ox + 14, mc_y - 20, ww - 36, 18, "Sprint review, demo prep...")

    cy = mc_y - 20
    ch = ct - cy

    # Record
    ry = cy - 10
    rh = 28
    ry -= rh
    dbtn(c, ox + 8, ry, ww - 16, rh, "Start Recording", PRIMARY, white, 10)

    # Drop hint
    dry = ry - 14
    c.setFillColor(MUTED)
    c.setFont(F, 7)
    c.drawCentredString(ox + ww / 2, dry, "drag & drop or click to open audio / text files")

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
        ("  7/10 \u2014 Decision 8, Time 6, Action 7", False),
        ("  Email? No  Cost: ~300 EUR", False),
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

    # Annotations — evenly spaced on the right
    ann_top = oy + wh - 20
    ann_gap = 36

    ann("History + Settings", "Top bar icons",
        hx - 8, hy, ann_top)
    ann("Meeting series", "Per-series context + chat",
        ox + ww - 8, ct, ann_top - ann_gap)
    ann("Meeting context", "Per-session notes",
        ox + ww - 8, mc_y - 10, ann_top - ann_gap * 2)
    ann("Record", "Click to start recording",
        ox + ww - 8, ry + rh / 2, ann_top - ann_gap * 3)
    ann("Drop zone", "Open or drag files here",
        ox + ww - 8, dry + 4, ann_top - ann_gap * 4)
    ann("Result", "AI summary with formatting",
        ox + ww - 8, smy + smh / 2, ann_top - ann_gap * 5)
    ann("Actions", "Copy to clipboard / open file",
        ox + ww - 8, boty + 4, ann_top - ann_gap * 6)


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
         "(configurable in Settings, default 180 seconds / 3 minutes). "
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
            rrect(c, 80, y - 24, 140, 24, r=6, stroke=PRIMARY, sw=1.2)
            c.saveState()
            c.setFillColor(PRIMARY)
            c.setFont(FB, 9)
            tw = c.stringWidth("Start Recording", FB, 9)
            c.drawString(80 + (140 - tw) / 2, y - 17, "Start Recording")
            c.restoreState()
            arr(c, 224, y - 12, 240, y - 12, color=TEXT2, w=1, hs=4)
            rrect(c, 244, y - 24, 140, 24, r=6, stroke=DANGER, sw=1.2)
            c.saveState()
            c.setFillColor(DANGER)
            c.setFont(FB, 9)
            tw = c.stringWidth("Stop  1:23", FB, 9)
            c.drawString(244 + (140 - tw) / 2, y - 17, "Stop  1:23")
            c.restoreState()
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
    tabs = ["General", "Models", "Instructions", "Recording Agent"]
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
        ("GLM-4 9B", "Good", "5.5 GB", False, False),
        ("Gemma 3 12B QAT", "Better", "8.9 GB", False, False),
        ("Qwen 3 30B", "Great", "19 GB", False, False),
        ("GPT-OSS 20B", "Best", "12 GB", True, True),
    ]
    for name, quality, size, selected, downloaded in local_models:
        c.saveState()
        c.setStrokeColor(PRIMARY if selected else BORDER)
        c.setLineWidth(1)
        c.circle(sx + 24, ry + 3, 4.5, fill=0, stroke=1)
        if selected:
            c.setFillColor(PRIMARY)
            c.circle(sx + 24, ry + 3, 2.5, fill=1, stroke=0)
        c.setFillColor(TEXT if selected else TEXT2)
        c.setFont(FB if selected else F, 8.5)
        c.drawString(sx + 34, ry, name)
        c.setFont(F, 7.5)
        c.setFillColor(TEXT2)
        c.drawString(sx + 118, ry, f"— {quality} ({size})")
        if downloaded:
            c.setFillColor(SUCCESS)
            c.setFont(FB, 7.5)
            c.drawString(sx + sw - 90, ry, "Ready")
            c.setFillColor(PRIMARY)
            c.setFont(F, 7.5)
            c.drawString(sx + sw - 68, ry, "Test")
            c.setFillColor(DANGER)
            c.drawString(sx + sw - 44, ry, "Delete")
        else:
            c.setFillColor(PRIMARY)
            c.setFont(F, 7.5)
            c.drawString(sx + sw - 60, ry, "Download")
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
    ann("Local models (Ollama)", "Run AI on your Mac —\n100% offline, no API key.\nDownload, Test, or Delete.", H - 330)
    ann("Whisper models", "Speech-to-text (offline).\nLarger = more accurate\nbut slower.", H - 460)


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
        "\u2022 *Decision output*: X/10",
        "\u2022 *Time efficiency*: X/10",
        "\u2022 *Actionability*: X/10",
        "\u2022 *Final*: avg of 3 \u2014 X/10",
        "\u2022 *Could this have been an email?* Yes/No",
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
        ("Silence Timeout:", "180 sec",
         "Auto-stop after this much silence (3 min).\nAdaptive calibration measures mic noise first."),
        ("Input Device:", "Default",
         "Choose your microphone or loopback device.\nDefault uses the system input."),
        ("Save Audio:", "off",
         "When on, saves WAV recordings to disk.\nOff by default — recordings are temporary."),
        ("Sound:", "on",
         "Play a sound when the summary is ready."),
        ("Recordings Dir:", "~/.summarizer/recordings",
         "Where transcripts and context files are stored."),
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
        ry -= 10

    # Divider
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.4)
    c.line(sx + 10, ry + 4, sx + sw - 10, ry + 4)
    ry -= 12

    # Version + update
    c.setFillColor(TEXT2)
    c.setFont(F, 8.5)
    c.drawString(sx + 14, ry, "Version:")
    c.setFillColor(TEXT)
    c.setFont(FB, 8.5)
    c.drawString(sx + 70, ry, "v1.18.4")
    dbtn(c, sx + sw - 145, ry - 5, 130, 18, "Check for Updates", PRIMARY, white, 8)
    ry -= 28

    dbtn(c, sx + 14, ry - 5, 100, 18, "Open Log File", Color(0.43, 0.43, 0.45), white, 8)
    c.setFillColor(TEXT2)
    c.setFont(F, 8)
    c.drawString(sx + 124, ry, "~/.summarizer/summarizer.log")
    ry -= 24


# ─── Context ────────────────────────────────────────────────────────

def page_context(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Meeting Series")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    hs = ParagraphStyle("h", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (hs, "What is a Meeting Series?"),
        (bs, "A meeting series groups recurring meetings (standups, 1-on-1s, reviews) "
             "so Summarizer can track progress and action items across sessions. "
             "All data is stored in a local SQLite database."),
        (hs, "Creating a Series"),
        (bs, "Click <b>+</b> next to the Meeting series dropdown and enter a name. "
             "Use <b>edit (pencil)</b> to open the series editor, "
             "<b>chat (bubble)</b> to chat about the series, "
             "and <b>\u00d7</b> to delete it."),
        (hs, "Persistent Context"),
        (bs, "Each series has a persistent context — participants, goals, key terms. "
             "Edit it via the <b>edit (pencil)</b> series editor. "
             "This is always included in the LLM prompt for accurate summaries."),
        (hs, "This Meeting Context"),
        (bs, "Per-session details — today's agenda, attendees, specific topics. "
             "Always included in the prompt. Saved alongside the transcript and "
             "summary in the database."),
        (hs, "History & Budget"),
        (bs, "Each meeting's summary (with its meeting context) is stored in the database. "
             "The Context Limit (default 5000 chars) controls how much history "
             "is loaded into the prompt — persistent context and current meeting context "
             "are always included in full, remaining budget is filled with recent summaries."),
        (hs, "Series Chat"),
        (bs, "Click <b>chat (bubble)</b> to chat with an AI about the series. "
             "The model sees the persistent context and all recent meeting summaries. "
             "Ask questions like 'what did we decide about X?' or 'what are the open action items?'"),
    ]

    fr = Frame(40, 200, W - 80, H - 120 - 200, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # Database diagram
    fy = 170
    c.setFont(FB, 11)
    c.setFillColor(PRIMARY)
    c.drawCentredString(W / 2, fy, "Data Storage")

    rrect(c, 60, fy - 110, W - 120, 100, r=6, fill=Color(0, 0, 0, 0.04))
    c.setFont(FB, 8)
    c.setFillColor(PRIMARY)
    c.drawString(75, fy - 16, "SQLite database: ~/.summarizer/summarizer.db")
    c.setFont(F, 8.5)
    c.setFillColor(TEXT2)
    c.drawString(75, fy - 34, "contexts table — series name, persistent context")
    c.drawString(75, fy - 48, "meetings table — transcript, summary, meeting context,")
    c.drawString(75, fy - 62, "                  duration, date, linked to series")
    c.setFont(F, 8)
    c.setFillColor(MUTED)
    c.drawString(75, fy - 82, "Existing _context.txt files are auto-migrated on first run.")
    c.drawString(75, fy - 96, "Browse all data via the History dialog (\U0001f553 icon in top bar).")


# ─── Menu Bar ──────────────────────────────────────────────────

def page_menu_bar(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Menu Bar & Recording Agent")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    hs = ParagraphStyle("h", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (hs, "Menu Bar Icon"),
        (bs, "Summarizer places an icon in the macOS menu bar. Clicking it reveals a compact "
             "menu with <b>Start/Stop Recording</b>, <b>Show Summarizer</b>, "
             "<b>Settings</b>, and <b>Quit</b>."),
        (hs, "Hide from Dock"),
        (bs, "When minimized to the menu bar tray, the app hides from the Dock. "
             "Click the menu bar icon and choose <b>Show Summarizer</b> to bring it back."),
        (hs, "Single Instance"),
        (bs, "Launching Summarizer again while it is already running does not open a "
             "second copy. Instead, the existing window is brought to the front."),
        (hs, "Recording Agent"),
        (bs, "The Recording Agent automatically starts recording when an upcoming meeting "
             "is detected from a web calendar backend. Configure the backend URL and "
             "behavior in <b>Settings \u2192 Recording Agent</b>."),
        (bs, "When a meeting is about to start, the agent activates recording and stops "
             "when the meeting ends. The transcript and summary are generated automatically, "
             "just like a manual recording session."),
    ]

    fr = Frame(40, 220, W - 80, H - 120 - 220, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # Menu mockup
    mx = 160
    my = 100
    mw = 180
    mh = 90
    rrect(c, mx, my, mw, mh, r=6, fill=white, stroke=BORDER, sw=0.8)

    items = [
        ("Start Recording", PRIMARY),
        ("Show Summarizer", TEXT),
        ("Settings", TEXT),
        ("Quit", DANGER),
    ]
    iy = my + mh - 16
    for label, color in items:
        c.setFillColor(color)
        c.setFont(F, 9)
        c.drawString(mx + 12, iy, label)
        iy -= 18

    # Label
    c.setFillColor(TEXT2)
    c.setFont(F, 9)
    c.drawCentredString(mx + mw / 2, my - 14, "Menu bar dropdown")


# ─── History ───────────────────────────────────────────────────

def page_history(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "Meeting History & Series")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    hs = ParagraphStyle("h", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (hs, "Meeting History"),
        (bs, "Click the <b>clock icon</b> in the top bar to open the Meeting History dialog. "
             "It shows a searchable, scrollable list of all past meetings with their date, "
             "series, transcript, and summary. All data is stored in a local SQLite database."),
        (hs, "Meeting Series Editor"),
        (bs, "Click the <b>edit button</b> (pencil) next to the series dropdown to open the "
             "series editor. Here you can rename series, update general context, review "
             "accumulated history, and delete series you no longer need."),
        (hs, "Series Chat"),
        (bs, "Click the <b>chat icon</b> (chat bubble) next to the series dropdown to open a "
             "chat window scoped to that meeting series. Ask questions about past meetings, "
             "action items, decisions, or trends \u2014 the LLM has access to the full series "
             "history stored in the database."),
        (hs, "SQLite Storage"),
        (bs, "All transcripts, summaries, meeting contexts, and series data are stored in a "
             "local SQLite database at <b>~/.summarizer/summarizer.db</b>. This replaces the "
             "older plain-text context files and provides faster search, reliable history, "
             "and structured queries for the series chat feature."),
    ]

    fr = Frame(40, 120, W - 80, H - 120 - 120, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # DB structure hint
    rrect(c, 60, 50, W - 120, 55, r=6, fill=Color(0, 0, 0, 0.04))
    c.setFillColor(TEXT2)
    c.setFont(FB, 9)
    c.drawString(75, 88, "~/.summarizer/")
    c.setFont(F, 9)
    c.drawString(90, 74, "summarizer.db     \u2014 SQLite database (meetings, series, contexts)")
    c.drawString(90, 60, "recordings/       \u2014 audio files (if Save Audio is enabled)")


# ─── FAQ ────────────────────────────────────────────────────────────

def page_faq(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "FAQ & Tips")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    qs = ParagraphStyle("q", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

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
         "Database: ~/.summarizer/summarizer.db (meetings, contexts, transcripts). "
         "Config: ~/.summarizer/config.json. "
         "Whisper models: ~/.summarizer/models/. "
         "App log: ~/.summarizer/summarizer.log."),
        ("Is it safe?",
         "Audio is always processed <b>locally</b> by Whisper — it never leaves your Mac. "
         "With cloud models, only the text transcript is sent to the LLM. "
         "With <b>local models (Ollama)</b>, everything stays on your Mac — fully offline."),
        ("How do I use the menu bar mode?",
         "Enable <b>Menu bar icon</b> in Settings > Recording Agent. "
         "Close the window — the app stays in the menu bar. "
         "Click the tray icon or launch the app again to show the window."),
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
               page_recording, page_menu_bar, page_history,
               page_settings_models, page_settings_instructions,
               page_settings_general, page_context, page_faq]:
        fn(c)
        c.showPage()

    c.save()
    print(f"Generated: {OUT}")


if __name__ == "__main__":
    main()
