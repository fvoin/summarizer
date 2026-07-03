"""Small UI widgets shared by the full and lite apps.

Must not import summarizer.summarizer or summarizer.db.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from .recorder import AudioRecorder
from .i18n import t


class MicPicker(QComboBox):
    """Dropdown of input devices; first entry is the system default (id None)."""

    def __init__(self, selected=None, parent=None):
        super().__init__(parent)
        self.addItem(t("input_device_default"), None)
        for dev in AudioRecorder.list_devices():
            self.addItem(dev["name"], dev["id"])
        if selected is not None:
            idx = self.findData(selected)
            if idx >= 0:
                self.setCurrentIndex(idx)

    def selected_device(self):
        return self.currentData()
