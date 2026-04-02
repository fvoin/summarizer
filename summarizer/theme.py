"""Theming system for Summarizer.

Provides named colour palettes and derived QSS helpers.  Every colour
that was previously hard-coded in app.py now lives here so that switching
themes is a single dict swap.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# Temp dir for generated arrow images (persists for app lifetime)
_ARROW_DIR = Path(tempfile.mkdtemp(prefix="summarizer_arrows_"))

# ---------------------------------------------------------------------------
# Palette definitions
# ---------------------------------------------------------------------------

_LIGHT: Dict[str, str] = {
    "primary":          "#4A90D9",
    "primary_hover":    "#3A7BC8",
    "primary_pressed":  "#2E6BB5",
    "primary_text":     "#ffffff",
    "accent":           "#7B68EE",
    "danger":           "#D94A4A",
    "danger_hover":     "#C43A3A",
    "bg":               "#ECECEC",
    "surface":          "#ffffff",
    "surface_alt":      "#F5F5F7",
    "border":           "#D1D1D6",
    "text":             "#1D1D1F",
    "text_secondary":   "#6E6E73",
    "text_muted":       "#AEAEB2",
    "success":          "#2D8A4E",
    "warning":          "#B08800",
    "error":            "#CC3333",
    "hover_overlay":    "rgba(0, 0, 0, 0.06)",
    "pressed_overlay":  "rgba(0, 0, 0, 0.12)",
    "selection":        "rgba(74, 144, 217, 0.25)",
    "progress_bg":      "#D5D5DA",
    "chat_assistant":   "#555555",
}

_DARK: Dict[str, str] = {
    "primary":          "#5B9FE6",
    "primary_hover":    "#7AB3F0",
    "primary_pressed":  "#4888CC",
    "primary_text":     "#ffffff",
    "accent":           "#9B8AFE",
    "danger":           "#E05555",
    "danger_hover":     "#F06666",
    "bg":               "#1E1E1E",
    "surface":          "#2D2D2D",
    "surface_alt":      "#353535",
    "border":           "#444444",
    "text":             "#E0E0E0",
    "text_secondary":   "#A0A0A0",
    "text_muted":       "#666666",
    "success":          "#4CAF72",
    "warning":          "#D4A017",
    "error":            "#E05555",
    "hover_overlay":    "rgba(255, 255, 255, 0.08)",
    "pressed_overlay":  "rgba(255, 255, 255, 0.14)",
    "selection":        "rgba(91, 159, 230, 0.30)",
    "progress_bg":      "#444444",
    "chat_assistant":   "#B0B0B0",
}

_NORD: Dict[str, str] = {
    "primary":          "#88C0D0",
    "primary_hover":    "#8FBCBB",
    "primary_pressed":  "#7AB0BF",
    "primary_text":     "#2E3440",
    "accent":           "#B48EAD",
    "danger":           "#BF616A",
    "danger_hover":     "#D08770",
    "bg":               "#2E3440",
    "surface":          "#3B4252",
    "surface_alt":      "#434C5E",
    "border":           "#4C566A",
    "text":             "#ECEFF4",
    "text_secondary":   "#D8DEE9",
    "text_muted":       "#6B7B8D",
    "success":          "#A3BE8C",
    "warning":          "#EBCB8B",
    "error":            "#BF616A",
    "hover_overlay":    "rgba(216, 222, 233, 0.08)",
    "pressed_overlay":  "rgba(216, 222, 233, 0.14)",
    "selection":        "rgba(136, 192, 208, 0.30)",
    "progress_bg":      "#4C566A",
    "chat_assistant":   "#D8DEE9",
}

_THEMES: Dict[str, Dict[str, str]] = {
    "light":    _LIGHT,
    "dark":     _DARK,
    "nord":     _NORD,
}

THEME_NAMES = list(_THEMES.keys())

# Active palette — module-level so everyone can import ``C``.
C: Dict[str, str] = dict(_LIGHT)


def apply(name: str) -> None:
    """Switch the active palette to *name* (e.g. ``"dark"``)."""
    C.clear()
    C.update(_THEMES.get(name, _LIGHT))


def apply_palette(app: QApplication) -> None:
    """Set QApplication palette from the active theme.

    This lets Fusion paint native-looking combo boxes, radio buttons,
    and other complex widgets without QSS fighting the renderer.
    """
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(C["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.Base, QColor(C["surface"]))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(C["surface_alt"]))
    p.setColor(QPalette.ColorRole.Text, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.Button, QColor(C["surface"]))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.Highlight, QColor(C["primary"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(C["primary_text"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(C["surface"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(C["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(C["text_muted"]))
    p.setColor(QPalette.ColorRole.Mid, QColor(C["border"]))
    p.setColor(QPalette.ColorRole.Dark, QColor(C["border"]))
    p.setColor(QPalette.ColorRole.Light, QColor(C["surface_alt"]))

    # Disabled state
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(C["text_muted"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(C["text_muted"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(C["text_muted"]))

    app.setPalette(p)


def _arrow_svg_path() -> str:
    """Generate a small SVG arrow and return its file path for QSS image: url()."""
    color = C["text_secondary"]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6">'
        f'<polygon points="0,0 10,0 5,6" fill="{color}"/>'
        '</svg>'
    )
    path = _ARROW_DIR / "combo_arrow.svg"
    path.write_text(svg)
    return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Derived QSS helpers  (call after apply())
# ---------------------------------------------------------------------------

def btn_primary() -> str:
    return f"""
        QPushButton {{
            background-color: {C['primary']};
            color: {C['primary_text']};
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 15px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {C['primary_hover']};
        }}
        QPushButton:pressed {{
            background-color: {C['primary_pressed']};
        }}
        QPushButton:disabled {{
            background-color: {C['border']};
            color: {C['text_muted']};
        }}
    """


def btn_recording() -> str:
    return f"""
        QPushButton {{
            background-color: {C['danger']};
            color: {C['primary_text']};
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 15px;
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {C['danger_hover']};
        }}
    """


def btn_secondary() -> str:
    return f"""
        QPushButton {{
            background-color: transparent;
            color: {C['primary']};
            border: none;
            border-radius: 6px;
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {C['hover_overlay']};
        }}
        QPushButton:pressed {{
            background-color: {C['pressed_overlay']};
        }}
        QPushButton:disabled {{
            color: {C['text_muted']};
        }}
    """


def flat_btn(color: str | None = None) -> str:
    c = color or C["primary"]
    return (
        f"QPushButton {{ background: transparent; border: none; border-radius: 4px;"
        f" padding: 2px 6px; font-size: 12px; font-weight: 500; color: {c}; }}"
        f" QPushButton:hover {{ background: {C['hover_overlay']}; }}"
        f" QPushButton:pressed {{ background: {C['pressed_overlay']}; }}"
    )


def ghost_btn() -> str:
    """Transparent button that highlights on hover (settings gear, etc.)."""
    return f"""
        QPushButton {{
            border: none;
            border-radius: 8px;
        }}
        QPushButton:hover {{
            background-color: {C['hover_overlay']};
        }}
    """


def window_style() -> str:
    return f"""
        QMainWindow, QDialog {{
            background-color: {C['bg']};
            color: {C['text']};
        }}
        QLabel {{
            color: {C['text']};
            background: transparent;
        }}
        QPushButton {{
            background-color: transparent;
            color: {C['primary']};
            border: none;
            border-radius: 6px;
            padding: 7px 14px;
            font-size: 13px;
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {C['hover_overlay']};
        }}
        QPushButton:pressed {{
            background-color: {C['pressed_overlay']};
        }}
        QPushButton:disabled {{
            color: {C['text_muted']};
        }}
        QTextEdit, QPlainTextEdit {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 6px;
            padding: 4px;
            selection-background-color: {C['selection']};
        }}
        QLineEdit {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {C['selection']};
        }}
        QComboBox {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 6px;
            padding: 4px 28px 4px 8px;
            min-height: 20px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 24px;
            border: none;
            background: transparent;
        }}
        QComboBox::down-arrow {{
            image: url({_arrow_svg_path()});
            width: 10px;
            height: 6px;
        }}
        QComboBox:on {{
            border-color: {C['primary']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {C['surface']};
            color: {C['text']};
            border: none;
            selection-background-color: {C['primary']};
            selection-color: {C['primary_text']};
            outline: none;
            padding: 4px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 4px 8px;
            border-radius: 4px;
            min-height: 22px;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {C['primary']};
            color: {C['primary_text']};
        }}
        QSpinBox {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 6px;
            padding: 4px 8px;
        }}
        QCheckBox {{
            color: {C['text']};
            spacing: 6px;
            background: transparent;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {C['border']};
            border-radius: 3px;
            background-color: {C['surface']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {C['primary']};
            border-color: {C['primary']};
        }}
        QRadioButton {{
            color: {C['text']};
            spacing: 6px;
            background: transparent;
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border: 2px solid {C['border']};
            border-radius: 10px;
            background-color: {C['surface']};
        }}
        QRadioButton::indicator:hover {{
            border-color: {C['primary']};
        }}
        QRadioButton::indicator:checked {{
            border-color: {C['primary']};
            background-color: {C['primary']};
        }}
        QGroupBox {{
            color: {C['text']};
            background-color: {C['bg']};
            border: 1px solid {C['border']};
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 16px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 4px;
            color: {C['text_secondary']};
        }}
        QScrollArea {{
            background-color: {C['bg']};
            border: none;
        }}
        QScrollArea > QWidget > QWidget {{
            background-color: {C['bg']};
        }}
        QTabWidget::pane {{
            border: 1px solid {C['border']};
            border-radius: 6px;
            background-color: {C['bg']};
        }}
        QTabBar::tab {{
            background-color: {C['surface_alt']};
            color: {C['text_secondary']};
            border: 1px solid {C['border']};
            border-bottom: none;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            padding: 6px 16px;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {C['bg']};
            color: {C['text']};
            font-weight: 600;
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {C['hover_overlay']};
        }}
        QProgressBar {{
            background-color: {C['progress_bg']};
            border: none;
            border-radius: 4px;
            height: 6px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {C['primary']};
            border-radius: 4px;
        }}
        QFormLayout {{
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {C['border']};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {C['text_muted']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {C['border']};
            border-radius: 4px;
            min-width: 24px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QToolTip {{
            background-color: {C['surface']};
            color: {C['text']};
            border: 1px solid {C['border']};
            padding: 4px;
            border-radius: 4px;
        }}
        QMessageBox {{
            background-color: {C['bg']};
        }}
        QMessageBox QLabel {{
            color: {C['text']};
        }}
        QSplitter::handle {{
            background-color: {C['border']};
        }}
    """


def card_style(selected: bool = False) -> str:
    """Wizard card button style."""
    if selected:
        bg = C["selection"]
        border = C["primary"]
    else:
        bg = C["surface"]
        border = C["border"]
    return f"""
        QPushButton {{
            background: {bg};
            border: 2px solid {border};
            border-radius: 12px;
            padding: 18px 16px;
            text-align: left;
            font-size: 13px;
            color: {C['text']};
        }}
        QPushButton:hover {{
            border-color: {C['primary']};
            background: {C['selection']};
        }}
    """


def status_colors() -> dict:
    """Colour pairs (fg, bg) for _set_status()."""
    return {
        "info":      (C["text_secondary"], "transparent"),
        "recording": (C["primary_text"],   C["danger"]),
        "busy":      (C["primary"],        C["selection"]),
        "done":      (C["success"],        f"rgba({_hex_to_rgb(C['success'])}, 0.1)"),
        "error":     (C["primary_text"],   C["danger"]),
    }


def _hex_to_rgb(hex_color: str) -> str:
    """Convert '#RRGGBB' to 'R, G, B'."""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"
