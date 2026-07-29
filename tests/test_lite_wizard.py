"""Transcriber first-run wizard: model-quality step + config defaults."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QDialog

from summarizer import app_lite, config

_app = QApplication.instance() or QApplication([])


class _FakeModelWorker(QObject):
    progress = pyqtSignal(float)
    done = pyqtSignal()
    error = pyqtSignal(str)
    finished = pyqtSignal()

    last_model = None

    def __init__(self, model_name):
        super().__init__()
        _FakeModelWorker.last_model = model_name

    def start(self):
        self.progress.emit(1.0)
        self.done.emit()


@pytest.fixture
def wizard_env(monkeypatch):
    saved = {}
    downloaded = {"base"}  # base ships with the app
    monkeypatch.setattr(app_lite, "_LiteModelDownloadWorker", _FakeModelWorker)
    monkeypatch.setattr(config, "load", lambda: {"whisper_model": "base"})
    monkeypatch.setattr(config, "save", lambda cfg: saved.update(cfg))
    monkeypatch.setattr(config, "is_model_downloaded", lambda m: m in downloaded)
    monkeypatch.setattr(
        app_lite.MicPicker, "__init__", lambda self, selected=None: __import__(
            "PyQt6.QtWidgets", fromlist=["QComboBox"]).QComboBox.__init__(self))
    monkeypatch.setattr(app_lite.MicPicker, "selected_device", lambda self: None)
    return saved, downloaded


def _advance_to_model_step(wiz):
    wiz._to_backend()
    wiz._to_model()


def test_download_medium_sets_it_as_default(wizard_env):
    saved, _ = wizard_env
    wiz = app_lite.LiteSetupWizard()
    _advance_to_model_step(wiz)
    wiz._download_medium()
    assert _FakeModelWorker.last_model == "medium"
    assert saved["whisper_model"] == "medium"
    assert wiz.result() == QDialog.DialogCode.Accepted


def test_skip_keeps_base_model(wizard_env):
    saved, _ = wizard_env
    wiz = app_lite.LiteSetupWizard()
    _advance_to_model_step(wiz)
    wiz._skip_model()
    assert saved["whisper_model"] == "base"
    assert wiz.result() == QDialog.DialogCode.Accepted


def test_model_step_skipped_when_medium_already_downloaded(wizard_env):
    saved, downloaded = wizard_env
    downloaded.add("medium")
    wiz = app_lite.LiteSetupWizard()
    _advance_to_model_step(wiz)
    # Nothing to offer: medium is present -> select it and finish.
    assert saved["whisper_model"] == "medium"
    assert wiz.result() == QDialog.DialogCode.Accepted


def test_wizard_uses_app_theme(wizard_env):
    wiz = app_lite.LiteSetupWizard()
    assert wiz.styleSheet()  # themed, not the bare default QDialog


def test_tray_enabled_by_default():
    assert config._DEFAULTS["menubar_enabled"] is True
