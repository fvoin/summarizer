import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from summarizer import widgets

_app = QApplication.instance() or QApplication([])


def test_micpicker_has_default_first_and_lists_devices(monkeypatch):
    monkeypatch.setattr(
        widgets.AudioRecorder, "list_devices",
        staticmethod(lambda: [{"id": 3, "name": "Built-in Mic", "channels": 1}]),
    )
    p = widgets.MicPicker()
    assert p.count() == 2  # default + one device
    assert p.itemData(0) is None  # system default
    assert p.itemData(1) == 3


def test_micpicker_preselects_saved(monkeypatch):
    monkeypatch.setattr(
        widgets.AudioRecorder, "list_devices",
        staticmethod(lambda: [{"id": 3, "name": "Built-in Mic", "channels": 1}]),
    )
    p = widgets.MicPicker(selected=3)
    assert p.selected_device() == 3
