"""macOS menu-bar (system tray) icon for Summarizer."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .i18n import t
from .theme import C


def _dot_icon(color: str, size: int = 22) -> QIcon:
    """Create a small filled circle icon for the tray."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    margin = 4
    p.drawEllipse(margin, margin, size - margin * 2, size - margin * 2)
    p.end()
    return QIcon(pm)


class TrayIcon(QSystemTrayIcon):
    """System tray icon with recording controls."""

    def __init__(self, parent=None, app_name: str = "Summarizer"):
        super().__init__(parent)
        self._app_name = app_name

        self._icon_idle = _dot_icon("#888888")
        self._icon_recording = _dot_icon("#D94A4A")
        self._icon_processing = _dot_icon("#4A90D9")

        self.setIcon(self._icon_idle)
        self.setToolTip(self._app_name)

        self._menu = QMenu()

        self._show_action = self._menu.addAction(t("tray_show"))
        self._menu.addSeparator()

        self._rec_action = self._menu.addAction(t("tray_start_rec"))
        self._menu.addSeparator()

        self._settings_action = self._menu.addAction(t("tray_settings"))
        self._menu.addSeparator()

        self._quit_action = self._menu.addAction(t("tray_quit"))

        self.setContextMenu(self._menu)

        self._recording = False

    # ── Public API for MainWindow to connect ─────────────────────────

    @property
    def show_action(self):
        return self._show_action

    @property
    def rec_action(self):
        return self._rec_action

    @property
    def settings_action(self):
        return self._settings_action

    @property
    def quit_action(self):
        return self._quit_action

    def set_recording(self, recording: bool):
        self._recording = recording
        if recording:
            self.setIcon(self._icon_recording)
            self._rec_action.setText(t("tray_stop_rec"))
            self.setToolTip(t("tray_recording"))
        else:
            self.setIcon(self._icon_idle)
            self._rec_action.setText(t("tray_start_rec"))
            self.setToolTip(self._app_name)

    def set_processing(self):
        self.setIcon(self._icon_processing)
        self.setToolTip(t("tray_processing"))

    def set_idle(self):
        if not self._recording:
            self.setIcon(self._icon_idle)
            self.setToolTip(self._app_name)
