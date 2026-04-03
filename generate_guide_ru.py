#!/usr/bin/env python3
"""Generate a PDF user guide for the Summarizer app (Russian version)."""

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

OUT = "Summarizer_Guide_RU.pdf"


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
    c.drawCentredString(W / 2, H / 2 - 16, "\u0420\u0443\u043a\u043e\u0432\u043e\u0434\u0441\u0442\u0432\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f")

    c.setFont(F, 12)
    c.setFillColor(Color(1, 1, 1, 0.7))
    c.drawCentredString(W / 2, H / 2 - 55, "\u0417\u0430\u043f\u0438\u0441\u044c, \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f \u0438 \u0441\u0443\u043c\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0432\u0441\u0442\u0440\u0435\u0447 \u0441 \u043f\u043e\u043c\u043e\u0449\u044c\u044e \u0418\u0418")
    c.drawCentredString(W / 2, H / 2 - 75, "macOS  /  Whisper  /  Gemini  /  GPT-5  /  Ollama")

    c.setFont(F, 9)
    c.setFillColor(Color(1, 1, 1, 0.45))
    c.drawCentredString(W / 2, H / 2 - 105, "v1.18.4")


# ─── Installation ───────────────────────────────────────────────────

def page_install(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u0423\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "\u041e\u0434\u043d\u043e\u0440\u0430\u0437\u043e\u0432\u0430\u044f \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u2014 \u0437\u0430\u043d\u0438\u043c\u0430\u0435\u0442 \u043e\u043a\u043e\u043b\u043e \u043c\u0438\u043d\u0443\u0442\u044b.")

    # Steps
    steps = [
        ("\u0421\u043a\u0430\u0447\u0430\u0439\u0442\u0435 Summarizer.dmg",
         "\u041f\u0435\u0440\u0435\u0439\u0434\u0438\u0442\u0435 \u043d\u0430 github.com/fvoin/summarizer/releases \u0438 \u0441\u043a\u0430\u0447\u0430\u0439\u0442\u0435 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 DMG-\u0444\u0430\u0439\u043b."),
        ("\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 DMG",
         "\u0414\u0432\u0430\u0436\u0434\u044b \u043a\u043b\u0438\u043a\u043d\u0438\u0442\u0435 \u043f\u043e \u0441\u043a\u0430\u0447\u0430\u043d\u043d\u043e\u043c\u0443 \u0444\u0430\u0439\u043b\u0443. \u041e\u0442\u043a\u0440\u043e\u0435\u0442\u0441\u044f \u043e\u043a\u043d\u043e \u0441 \u0438\u043a\u043e\u043d\u043a\u043e\u0439 Summarizer \u0438 \u043f\u0430\u043f\u043a\u043e\u0439 Applications."),
        ("\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0432 Applications",
         "\u041f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0438\u043a\u043e\u043d\u043a\u0443 Summarizer \u0432 \u044f\u0440\u043b\u044b\u043a \u043f\u0430\u043f\u043a\u0438 Applications."),
        ("\u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u0438 \u0440\u0430\u0437\u0440\u0435\u0448\u0438\u0442\u0435",
         "\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 Summarizer \u0438\u0437 Applications (Launchpad \u0438\u043b\u0438 Finder).\n"
         "macOS \u0437\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u0443\u0435\u0442 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u2014 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u041f\u041a\u041c \u043d\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0438 \u2192 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u2192 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0435\u0449\u0451 \u0440\u0430\u0437.\n"
         "\u0418\u043b\u0438: \u0421\u0438\u0441\u0442\u0435\u043c\u043d\u044b\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2192 \u041a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u0438 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u044c \u2192 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0432 \u043b\u044e\u0431\u043e\u043c \u0441\u043b\u0443\u0447\u0430\u0435."),
        ("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u0442\u0435 \u043c\u043e\u0434\u0435\u043b\u044c \u0418\u0418",
         "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u0438\u043a\u043e\u043d\u043a\u0443 \u0448\u0435\u0441\u0442\u0435\u0440\u0451\u043d\u043a\u0438 \u2192 \u0432\u043a\u043b\u0430\u0434\u043a\u0430 \u041c\u043e\u0434\u0435\u043b\u0438.\n"
         "\u041e\u0431\u043b\u0430\u043a\u043e: \u0432\u0432\u0435\u0434\u0438\u0442\u0435 API-\u043a\u043b\u044e\u0447 (\u0431\u0435\u0441\u043f\u043b\u0430\u0442\u043d\u044b\u0439 \u043a\u043b\u044e\u0447 Gemini \u043d\u0430 aistudio.google.com/apikey)\n"
         "\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u043e: \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u0421\u043a\u0430\u0447\u0430\u0442\u044c \u0443 \u043b\u044e\u0431\u043e\u0439 \u043c\u043e\u0434\u0435\u043b\u0438 Ollama \u2014 \u0431\u0435\u0437 API-\u043a\u043b\u044e\u0447\u0430, \u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e \u043e\u0444\u043b\u0430\u0439\u043d."),
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
    c.drawString(75, 95, "\u0422\u043e\u043b\u044c\u043a\u043e \u043f\u0440\u0438 \u043f\u0435\u0440\u0432\u043e\u043c \u0437\u0430\u043f\u0443\u0441\u043a\u0435 (\u043e\u0431\u0445\u043e\u0434 \u043a\u0430\u0440\u0430\u043d\u0442\u0438\u043d\u0430 macOS):")
    c.setFont(F, 9)
    c.setFillColor(TEXT)
    c.drawString(75, 81, "\u0412\u0430\u0440\u0438\u0430\u043d\u0442 A:  \u041f\u041a\u041c \u043d\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0438 \u2192 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u2192 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0432 \u0434\u0438\u0430\u043b\u043e\u0433\u0435")
    c.drawString(75, 67, "\u0412\u0430\u0440\u0438\u0430\u043d\u0442 B:  \u0421\u0438\u0441\u0442\u0435\u043c\u043d\u044b\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2192 \u041a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c \u0438 \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e\u0441\u0442\u044c \u2192 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0432 \u043b\u044e\u0431\u043e\u043c \u0441\u043b\u0443\u0447\u0430\u0435")
    c.drawString(75, 53, "\u042d\u0442\u043e \u043d\u0443\u0436\u043d\u043e \u0441\u0434\u0435\u043b\u0430\u0442\u044c \u043e\u0434\u0438\u043d \u0440\u0430\u0437 \u0434\u043b\u044f \u043b\u044e\u0431\u043e\u0433\u043e \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u044f \u043d\u0435 \u0438\u0437 App Store.")


# ─── What Is ────────────────────────────────────────────────────────

def page_what_is(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u0427\u0442\u043e \u0442\u0430\u043a\u043e\u0435 Summarizer?")

    bs = ParagraphStyle("b", fontName=F, fontSize=11, leading=16, textColor=TEXT, spaceAfter=8)
    hs = ParagraphStyle("h", fontName=FB, fontSize=13, leading=18, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (bs, "<b>Summarizer</b> \u2014 \u044d\u0442\u043e \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0434\u043b\u044f macOS, \u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0437\u0430\u043f\u0438\u0441\u044b\u0432\u0430\u0435\u0442, "
             "\u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u0431\u0438\u0440\u0443\u0435\u0442 \u0438 \u0441\u0443\u043c\u043c\u0438\u0440\u0443\u0435\u0442 \u0432\u0441\u0442\u0440\u0435\u0447\u0438 \u0438 \u0430\u0443\u0434\u0438\u043e\u0437\u0430\u043f\u0438\u0441\u0438."),
        (bs, "\u041e\u043d\u043e \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0435\u0442 <b>Whisper</b> \u0434\u043b\u044f \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0432\u0430\u043d\u0438\u044f \u0440\u0435\u0447\u0438 (\u0430\u0443\u0434\u0438\u043e \u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u043f\u043e\u043a\u0438\u0434\u0430\u0435\u0442 "
             "\u0432\u0430\u0448 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440) \u0438 LLM-\u043c\u043e\u0434\u0435\u043b\u0438 (Gemini, Claude, OpenAI) \u0434\u043b\u044f \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u0438 "
             "\u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0441\u0430\u043c\u043c\u0430\u0440\u0438."),
        (hs, "\u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u0438"),
        (bs, "<b>\u0417\u0430\u043f\u0438\u0441\u044c \u0430\u0443\u0434\u0438\u043e</b> \u2014 \u0437\u0430\u043f\u0438\u0441\u044c \u0441 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0430 \u0441 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438\u043c "
             "\u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0435\u043d\u0438\u0435\u043c \u0442\u0438\u0448\u0438\u043d\u044b \u0438 \u0430\u0432\u0442\u043e\u0441\u0442\u043e\u043f\u043e\u043c"),
        (bs, "<b>\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u0430\u044f \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f</b> \u2014 \u043c\u043e\u0434\u0435\u043b\u0438 Whisper (tiny \u2014 large-v3) "
             "\u0440\u0430\u0431\u043e\u0442\u0430\u044e\u0442 \u043f\u0440\u044f\u043c\u043e \u043d\u0430 \u0432\u0430\u0448\u0435\u043c Mac, \u043e\u0431\u043b\u0430\u043a\u043e \u043d\u0435 \u043d\u0443\u0436\u043d\u043e"),
        (bs, "<b>\u0418\u0418-\u0441\u0443\u043c\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435</b> \u2014 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u0432\u044b\u0432\u043e\u0434: \u041e\u0431\u0437\u043e\u0440, \u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u044f, "
             "\u0417\u0430\u0434\u0430\u0447\u0438, \u0422\u0435\u043c\u044b \u043e\u0431\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u044f, \u0420\u0438\u0441\u043a\u0438 \u0438 \u041e\u0446\u0435\u043d\u043a\u0430 \u0432\u0441\u0442\u0440\u0435\u0447\u0438 \u0441 \u043e\u0446\u0435\u043d\u043a\u043e\u0439 \u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u0438"),
        (bs, "<b>\u041f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e \u043e\u0444\u043b\u0430\u0439\u043d-\u0440\u0435\u0436\u0438\u043c</b> \u2014 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 LLM (Llama, Gemma, Qwen) \u0447\u0435\u0440\u0435\u0437 Ollama "
             "\u0434\u043b\u044f 100% \u043e\u0444\u043b\u0430\u0439\u043d-\u0440\u0430\u0431\u043e\u0442\u044b \u2014 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043f\u043e\u043a\u0438\u0434\u0430\u0435\u0442 \u0432\u0430\u0448 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440"),
        (bs, "<b>\u041f\u0440\u043e\u0444\u0438\u043b\u0438 \u0438\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0439</b> \u2014 \u0441\u043e\u0437\u0434\u0430\u0432\u0430\u0439\u0442\u0435 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u043f\u0440\u043e\u043c\u043f\u0442-\u043f\u0440\u043e\u0444\u0438\u043b\u0435\u0439 \u0438 \u043f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0430\u0439\u0442\u0435\u0441\u044c "
             "\u043c\u0435\u0436\u0434\u0443 \u043d\u0438\u043c\u0438 \u0434\u043b\u044f \u0440\u0430\u0437\u043d\u044b\u0445 \u0442\u0438\u043f\u043e\u0432 \u0432\u0441\u0442\u0440\u0435\u0447 (\u0441\u0442\u0435\u043d\u0434\u0430\u043f, \u0440\u0435\u0432\u044c\u044e, 1-\u043d\u0430-1...)"),
        (bs, "<b>\u0421\u0435\u0440\u0438\u0438 \u0432\u0441\u0442\u0440\u0435\u0447</b> \u2014 \u043d\u0430\u043a\u0430\u043f\u043b\u0438\u0432\u0430\u0439\u0442\u0435 \u0438\u0441\u0442\u043e\u0440\u0438\u044e \u0432\u0441\u0442\u0440\u0435\u0447 \u0434\u043b\u044f \u0431\u043e\u043b\u0435\u0435 \u0442\u043e\u0447\u043d\u044b\u0445 \u0441\u0430\u043c\u043c\u0430\u0440\u0438 "
             "\u043f\u043e \u0440\u0435\u0433\u0443\u043b\u044f\u0440\u043d\u044b\u043c \u0432\u0441\u0442\u0440\u0435\u0447\u0430\u043c"),
        (bs, "<b>\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0432\u0441\u0442\u0440\u0435\u0447</b> \u2014 \u0431\u0430\u0437\u0430 \u0434\u0430\u043d\u043d\u044b\u0445 SQLite \u0445\u0440\u0430\u043d\u0438\u0442 \u0432\u0441\u0435 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442\u044b, \u0441\u0430\u043c\u043c\u0430\u0440\u0438 "
             "\u0438 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u044b \u0441 \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e\u0441\u0442\u044c\u044e \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0430 \u0438\u0441\u0442\u043e\u0440\u0438\u0438"),
        (bs, "<b>\u0427\u0430\u0442 \u043f\u043e \u0441\u0435\u0440\u0438\u0438 \u0432\u0441\u0442\u0440\u0435\u0447</b> \u2014 \u0437\u0430\u0434\u0430\u0432\u0430\u0439\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u043f\u043e \u0438\u0441\u0442\u043e\u0440\u0438\u0438 \u0432\u0441\u0442\u0440\u0435\u0447 "
             "\u0441 \u043f\u043e\u043c\u043e\u0449\u044c\u044e \u043b\u044e\u0431\u043e\u0439 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043d\u043d\u043e\u0439 LLM"),
        (bs, "<b>\u0420\u0435\u0436\u0438\u043c \u043c\u0435\u043d\u044e-\u0431\u0430\u0440\u0430</b> \u2014 \u0434\u043e\u0441\u0442\u0443\u043f \u043a \u0443\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u044e \u0437\u0430\u043f\u0438\u0441\u044c\u044e \u0438\u0437 \u0441\u0442\u0440\u043e\u043a\u0438 \u043c\u0435\u043d\u044e macOS, "
             "\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0441\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0438\u0437 Dock"),
        (bs, "<b>\u0410\u0433\u0435\u043d\u0442 \u0437\u0430\u043f\u0438\u0441\u0438</b> \u2014 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0437\u0430\u043f\u0438\u0441\u044c \u0432\u0441\u0442\u0440\u0435\u0447 \u0438\u0437 \u0432\u0435\u0431-\u043a\u0430\u043b\u0435\u043d\u0434\u0430\u0440\u044f"),
        (bs, "<b>\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430 \u0442\u0435\u043c</b> \u2014 \u0441\u0432\u0435\u0442\u043b\u0430\u044f, \u0442\u0451\u043c\u043d\u0430\u044f \u0438 Nord \u0446\u0432\u0435\u0442\u043e\u0432\u044b\u0435 \u0441\u0445\u0435\u043c\u044b"),
        (bs, "<b>\u0413\u043e\u0442\u043e\u0432\u043e \u0434\u043b\u044f Slack</b> \u2014 \u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0430\u043c\u043c\u0430\u0440\u0438 \u0432\u0441\u0442\u0430\u0432\u043b\u044f\u0435\u0442 \u0442\u0435\u043a\u0441\u0442 \u0441 \u0444\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435\u043c "
             "\u0436\u0438\u0440\u043d\u044b\u0439/\u043a\u0443\u0440\u0441\u0438\u0432, \u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e \u0432 Slack"),
    ]

    fr = Frame(40, 320, W - 80, H - 120 - 320, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # Flow
    fy = 270
    c.setFont(FB, 12)
    c.setFillColor(PRIMARY)
    c.drawCentredString(W / 2, fy + 20, "\u0420\u0430\u0431\u043e\u0447\u0438\u0439 \u043f\u0440\u043e\u0446\u0435\u0441\u0441")

    steps = [
        ("\u0417\u0430\u043f\u0438\u0441\u044c", PRIMARY),
        ("\u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f", ACCENT),
        ("\u0421\u0443\u043c\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435", SUCCESS),
        ("\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435", PRIMARY),
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
    c.drawCentredString(W / 2, fy - 56, "\u0412\u0435\u0441\u044c \u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u0437\u0430\u043d\u0438\u043c\u0430\u0435\u0442 \u043e\u0442 \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u0438\u0445 \u0441\u0435\u043a\u0443\u043d\u0434 \u0434\u043e \u043f\u0430\u0440\u044b \u043c\u0438\u043d\u0443\u0442")

    # Privacy note
    rrect(c, 50, 82, W - 100, 105, r=8, fill=Color(0.29, 0.56, 0.85, 0.07))
    c.setFillColor(PRIMARY)
    c.setFont(FB, 10)
    c.drawString(65, 168, "\u041a\u043e\u043d\u0444\u0438\u0434\u0435\u043d\u0446\u0438\u0430\u043b\u044c\u043d\u043e\u0441\u0442\u044c")
    c.setFont(F, 9.5)
    c.setFillColor(TEXT)
    lines = [
        "\u0410\u0443\u0434\u0438\u043e \u043e\u0431\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u041b\u041e\u041a\u0410\u041b\u042c\u041d\u041e \u0447\u0435\u0440\u0435\u0437 Whisper \u2014 \u043e\u043d\u043e \u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u043f\u043e\u043a\u0438\u0434\u0430\u0435\u0442 \u0432\u0430\u0448 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440.",
        "\u041f\u0440\u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0438 \u043e\u0431\u043b\u0430\u0447\u043d\u044b\u0445 \u043c\u043e\u0434\u0435\u043b\u0435\u0439 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u0430\u044f \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f.",
        "\u0421 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u043c\u0438 \u043c\u043e\u0434\u0435\u043b\u044f\u043c\u0438 (Ollama) \u0432\u0441\u0451 \u043e\u0441\u0442\u0430\u0451\u0442\u0441\u044f \u043d\u0430 \u0432\u0430\u0448\u0435\u043c Mac \u2014 \u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e \u043e\u0444\u043b\u0430\u0439\u043d.",
        "\u0414\u0430\u043d\u043d\u044b\u0435 \u043d\u0435 \u0441\u043e\u0431\u0438\u0440\u0430\u044e\u0442\u0441\u044f. \u0410\u043a\u043a\u0430\u0443\u043d\u0442\u044b \u043d\u0435 \u043d\u0443\u0436\u043d\u044b. \u0412\u0441\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u043f\u0440\u0438\u043d\u0430\u0434\u043b\u0435\u0436\u0430\u0442 \u0432\u0430\u043c.",
    ]
    ly = 150
    for line in lines:
        c.drawString(65, ly, line)
        ly -= 16


# ─── Main Window ────────────────────────────────────────────────────

def page_main_window(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u0413\u043b\u0430\u0432\u043d\u043e\u0435 \u043e\u043a\u043d\u043e")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "\u0412\u0441\u0451 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0438\u0437 \u043e\u0434\u043d\u043e\u0433\u043e \u043e\u043a\u043d\u0430.")

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
    c.drawString(ox + 14, ct, "\u0421\u0435\u0440\u0438\u044f \u0432\u0441\u0442\u0440\u0435\u0447:")
    combo(c, ox + 72, ct - 4, 130, 14)
    c.setFillColor(PRIMARY)
    c.setFont(FB, 11)
    c.drawString(ox + 206, ct - 2, "+")
    c.setFillColor(HexColor("#b08800"))
    c.setFont(F, 12)
    c.drawString(ox + 222, ct - 2, "\u270f")
    # Chat bubble icon
    c.setFillColor(PRIMARY)
    c.setFont(F, 10)
    c.drawString(ox + 238, ct - 2, "\U0001f4ac")
    c.setFillColor(DANGER)
    c.setFont(FB, 11)
    c.drawString(ox + 254, ct - 2, "\u00d7")

    # This meeting context field
    mc_y = ct - 20
    c.setFillColor(TEXT2)
    c.setFont(F, 6.5)
    c.drawString(ox + 14, mc_y, "\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u044d\u0442\u043e\u0439 \u0432\u0441\u0442\u0440\u0435\u0447\u0438")
    field(c, ox + 14, mc_y - 20, ww - 36, 18, "\u041e\u0431\u0437\u043e\u0440 \u0441\u043f\u0440\u0438\u043d\u0442\u0430, \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430 \u0434\u0435\u043c\u043e...")

    cy = mc_y - 20
    ch = ct - cy

    # Record
    ry = cy - 10
    rh = 28
    ry -= rh
    dbtn(c, ox + 8, ry, ww - 16, rh, "\u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c", PRIMARY, white, 10)

    # Drop hint
    dry = ry - 14
    c.setFillColor(MUTED)
    c.setFont(F, 7)
    c.drawCentredString(ox + ww / 2, dry, "\u043f\u0435\u0440\u0435\u0442\u0430\u0449\u0438\u0442\u0435 \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u0434\u043b\u044f \u043e\u0442\u043a\u0440\u044b\u0442\u0438\u044f \u0430\u0443\u0434\u0438\u043e / \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u044b\u0445 \u0444\u0430\u0439\u043b\u043e\u0432")

    # Status
    sty = dry - 18
    rrect(c, ox + 10, sty - 2, 36, 13, r=6, fill=Color(0.18, 0.54, 0.31, 0.12))
    c.setFillColor(SUCCESS)
    c.setFont(FB, 7)
    c.drawString(ox + 16, sty + 1, "\u0413\u043e\u0442\u043e\u0432\u043e")

    # Summary
    smt = sty - 10
    smh = smt - oy - 32
    smy = smt - smh
    rrect(c, ox + 8, smy, ww - 16, smh, r=5, fill=white, stroke=BORDER, sw=0.3)
    lines = [
        ("\U0001f5d2\ufe0f \u041e\u0431\u0437\u043e\u0440", True),
        ("  \u0421\u0438\u043d\u043a \u043f\u043e \u0434\u043e\u0440\u043e\u0436\u043d\u043e\u0439 \u043a\u0430\u0440\u0442\u0435 Q3; \u043e\u0434\u043e\u0431\u0440\u0435\u043d \u043d\u043e\u0432\u044b\u0439 \u0434\u0430\u0448\u0431\u043e\u0440\u0434.", False),
        ("", False),
        ("\U0001f3af \u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u044f", True),
        ("  \u0420\u0435\u0434\u0438\u0437\u0430\u0439\u043d \u0434\u0430\u0448\u0431\u043e\u0440\u0434\u0430 \u043e\u0434\u043e\u0431\u0440\u0435\u043d \u0434\u043b\u044f v2.4", False),
        ("", False),
        ("\u2705 \u0417\u0430\u0434\u0430\u0447\u0438", True),
        ("  \u041c\u0430\u0448\u0430 \u2014 \u043f\u0440\u043e\u0442\u043e\u0442\u0438\u043f \u2014 \u043f\u044f\u0442\u043d\u0438\u0446\u0430", False),
        ("  \u041f\u0435\u0442\u044f \u2014 \u0440\u0435\u0432\u044c\u044e API \u2014 \u0441\u043b\u0435\u0434. \u0441\u043f\u0440\u0438\u043d\u0442", False),
        ("", False),
        ("\U0001f4ca \u041e\u0446\u0435\u043d\u043a\u0430 \u0432\u0441\u0442\u0440\u0435\u0447\u0438", True),
        ("  7/10 \u2014 \u0420\u0435\u0448\u0435\u043d\u0438\u044f 8, \u0412\u0440\u0435\u043c\u044f 6, \u0417\u0430\u0434\u0430\u0447\u0438 7", False),
        ("  Email? \u041d\u0435\u0442  \u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c: ~300 EUR", False),
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
    c.drawString(ox + 14, boty, "\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0430\u043c\u043c\u0430\u0440\u0438")
    c.drawString(ox + 120, boty, "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442")

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

    ann("\u0418\u0441\u0442\u043e\u0440\u0438\u044f", "\u041f\u0440\u043e\u0441\u043c\u043e\u0442\u0440 \u043f\u0440\u043e\u0448\u043b\u044b\u0445 \u0432\u0441\u0442\u0440\u0435\u0447",
        hx - 8, hy, oy + wh - 35)
    ann("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", "LLM, Whisper, API-\u043a\u043b\u044e\u0447\u0438",
        gx - 8, gy, oy + wh - 55)
    ann("\u0421\u0435\u0440\u0438\u044f \u0432\u0441\u0442\u0440\u0435\u0447", "\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442 \u0441\u0435\u0440\u0438\u0438 + \u0447\u0430\u0442",
        ox + ww - 8, cy + ch / 2, cy + ch / 2 + 6)
    ann("\u0417\u0430\u043f\u0438\u0441\u044c", "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u0434\u043b\u044f \u043d\u0430\u0447\u0430\u043b\u0430 \u0437\u0430\u043f\u0438\u0441\u0438",
        ox + ww - 8, ry + rh / 2, ry + rh / 2 + 6)
    ann("\u0421\u0442\u0430\u0442\u0443\u0441", "\u0426\u0432\u0435\u0442\u043e\u0432\u043e\u0439 \u0438\u043d\u0434\u0438\u043a\u0430\u0442\u043e\u0440 \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u044f",
        ox + 48, sty + 4, sty + 4)
    ann("\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442", "\u0418\u0418-\u0441\u0430\u043c\u043c\u0430\u0440\u0438 \u0441 \u0444\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435\u043c",
        ox + ww - 8, smy + smh / 2, smy + smh / 2 + 6)
    ann("\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u044f", "\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c / \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0444\u0430\u0439\u043b",
        ox + ww - 8, boty + 4, boty)


# ─── Recording ──────────────────────────────────────────────────────

def page_recording(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u0417\u0430\u043f\u0438\u0441\u044c \u0430\u0443\u0434\u0438\u043e")

    y = H - 95

    steps = [
        ("\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c",
         "\u041a\u043d\u043e\u043f\u043a\u0430 \u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0441\u044f \u043a\u0440\u0430\u0441\u043d\u043e\u0439 \u0438 \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0442\u0430\u0439\u043c\u0435\u0440. \u041f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0437\u0430\u043f\u0438\u0441\u044b\u0432\u0430\u0435\u0442 "
         "\u0430\u0443\u0434\u0438\u043e \u0441 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e \u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u0430 \u0432\u0432\u043e\u0434\u0430 (\u043d\u0430\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0432 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445).",
         True),
        ("\u0410\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0430",
         "\u0417\u0430\u043f\u0438\u0441\u044c \u043e\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043f\u043e\u0441\u043b\u0435 \u043f\u0435\u0440\u0438\u043e\u0434\u0430 \u0442\u0438\u0448\u0438\u043d\u044b "
         "(\u043d\u0430\u0441\u0442\u0440\u0430\u0438\u0432\u0430\u0435\u0442\u0441\u044f \u0432 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445, \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e 180 \u0441\u0435\u043a\u0443\u043d\u0434 / 3 \u043c\u0438\u043d\u0443\u0442\u044b). "
         "\u0422\u0430\u043a\u0436\u0435 \u043c\u043e\u0436\u043d\u043e \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0432\u0440\u0443\u0447\u043d\u0443\u044e, \u043d\u0430\u0436\u0430\u0432 \u043a\u0440\u0430\u0441\u043d\u0443\u044e \u043a\u043d\u043e\u043f\u043a\u0443.",
         False),
        ("\u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f",
         "\u041f\u043e\u0441\u043b\u0435 \u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043a\u0438 Whisper \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0451\u0442 \u0440\u0435\u0447\u044c. "
         "\u041c\u043e\u0434\u0435\u043b\u044c \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e \u2014 \u0430\u0443\u0434\u0438\u043e \u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u043f\u043e\u043a\u0438\u0434\u0430\u0435\u0442 \u0432\u0430\u0448 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440. "
         "\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441 \u043e\u0442\u043e\u0431\u0440\u0430\u0436\u0430\u0435\u0442\u0441\u044f \u0446\u0432\u0435\u0442\u043e\u0432\u044b\u043c \u0438\u043d\u0434\u0438\u043a\u0430\u0442\u043e\u0440\u043e\u043c \u0441\u0442\u0430\u0442\u0443\u0441\u0430.",
         False),
        ("\u0421\u0430\u043c\u043c\u0430\u0440\u0438 \u0438 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442",
         "LLM \u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u0435\u0442 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435 \u0441\u0430\u043c\u043c\u0430\u0440\u0438. \u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0430\u043c\u043c\u0430\u0440\u0438 "
         "\u0434\u043b\u044f \u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f \u0441 \u0444\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435\u043c, \u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u0432 Slack. "
         "\u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0435\u0442\u0441\u044f \u0432 \u0444\u0430\u0439\u043b, \u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u043c\u043e\u0436\u043d\u043e \u043e\u0442\u043a\u0440\u044b\u0442\u044c.",
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
            tw = c.stringWidth("\u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c", FB, 9)
            c.drawString(80 + (140 - tw) / 2, y - 17, "\u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c")
            c.restoreState()
            arr(c, 224, y - 12, 240, y - 12, color=TEXT2, w=1, hs=4)
            rrect(c, 244, y - 24, 140, 24, r=6, stroke=DANGER, sw=1.2)
            c.saveState()
            c.setFillColor(DANGER)
            c.setFont(FB, 9)
            tw = c.stringWidth("\u0421\u0442\u043e\u043f  1:23", FB, 9)
            c.drawString(244 + (140 - tw) / 2, y - 17, "\u0421\u0442\u043e\u043f  1:23")
            c.restoreState()
            y -= 32
        y -= 18

    # Tips
    th = 70
    ty = y - th - 10
    rrect(c, 40, ty, W - 80, th, r=8, fill=Color(0.29, 0.56, 0.85, 0.07))
    c.setFillColor(PRIMARY)
    c.setFont(FB, 10)
    c.drawString(55, ty + th - 16, "\u0421\u043e\u0432\u0435\u0442\u044b")
    c.setFont(F, 9)
    c.setFillColor(TEXT)
    tips = [
        "- Whisper \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e \u2014 \u0430\u0443\u0434\u0438\u043e \u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0432 \u043e\u0431\u043b\u0430\u043a\u043e",
        "- \u0414\u043b\u044f \u043b\u0443\u0447\u0448\u0435\u0433\u043e \u043a\u0430\u0447\u0435\u0441\u0442\u0432\u0430 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 \u043c\u043e\u0434\u0435\u043b\u044c medium \u0438\u043b\u0438 large-v3",
        "- \u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435 \u0430\u0443\u0434\u0438\u043e\u0444\u0430\u0439\u043b\u043e\u0432 \u043c\u043e\u0436\u043d\u043e \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u044c \u0432 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445 (\u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u043e \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e)",
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
    c.drawCentredString(sx + sw / 2, sy + sh - 16, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438")

    # Tab bar
    tab_y = sy + sh - 24
    tabs = ["\u041e\u0431\u0449\u0438\u0435", "\u041c\u043e\u0434\u0435\u043b\u0438", "\u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0438", "\u0410\u0433\u0435\u043d\u0442 \u0437\u0430\u043f\u0438\u0441\u0438"]
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
    dbtn(c, sx + sw - 128, sy + 10, 58, 18, "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c", PRIMARY, white, 8)
    c.setFillColor(TEXT2)
    c.setFont(F, 8)
    c.drawString(sx + sw - 60, sy + 15, "\u041e\u0442\u043c\u0435\u043d\u0430")

    return sx, tab_y - 30, sw, sy + 34


# ─── Settings: Models tab ──────────────────────────────────────────

def page_settings_models(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2014 \u041c\u043e\u0434\u0435\u043b\u0438")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "\u0412\u044b\u0431\u043e\u0440 \u043c\u0435\u0436\u0434\u0443 \u043e\u0431\u043b\u0430\u0447\u043d\u044b\u043c\u0438 \u0438 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u043c\u0438 \u0418\u0418-\u043c\u043e\u0434\u0435\u043b\u044f\u043c\u0438 \u0434\u043b\u044f \u0441\u0443\u043c\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f.")

    sx, ry, sw, bottom = _settings_frame(c, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", "\u041c\u043e\u0434\u0435\u043b\u0438")

    # ── Cloud ──
    c.setFillColor(HexColor("#6e6e73"))
    c.setFont(FB, 8)
    c.drawString(sx + 14, ry, "\u2601  \u041e\u0431\u043b\u0430\u043a\u043e")
    ry -= 16

    cloud_models = [
        ("Gemini 3 Flash Preview", True),
        ("Gemini 2.5 Pro", False),
        ("GPT-5 mini", False),
        ("GPT-5.4", False),
        ("\u0414\u0440\u0443\u0433\u0430\u044f:", False),
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

    # Custom text field on same line as "Другая:"
    ry += 15
    field(c, sx + 80, ry - 4, sw - 105, 14, "\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u043c\u043e\u0434\u0435\u043b\u0438\u2026")
    ry -= 20

    # API Key + Base URL
    c.setFillColor(TEXT)
    c.setFont(FB, 8)
    c.drawString(sx + 14, ry, "API-\u043a\u043b\u044e\u0447:")
    field(c, sx + 66, ry - 5, 114, 14, "\u0432\u0430\u0448 API-\u043a\u043b\u044e\u0447")
    c.drawString(sx + 192, ry, "Base URL:")
    field(c, sx + 240, ry - 5, sw - 260, 14, "(\u043e\u043f\u0446\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u043e)")
    ry -= 26

    # ── Local ──
    c.setFillColor(HexColor("#6e6e73"))
    c.setFont(FB, 8)
    c.drawString(sx + 14, ry, "\u26a1  \u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 (Ollama)")
    ry -= 16

    local_models = [
        ("GLM-4 9B", "\u0425\u043e\u0440\u043e\u0448\u043e", "5.5 GB", False, False),
        ("Gemma 3 12B QAT", "\u041b\u0443\u0447\u0448\u0435", "8.9 GB", False, False),
        ("Qwen 3 30B", "\u041e\u0442\u043b\u0438\u0447\u043d\u043e", "19 GB", False, False),
        ("GPT-OSS 20B", "\u041b\u0443\u0447\u0448\u0435\u0435", "12 GB", True, True),
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
        c.drawString(sx + 118, ry, f"\u2014 {quality} ({size})")
        if downloaded:
            c.setFillColor(SUCCESS)
            c.setFont(FB, 7.5)
            c.drawString(sx + sw - 90, ry, "\u0413\u043e\u0442\u043e\u0432\u043e")
            c.setFillColor(PRIMARY)
            c.setFont(F, 7.5)
            c.drawString(sx + sw - 68, ry, "\u0422\u0435\u0441\u0442")
            c.setFillColor(DANGER)
            c.drawString(sx + sw - 44, ry, "\u0423\u0434\u0430\u043b\u0438\u0442\u044c")
        else:
            c.setFillColor(PRIMARY)
            c.setFont(F, 7.5)
            c.drawString(sx + sw - 60, ry, "\u0421\u043a\u0430\u0447\u0430\u0442\u044c")
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
    c.drawString(sx + 14, ry, "\u041c\u043e\u0434\u0435\u043b\u044c Whisper (\u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0432\u0430\u043d\u0438\u0435 \u0440\u0435\u0447\u0438)")
    ry -= 16

    whisper_models = [
        ("tiny", "75 MB", "\u0411\u0430\u0437\u043e\u0432\u043e\u0435", False, False),
        ("base", "145 MB", "\u0425\u043e\u0440\u043e\u0448\u0435\u0435", True, True),
        ("small", "465 MB", "\u041b\u0443\u0447\u0448\u0435", False, False),
        ("medium", "1.5 GB", "\u041e\u0442\u043b\u0438\u0447\u043d\u043e\u0435", False, False),
        ("large-v3", "3.1 GB", "\u041c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d\u043e\u0435", False, False),
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
        c.drawString(sx + 82, ry, f"\u2014 {quality} ({size})")
        if downloaded:
            c.setFillColor(SUCCESS)
            c.setFont(FB, 8)
            c.drawString(sx + sw - 55, ry, "\u0413\u043e\u0442\u043e\u0432\u043e")
        else:
            c.setFillColor(PRIMARY)
            c.setFont(F, 8)
            c.drawString(sx + sw - 70, ry, "\u0421\u043a\u0430\u0447\u0430\u0442\u044c")
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

    ann("\u041f\u0440\u0435\u0441\u0435\u0442\u044b \u043e\u0431\u043b\u0430\u043a\u0430", "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043c\u043e\u0434\u0435\u043b\u044c \u0438\u043b\u0438 \u0432\u0432\u0435\u0434\u0438\u0442\u0435\n\u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435 \u0441\u0432\u043e\u0435\u0439 \u043c\u043e\u0434\u0435\u043b\u0438", H - 150)
    ann("API-\u0434\u0430\u043d\u043d\u044b\u0435", "\u041a\u043b\u044e\u0447 \u0434\u043b\u044f \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u043e\u0433\u043e\n\u043e\u0431\u043b\u0430\u0447\u043d\u043e\u0433\u043e \u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440\u0430", H - 245)
    ann("\u041b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u0435 \u043c\u043e\u0434\u0435\u043b\u0438 (Ollama)", "\u0417\u0430\u043f\u0443\u0441\u043a \u0418\u0418 \u043d\u0430 \u0432\u0430\u0448\u0435\u043c Mac \u2014\n100% \u043e\u0444\u043b\u0430\u0439\u043d, \u0431\u0435\u0437 API-\u043a\u043b\u044e\u0447\u0430.\n\u0421\u043a\u0430\u0447\u0430\u0442\u044c, \u0422\u0435\u0441\u0442, \u0423\u0434\u0430\u043b\u0438\u0442\u044c.", H - 330)
    ann("\u041c\u043e\u0434\u0435\u043b\u0438 Whisper", "\u0420\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u0432\u0430\u043d\u0438\u0435 \u0440\u0435\u0447\u0438 (\u043e\u0444\u043b\u0430\u0439\u043d).\n\u0411\u043e\u043b\u044c\u0448\u0435 = \u0442\u043e\u0447\u043d\u0435\u0435,\n\u043d\u043e \u043c\u0435\u0434\u043b\u0435\u043d\u043d\u0435\u0435.", H - 460)


# ─── Settings: Instructions tab ────────────────────────────────────

def page_settings_instructions(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2014 \u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0438")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u043f\u0440\u043e\u043c\u043f\u0442\u0430 \u0418\u0418. \u041f\u0440\u043e\u0444\u0438\u043b\u0438 \u0434\u043b\u044f \u0440\u0430\u0437\u043d\u044b\u0445 \u0442\u0438\u043f\u043e\u0432 \u0432\u0441\u0442\u0440\u0435\u0447.")

    sx, ry, sw, bottom = _settings_frame(c, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", "\u0418\u043d\u0441\u0442\u0440\u0443\u043a\u0446\u0438\u0438")

    # Profile row
    c.setFillColor(TEXT)
    c.setFont(FB, 9)
    c.drawString(sx + 14, ry, "\u041f\u0440\u043e\u0444\u0438\u043b\u044c:")
    combo(c, sx + 66, ry - 5, 154, 18, "\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e")

    c.setFillColor(PRIMARY)
    c.setFont(F, 9)
    c.drawString(sx + 232, ry, "\u041d\u043e\u0432\u044b\u0439")
    c.setFillColor(DANGER)
    c.drawString(sx + 270, ry, "\u0423\u0434\u0430\u043b\u0438\u0442\u044c")
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

    ann("\u041f\u0440\u043e\u0444\u0438\u043b\u0438", "\u0421\u043e\u0437\u0434\u0430\u0439\u0442\u0435 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u0435 \u043f\u0440\u043e\u043c\u043f\u0442\u044b \u0434\u043b\u044f\n\u0441\u0442\u0435\u043d\u0434\u0430\u043f\u043e\u0432, \u0440\u0435\u0432\u044c\u044e, 1-\u043d\u0430-1.\n\u041f\u0435\u0440\u0435\u043a\u043b\u044e\u0447\u0430\u0439\u0442\u0435 \u0432 \u0432\u044b\u043f\u0430\u0434\u0430\u044e\u0449\u0435\u043c \u043c\u0435\u043d\u044e.", H - 150)
    ann("\u041f\u0440\u043e\u043c\u043f\u0442 \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e", "\u0421\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435 \u0441\u0430\u043c\u043c\u0430\u0440\u0438 \u0432\u0441\u0442\u0440\u0435\u0447\u0438\n\u0441 \u0440\u0430\u0437\u0434\u0435\u043b\u0430\u043c\u0438: \u041e\u0431\u0437\u043e\u0440,\n\u0420\u0435\u0448\u0435\u043d\u0438\u044f, \u0417\u0430\u0434\u0430\u0447\u0438, \u041e\u0446\u0435\u043d\u043a\u0430.\n\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u0443\u0439\u0442\u0435 \u0438\u043b\u0438 \u0437\u0430\u043c\u0435\u043d\u0438\u0442\u0435.", H - 260)
    ann("\u041f\u0440\u0430\u0432\u0438\u043b\u0430 \u0444\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f", "\u0423\u043f\u0440\u0430\u0432\u043b\u044f\u0435\u0442 \u0444\u043e\u0440\u043c\u0430\u0442\u043e\u043c \u0432\u044b\u0432\u043e\u0434\u0430\nLLM \u2014 \u043c\u0430\u0440\u043a\u0435\u0440\u044b, \u0436\u0438\u0440\u043d\u044b\u0439,\n\u043a\u0443\u0440\u0441\u0438\u0432, \u0431\u0435\u0437 markdown.", H - 400)


# ─── Settings: General tab ─────────────────────────────────────────

def page_settings_general(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2014 \u041e\u0431\u0449\u0438\u0435")
    c.setFillColor(TEXT)
    c.setFont(F, 11)
    c.drawString(40, H - 82, "\u0410\u0443\u0434\u0438\u043e, \u0437\u0430\u043f\u0438\u0441\u044c \u0438 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u0445\u0440\u0430\u043d\u0435\u043d\u0438\u044f.")

    sx, ry, sw, bottom = _settings_frame(c, "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", "\u041e\u0431\u0449\u0438\u0435")

    rows = [
        ("\u041b\u0438\u043c\u0438\u0442 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0430:", "5000 \u0441\u0438\u043c\u0432.",
         "\u041c\u0430\u043a\u0441. \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432 \u0438\u0437 \u0444\u0430\u0439\u043b\u0430 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0430.\n\u0421\u0442\u0430\u0440\u044b\u0439 \u043a\u043e\u043d\u0442\u0435\u043d\u0442 \u043e\u0431\u0440\u0435\u0437\u0430\u0435\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438."),
        ("\u0422\u0430\u0439\u043c\u0430\u0443\u0442 \u0442\u0438\u0448\u0438\u043d\u044b:", "180 \u0441\u0435\u043a",
         "\u0410\u0432\u0442\u043e\u0441\u0442\u043e\u043f \u043f\u043e\u0441\u043b\u0435 \u044d\u0442\u043e\u0433\u043e \u043f\u0435\u0440\u0438\u043e\u0434\u0430 \u0442\u0438\u0448\u0438\u043d\u044b (3 \u043c\u0438\u043d).\n\u0410\u0434\u0430\u043f\u0442\u0438\u0432\u043d\u0430\u044f \u043a\u0430\u043b\u0438\u0431\u0440\u043e\u0432\u043a\u0430 \u0438\u0437\u043c\u0435\u0440\u044f\u0435\u0442 \u0448\u0443\u043c \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d\u0430."),
        ("\u0423\u0441\u0442\u0440-\u0432\u043e \u0432\u0432\u043e\u0434\u0430:", "\u041f\u043e \u0443\u043c\u043e\u043b\u0447.",
         "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043c\u0438\u043a\u0440\u043e\u0444\u043e\u043d \u0438\u043b\u0438 loopback-\u0443\u0441\u0442\u0440\u043e\u0439\u0441\u0442\u0432\u043e.\n\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u2014 \u0441\u0438\u0441\u0442\u0435\u043c\u043d\u044b\u0439 \u0432\u0445\u043e\u0434."),
        ("\u0421\u043e\u0445\u0440. \u0430\u0443\u0434\u0438\u043e:", "\u0432\u044b\u043a\u043b",
         "\u041f\u0440\u0438 \u0432\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u0435\u0442 WAV-\u0437\u0430\u043f\u0438\u0441\u0438 \u043d\u0430 \u0434\u0438\u0441\u043a.\n\u041e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u043e \u043f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e \u2014 \u0437\u0430\u043f\u0438\u0441\u0438 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u044b\u0435."),
        ("\u0417\u0432\u0443\u043a:", "\u0432\u043a\u043b",
         "\u0417\u0432\u0443\u043a\u043e\u0432\u043e\u0435 \u0443\u0432\u0435\u0434\u043e\u043c\u043b\u0435\u043d\u0438\u0435 \u043f\u043e \u0433\u043e\u0442\u043e\u0432\u043d\u043e\u0441\u0442\u0438 \u0441\u0430\u043c\u043c\u0430\u0440\u0438."),
        ("\u041f\u0430\u043f\u043a\u0430 \u0437\u0430\u043f\u0438\u0441\u0435\u0439:", "~/.summarizer/recordings",
         "\u0413\u0434\u0435 \u0445\u0440\u0430\u043d\u044f\u0442\u0441\u044f \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442\u044b \u0438 \u0444\u0430\u0439\u043b\u044b \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0430."),
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
    c.drawString(sx + 14, ry, "\u0412\u0435\u0440\u0441\u0438\u044f:")
    c.setFillColor(TEXT)
    c.setFont(FB, 8.5)
    c.drawString(sx + 70, ry, "v1.18.4")
    dbtn(c, sx + sw - 165, ry - 5, 150, 18, "\u041f\u0440\u043e\u0432\u0435\u0440\u0438\u0442\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0438\u044f", PRIMARY, white, 8)
    ry -= 28

    dbtn(c, sx + 14, ry - 5, 110, 18, "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043b\u043e\u0433-\u0444\u0430\u0439\u043b", Color(0.43, 0.43, 0.45), white, 8)
    c.setFillColor(TEXT2)
    c.setFont(F, 8)
    c.drawString(sx + 134, ry, "~/.summarizer/summarizer.log")
    ry -= 24


# ─── Context ────────────────────────────────────────────────────────

def page_context(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u0421\u0435\u0440\u0438\u0438 \u0432\u0441\u0442\u0440\u0435\u0447")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    hs = ParagraphStyle("h", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (hs, "Что такое серия встреч?"),
        (bs, "Серия встреч группирует регулярные встречи (стендапы, 1-на-1, ревью), "
             "чтобы Summarizer мог отслеживать прогресс и задачи между сессиями. "
             "Все данные хранятся в локальной базе данных SQLite."),
        (hs, "Создание серии"),
        (bs, "Нажмите <b>+</b> рядом с выпадающим списком серий. "
             "Используйте <b>edit (карандаш)</b> для редактирования, "
             "<b>chat (облачко)</b> для чата о серии, "
             "и <b>\u00d7</b> для удаления."),
        (hs, "Постоянный контекст"),
        (bs, "У каждой серии есть постоянный контекст — участники, цели, ключевые термины. "
             "Редактируется через диалог редактирования серии. "
             "Всегда включается целиком в промпт LLM."),
        (hs, "Контекст этой встречи"),
        (bs, "Детали конкретной встречи — повестка, участники, темы. "
             "Всегда включается в промпт. Сохраняется в базу данных "
             "вместе с транскриптом и саммари."),
        (hs, "История и бюджет"),
        (bs, "Каждое саммари (с контекстом встречи) сохраняется в базу данных. "
             "Лимит контекста (по умолчанию 5000 симв.) определяет, сколько истории "
             "загружается — постоянный контекст и контекст встречи включаются целиком, "
             "оставшийся бюджет заполняется недавними саммари."),
        (hs, "Чат по серии"),
        (bs, "Нажмите <b>chat (облачко)</b> для чата с ИИ о серии. "
             "Модель видит постоянный контекст и все недавние саммари. "
             "Задавайте вопросы вроде «что решили по X?» или «какие открытые задачи?»"),
    ]

    fr = Frame(40, 200, W - 80, H - 120 - 200, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # Database diagram
    fy = 170
    c.setFont(FB, 11)
    c.setFillColor(PRIMARY)
    c.drawCentredString(W / 2, fy, "Хранение данных")

    rrect(c, 60, fy - 110, W - 120, 100, r=6, fill=Color(0, 0, 0, 0.04))
    c.setFont(FB, 8)
    c.setFillColor(PRIMARY)
    c.drawString(75, fy - 16, "База данных SQLite: ~/.summarizer/summarizer.db")
    c.setFont(F, 8.5)
    c.setFillColor(TEXT2)
    c.drawString(75, fy - 34, "contexts — название серии, постоянный контекст")
    c.drawString(75, fy - 48, "meetings — транскрипт, саммари, контекст встречи,")
    c.drawString(75, fy - 62, "                  длительность, дата, привязка к серии")
    c.setFont(F, 8)
    c.setFillColor(MUTED)
    c.drawString(75, fy - 82, "Существующие _context.txt файлы мигрируются автоматически.")
    c.drawString(75, fy - 96, "Все данные доступны через диалог Истории (значок часов).")


# ─── Menu Bar ──────────────────────────────────────────────────

def page_menu_bar(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u041c\u0435\u043d\u044e-\u0431\u0430\u0440 \u0438 \u0430\u0433\u0435\u043d\u0442 \u0437\u0430\u043f\u0438\u0441\u0438")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    hs = ParagraphStyle("h", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (hs, "\u0418\u043a\u043e\u043d\u043a\u0430 \u0432 \u043c\u0435\u043d\u044e-\u0431\u0430\u0440\u0435"),
        (bs, "Summarizer \u0440\u0430\u0437\u043c\u0435\u0449\u0430\u0435\u0442 \u0438\u043a\u043e\u043d\u043a\u0443 \u0432 \u0441\u0442\u0440\u043e\u043a\u0435 \u043c\u0435\u043d\u044e macOS. \u041f\u043e \u043a\u043b\u0438\u043a\u0443 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u043a\u043e\u043c\u043f\u0430\u043a\u0442\u043d\u043e\u0435 "
             "\u043c\u0435\u043d\u044e \u0441 \u043f\u0443\u043d\u043a\u0442\u0430\u043c\u0438 <b>\u041d\u0430\u0447\u0430\u0442\u044c/\u041e\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c</b>, <b>\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c Summarizer</b>, "
             "<b>\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438</b> \u0438 <b>\u0412\u044b\u0445\u043e\u0434</b>."),
        (hs, "\u0421\u043a\u0440\u044b\u0442\u0438\u0435 \u0438\u0437 Dock"),
        (bs, "\u041f\u0440\u0438 \u0441\u0432\u043e\u0440\u0430\u0447\u0438\u0432\u0430\u043d\u0438\u0438 \u0432 \u0442\u0440\u0435\u0439 \u043c\u0435\u043d\u044e-\u0431\u0430\u0440\u0430 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0441\u043a\u0440\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0438\u0437 Dock. "
             "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043d\u0430 \u0438\u043a\u043e\u043d\u043a\u0443 \u0432 \u043c\u0435\u043d\u044e-\u0431\u0430\u0440\u0435 \u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 <b>\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c Summarizer</b>, \u0447\u0442\u043e\u0431\u044b \u0432\u0435\u0440\u043d\u0443\u0442\u044c \u043e\u043a\u043d\u043e."),
        (hs, "\u041e\u0434\u0438\u043d \u044d\u043a\u0437\u0435\u043c\u043f\u043b\u044f\u0440"),
        (bs, "\u041f\u043e\u0432\u0442\u043e\u0440\u043d\u044b\u0439 \u0437\u0430\u043f\u0443\u0441\u043a Summarizer \u043d\u0435 \u043e\u0442\u043a\u0440\u044b\u0432\u0430\u0435\u0442 \u0432\u0442\u043e\u0440\u0443\u044e \u043a\u043e\u043f\u0438\u044e. "
             "\u0412\u043c\u0435\u0441\u0442\u043e \u044d\u0442\u043e\u0433\u043e \u0441\u0443\u0449\u0435\u0441\u0442\u0432\u0443\u044e\u0449\u0435\u0435 \u043e\u043a\u043d\u043e \u0432\u044b\u0432\u043e\u0434\u0438\u0442\u0441\u044f \u043d\u0430 \u043f\u0435\u0440\u0435\u0434\u043d\u0438\u0439 \u043f\u043b\u0430\u043d."),
        (hs, "\u0410\u0433\u0435\u043d\u0442 \u0437\u0430\u043f\u0438\u0441\u0438"),
        (bs, "\u0410\u0433\u0435\u043d\u0442 \u0437\u0430\u043f\u0438\u0441\u0438 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u043d\u0430\u0447\u0438\u043d\u0430\u0435\u0442 \u0437\u0430\u043f\u0438\u0441\u044c, \u043a\u043e\u0433\u0434\u0430 \u043e\u0431\u043d\u0430\u0440\u0443\u0436\u0438\u0432\u0430\u0435\u0442 \u043f\u0440\u0435\u0434\u0441\u0442\u043e\u044f\u0449\u0443\u044e \u0432\u0441\u0442\u0440\u0435\u0447\u0443 "
             "\u0438\u0437 \u0432\u0435\u0431-\u043a\u0430\u043b\u0435\u043d\u0434\u0430\u0440\u044f. \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u0442\u0435 URL \u0431\u044d\u043a\u0435\u043d\u0434\u0430 \u0438 "
             "\u043f\u043e\u0432\u0435\u0434\u0435\u043d\u0438\u0435 \u0432 <b>\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2192 \u0410\u0433\u0435\u043d\u0442 \u0437\u0430\u043f\u0438\u0441\u0438</b>."),
        (bs, "\u041a\u043e\u0433\u0434\u0430 \u0432\u0441\u0442\u0440\u0435\u0447\u0430 \u043d\u0430\u0447\u0438\u043d\u0430\u0435\u0442\u0441\u044f, \u0430\u0433\u0435\u043d\u0442 \u0430\u043a\u0442\u0438\u0432\u0438\u0440\u0443\u0435\u0442 \u0437\u0430\u043f\u0438\u0441\u044c \u0438 \u043e\u0441\u0442\u0430\u043d\u0430\u0432\u043b\u0438\u0432\u0430\u0435\u0442 "
             "\u043f\u043e \u043e\u043a\u043e\u043d\u0447\u0430\u043d\u0438\u0438. \u0422\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442 \u0438 \u0441\u0430\u043c\u043c\u0430\u0440\u0438 \u0433\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u044e\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438, "
             "\u043a\u0430\u043a \u043f\u0440\u0438 \u0440\u0443\u0447\u043d\u043e\u0439 \u0437\u0430\u043f\u0438\u0441\u0438."),
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
        ("\u041d\u0430\u0447\u0430\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044c", PRIMARY),
        ("\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c Summarizer", TEXT),
        ("\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438", TEXT),
        ("\u0412\u044b\u0445\u043e\u0434", DANGER),
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
    c.drawCentredString(mx + mw / 2, my - 14, "\u0412\u044b\u043f\u0430\u0434\u0430\u044e\u0449\u0435\u0435 \u043c\u0435\u043d\u044e \u043c\u0435\u043d\u044e-\u0431\u0430\u0440\u0430")


# ─── History ───────────────────────────────────────────────────

def page_history(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0432\u0441\u0442\u0440\u0435\u0447 \u0438 \u0441\u0435\u0440\u0438\u0438")

    bs = ParagraphStyle("b", fontName=F, fontSize=10.5, leading=15, textColor=TEXT, spaceAfter=6)
    hs = ParagraphStyle("h", fontName=FB, fontSize=12, leading=16, textColor=PRIMARY,
                        spaceBefore=14, spaceAfter=4)

    content = [
        (hs, "\u0418\u0441\u0442\u043e\u0440\u0438\u044f \u0432\u0441\u0442\u0440\u0435\u0447"),
        (bs, "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 <b>\u0438\u043a\u043e\u043d\u043a\u0443 \u0447\u0430\u0441\u043e\u0432</b> \u0432 \u0432\u0435\u0440\u0445\u043d\u0435\u0439 \u043f\u0430\u043d\u0435\u043b\u0438, \u0447\u0442\u043e\u0431\u044b \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0434\u0438\u0430\u043b\u043e\u0433 \u0438\u0441\u0442\u043e\u0440\u0438\u0438 \u0432\u0441\u0442\u0440\u0435\u0447. "
             "\u041e\u043d \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0441\u043f\u0438\u0441\u043e\u043a \u0432\u0441\u0435\u0445 \u043f\u0440\u043e\u0448\u043b\u044b\u0445 \u0432\u0441\u0442\u0440\u0435\u0447 \u0441 \u0434\u0430\u0442\u043e\u0439, "
             "\u0441\u0435\u0440\u0438\u0435\u0439, \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442\u043e\u043c \u0438 \u0441\u0430\u043c\u043c\u0430\u0440\u0438 \u0441 \u043f\u043e\u0438\u0441\u043a\u043e\u043c \u0438 \u043f\u0440\u043e\u043a\u0440\u0443\u0442\u043a\u043e\u0439. \u0412\u0441\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u0445\u0440\u0430\u043d\u044f\u0442\u0441\u044f \u0432 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0439 \u0431\u0430\u0437\u0435 SQLite."),
        (hs, "\u0420\u0435\u0434\u0430\u043a\u0442\u043e\u0440 \u0441\u0435\u0440\u0438\u0438 \u0432\u0441\u0442\u0440\u0435\u0447"),
        (bs, "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 <b>\u043a\u043d\u043e\u043f\u043a\u0443 \u0440\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u044f</b> (\u270f) \u0440\u044f\u0434\u043e\u043c \u0441 \u0432\u044b\u043f\u0430\u0434\u0430\u044e\u0449\u0438\u043c \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0441\u0435\u0440\u0438\u0438, \u0447\u0442\u043e\u0431\u044b \u043e\u0442\u043a\u0440\u044b\u0442\u044c "
             "\u0440\u0435\u0434\u0430\u043a\u0442\u043e\u0440. \u0417\u0434\u0435\u0441\u044c \u043c\u043e\u0436\u043d\u043e \u043f\u0435\u0440\u0435\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u0442\u044c \u0441\u0435\u0440\u0438\u044e, \u043e\u0431\u043d\u043e\u0432\u0438\u0442\u044c \u043e\u0431\u0449\u0438\u0439 \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442, \u043f\u0440\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c "
             "\u043d\u0430\u043a\u043e\u043f\u043b\u0435\u043d\u043d\u0443\u044e \u0438\u0441\u0442\u043e\u0440\u0438\u044e \u0438 \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u043d\u0435\u043d\u0443\u0436\u043d\u044b\u0435 \u0441\u0435\u0440\u0438\u0438."),
        (hs, "\u0427\u0430\u0442 \u043f\u043e \u0441\u0435\u0440\u0438\u0438"),
        (bs, "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 <b>\u0438\u043a\u043e\u043d\u043a\u0443 \u0447\u0430\u0442\u0430</b> (\U0001f4ac) \u0440\u044f\u0434\u043e\u043c \u0441 \u0432\u044b\u043f\u0430\u0434\u0430\u044e\u0449\u0438\u043c \u0441\u043f\u0438\u0441\u043a\u043e\u043c \u0441\u0435\u0440\u0438\u0438, \u0447\u0442\u043e\u0431\u044b \u043e\u0442\u043a\u0440\u044b\u0442\u044c "
             "\u043e\u043a\u043d\u043e \u0447\u0430\u0442\u0430 \u0434\u043b\u044f \u044d\u0442\u043e\u0439 \u0441\u0435\u0440\u0438\u0438. \u0417\u0430\u0434\u0430\u0432\u0430\u0439\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u043e \u043f\u0440\u043e\u0448\u043b\u044b\u0445 \u0432\u0441\u0442\u0440\u0435\u0447\u0430\u0445, "
             "\u0437\u0430\u0434\u0430\u0447\u0430\u0445, \u0440\u0435\u0448\u0435\u043d\u0438\u044f\u0445 \u0438\u043b\u0438 \u0442\u0435\u043d\u0434\u0435\u043d\u0446\u0438\u044f\u0445 \u2014 LLM \u0438\u043c\u0435\u0435\u0442 \u0434\u043e\u0441\u0442\u0443\u043f \u043a\u043e \u0432\u0441\u0435\u0439 \u0438\u0441\u0442\u043e\u0440\u0438\u0438 \u0441\u0435\u0440\u0438\u0438 "
             "\u0438\u0437 \u0431\u0430\u0437\u044b \u0434\u0430\u043d\u043d\u044b\u0445."),
        (hs, "\u0425\u0440\u0430\u043d\u0438\u043b\u0438\u0449\u0435 SQLite"),
        (bs, "\u0412\u0441\u0435 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442\u044b, \u0441\u0430\u043c\u043c\u0430\u0440\u0438, \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u044b \u0432\u0441\u0442\u0440\u0435\u0447 \u0438 \u0434\u0430\u043d\u043d\u044b\u0435 \u0441\u0435\u0440\u0438\u0439 \u0445\u0440\u0430\u043d\u044f\u0442\u0441\u044f \u0432 "
             "\u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0439 \u0431\u0430\u0437\u0435 SQLite \u043f\u043e \u043f\u0443\u0442\u0438 <b>~/.summarizer/summarizer.db</b>. \u042d\u0442\u043e \u0437\u0430\u043c\u0435\u043d\u044f\u0435\u0442 "
             "\u0441\u0442\u0430\u0440\u044b\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u044b\u0435 \u0444\u0430\u0439\u043b\u044b \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u0430 \u0438 \u043e\u0431\u0435\u0441\u043f\u0435\u0447\u0438\u0432\u0430\u0435\u0442 \u0431\u044b\u0441\u0442\u0440\u044b\u0439 \u043f\u043e\u0438\u0441\u043a, \u043d\u0430\u0434\u0451\u0436\u043d\u0443\u044e \u0438\u0441\u0442\u043e\u0440\u0438\u044e "
             "\u0438 \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0435 \u0437\u0430\u043f\u0440\u043e\u0441\u044b \u0434\u043b\u044f \u0447\u0430\u0442\u0430 \u043f\u043e \u0441\u0435\u0440\u0438\u0438."),
    ]

    fr = Frame(40, 120, W - 80, H - 120 - 120, showBoundary=0)
    fr.addFromList([Paragraph(t, s) for s, t in content], c)

    # DB structure hint
    rrect(c, 60, 50, W - 120, 55, r=6, fill=Color(0, 0, 0, 0.04))
    c.setFillColor(TEXT2)
    c.setFont(FB, 9)
    c.drawString(75, 88, "~/.summarizer/")
    c.setFont(F, 9)
    c.drawString(90, 74, "summarizer.db     \u2014 \u0431\u0430\u0437\u0430 SQLite (\u0432\u0441\u0442\u0440\u0435\u0447\u0438, \u0441\u0435\u0440\u0438\u0438, \u043a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u044b)")
    c.drawString(90, 60, "recordings/       \u2014 \u0430\u0443\u0434\u0438\u043e\u0444\u0430\u0439\u043b\u044b (\u0435\u0441\u043b\u0438 \u0432\u043a\u043b\u044e\u0447\u0435\u043d\u043e \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435 \u0430\u0443\u0434\u0438\u043e)")


# ─── FAQ ────────────────────────────────────────────────────────────

def page_faq(c):
    c.setFont(FB, 22)
    c.setFillColor(PRIMARY)
    c.drawString(40, H - 60, "\u0427\u0430\u0441\u0442\u044b\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u0438 \u0441\u043e\u0432\u0435\u0442\u044b")

    bs = ParagraphStyle("b", fontName=F, fontSize=10, leading=14.5, textColor=TEXT, spaceAfter=6)
    qs = ParagraphStyle("q", fontName=FB, fontSize=11, leading=15, textColor=TEXT,
                        spaceBefore=12, spaceAfter=3)

    qa = [
        ("\u0413\u0434\u0435 \u0432\u0437\u044f\u0442\u044c API-\u043a\u043b\u044e\u0447?",
         "Gemini: aistudio.google.com \u2014 \u0421\u043e\u0437\u0434\u0430\u0442\u044c API-\u043a\u043b\u044e\u0447. "
         "Claude: console.anthropic.com \u2014 API Keys. "
         "OpenAI: platform.openai.com \u2014 API Keys."),
        ("\u0424\u043e\u0440\u043c\u0430\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043d\u0435 \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043f\u0440\u0438 \u0432\u0441\u0442\u0430\u0432\u043a\u0435 \u0432 Slack?",
         "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443 <b>\u041a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0430\u043c\u043c\u0430\u0440\u0438</b> \u2014 \u043e\u043d\u0430 \u043a\u043e\u043f\u0438\u0440\u0443\u0435\u0442 \u0442\u0435\u043a\u0441\u0442 \u0441 HTML-\u0440\u0430\u0437\u043c\u0435\u0442\u043a\u043e\u0439, "
         "\u0438 \u0436\u0438\u0440\u043d\u044b\u0439/\u043a\u0443\u0440\u0441\u0438\u0432 \u043e\u0442\u043e\u0431\u0440\u0430\u0436\u0430\u044e\u0442\u0441\u044f \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u043e. \u041e\u0431\u044b\u0447\u043d\u044b\u0439 Cmd+C \u043a\u043e\u043f\u0438\u0440\u0443\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e \u043f\u0440\u043e\u0441\u0442\u043e\u0439 \u0442\u0435\u043a\u0441\u0442."),
        ("\u041a\u0430\u043a\u0443\u044e \u043c\u043e\u0434\u0435\u043b\u044c Whisper \u0432\u044b\u0431\u0440\u0430\u0442\u044c?",
         "<b>base</b> (145 MB) \u2014 \u0431\u044b\u0441\u0442\u0440\u0430\u044f, \u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u0434\u043b\u044f \u0447\u0451\u0442\u043a\u043e\u0439 \u0440\u0435\u0447\u0438. "
         "<b>medium</b> (1.5 GB) \u2014 \u043b\u0443\u0447\u0448\u0438\u0439 \u0431\u0430\u043b\u0430\u043d\u0441 \u0441\u043a\u043e\u0440\u043e\u0441\u0442\u0438 \u0438 \u0442\u043e\u0447\u043d\u043e\u0441\u0442\u0438. "
         "<b>large-v3</b> (3.1 GB) \u2014 \u043c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d\u0430\u044f \u0442\u043e\u0447\u043d\u043e\u0441\u0442\u044c, \u043d\u043e \u043c\u0435\u0434\u043b\u0435\u043d\u043d\u0435\u0435."),
        ("\u0413\u0434\u0435 \u0445\u0440\u0430\u043d\u044f\u0442\u0441\u044f \u0434\u0430\u043d\u043d\u044b\u0435?",
         "\u041a\u043e\u043d\u0444\u0438\u0433: ~/.summarizer/config.json. "
         "\u041a\u043e\u043d\u0442\u0435\u043a\u0441\u0442\u044b \u0438 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442\u044b: ~/.summarizer/recordings/. "
         "\u041c\u043e\u0434\u0435\u043b\u0438 Whisper: ~/.summarizer/models/. "
         "\u041b\u043e\u0433: ~/.summarizer/summarizer.log (\u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0447\u0435\u0440\u0435\u0437 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2192 \u041e\u0431\u0449\u0438\u0435 \u2192 \u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043b\u043e\u0433-\u0444\u0430\u0439\u043b)."),
        ("\u042d\u0442\u043e \u0431\u0435\u0437\u043e\u043f\u0430\u0441\u043d\u043e?",
         "\u0410\u0443\u0434\u0438\u043e \u0432\u0441\u0435\u0433\u0434\u0430 \u043e\u0431\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u0435\u0442\u0441\u044f <b>\u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e</b> \u0447\u0435\u0440\u0435\u0437 Whisper \u2014 \u043e\u043d\u043e \u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u043f\u043e\u043a\u0438\u0434\u0430\u0435\u0442 \u0432\u0430\u0448 Mac. "
         "\u041f\u0440\u0438 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0438 \u043e\u0431\u043b\u0430\u0447\u043d\u044b\u0445 \u043c\u043e\u0434\u0435\u043b\u0435\u0439 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u0442\u043e\u043b\u044c\u043a\u043e \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u0430\u044f \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0446\u0438\u044f. "
         "\u0421 <b>\u043b\u043e\u043a\u0430\u043b\u044c\u043d\u044b\u043c\u0438 \u043c\u043e\u0434\u0435\u043b\u044f\u043c\u0438 (Ollama)</b> \u0432\u0441\u0451 \u043e\u0441\u0442\u0430\u0451\u0442\u0441\u044f \u043d\u0430 \u0432\u0430\u0448\u0435\u043c Mac \u2014 \u043f\u043e\u043b\u043d\u043e\u0441\u0442\u044c\u044e \u043e\u0444\u043b\u0430\u0439\u043d, "
         "\u0434\u0430\u043d\u043d\u044b\u0435 \u043d\u0438\u043a\u043e\u0433\u0434\u0430 \u043d\u0435 \u043f\u043e\u043a\u0438\u0434\u0430\u044e\u0442 \u0432\u0430\u0448 \u043a\u043e\u043c\u043f\u044c\u044e\u0442\u0435\u0440."),
        ("\u041a\u0430\u043a \u043f\u0440\u043e\u0442\u0435\u0441\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u0443\u044e \u043c\u043e\u0434\u0435\u043b\u044c \u043f\u0435\u0440\u0435\u0434 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u0438\u0435\u043c?",
         "\u0412 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 \u2192 \u041c\u043e\u0434\u0435\u043b\u0438, \u043f\u043e\u0441\u043b\u0435 \u0441\u043a\u0430\u0447\u0438\u0432\u0430\u043d\u0438\u044f \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e\u0439 \u043c\u043e\u0434\u0435\u043b\u0438 \u043f\u043e\u044f\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u043a\u043d\u043e\u043f\u043a\u0430 <b>\u0422\u0435\u0441\u0442</b>. "
         "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u0435\u0451, \u0447\u0442\u043e\u0431\u044b \u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0447\u0430\u0442 \u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u044f\u0442\u044c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f \u043c\u043e\u0434\u0435\u043b\u0438 \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e."),
        ("\u041c\u043e\u0436\u043d\u043e \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c \u0441\u0432\u043e\u0439 LLM-\u044d\u043d\u0434\u043f\u043e\u0439\u043d\u0442?",
         "\u0414\u0430 \u2014 \u0443\u043a\u0430\u0436\u0438\u0442\u0435 \u043f\u043e\u043b\u0435 <b>Base URL</b> \u0432 \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430\u0445 \u043d\u0430 \u043b\u044e\u0431\u043e\u0439 "
         "OpenAI-\u0441\u043e\u0432\u043c\u0435\u0441\u0442\u0438\u043c\u044b\u0439 API-\u044d\u043d\u0434\u043f\u043e\u0439\u043d\u0442."),
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
    c.setTitle("Summarizer - \u0420\u0443\u043a\u043e\u0432\u043e\u0434\u0441\u0442\u0432\u043e \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f")
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
