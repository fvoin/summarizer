"""Silence auto-stop wiring in the Transcriber (lite) app.

Regression tests for the 2026-07-27 data loss: the lite app started the
recorder without on_auto_stop, so a silence auto-stop silently killed the
session — no finalize, no transcript, leaked system-audio tap, UI stuck on
"Recording", and the next Stop press toggled a NEW recording.
"""

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMainWindow, QPlainTextEdit, QPushButton,
)

from summarizer import app_lite

_app = QApplication.instance() or QApplication([])


class _FakeRecorder:
    def __init__(self, silence_timeout=30, input_device=None):
        self.on_auto_stop = None
        self.stop_called = False
        self.cleanup_called = False

    def start(self, on_auto_stop=None):
        self.on_auto_stop = on_auto_stop
        return "/tmp/fake.wav"

    def stop(self):
        self.stop_called = True
        return None

    def cleanup_sources(self):
        self.cleanup_called = True

    def is_recording(self):
        return not self.stop_called


class _FakeDiarizer(QObject):
    partial = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, *a, **kw):
        super().__init__()
        self.finalized = False

    def start(self):
        pass

    def isRunning(self):
        return False

    def request_finalize(self):
        self.finalized = True

    def request_abort(self):
        pass


class _FakeTray:
    def set_recording(self, *a):
        pass

    def set_processing(self, *a):
        pass

    def set_idle(self, *a):
        pass


def _bare_window(monkeypatch) -> app_lite.LiteWindow:
    """LiteWindow with real Qt plumbing but none of the heavy __init__
    machinery (poller, update checker, tray icon)."""
    monkeypatch.setattr(app_lite, "AudioRecorder", _FakeRecorder)
    monkeypatch.setattr(app_lite, "RealtimeDiarizer", _FakeDiarizer)
    monkeypatch.setattr(app_lite.config, "load", lambda: {})
    win = app_lite.LiteWindow.__new__(app_lite.LiteWindow)
    QMainWindow.__init__(win)
    win._recorder = None
    win._rt_diar = None
    win._start_ts = None
    win._last_duration = 0
    win._agent_meeting = None
    win._workers = []
    win._timer = QTimer(win)
    win._tray = _FakeTray()
    win.status = QLabel()
    win.transcript = QPlainTextEdit()
    win.copy_btn = QPushButton()
    win.record_btn = QPushButton()
    win._wire_auto_stop()
    return win


def test_start_passes_auto_stop_callback(monkeypatch):
    win = _bare_window(monkeypatch)
    win._start()
    assert win._recorder.on_auto_stop is not None


def test_auto_stop_finalizes_like_manual_stop(monkeypatch):
    win = _bare_window(monkeypatch)
    win._start()
    rec, diar = win._recorder, win._rt_diar
    rec.on_auto_stop()  # what the recorder's monitor thread invokes
    _app.processEvents()  # deliver the queued cross-thread signal
    assert rec.stop_called
    assert rec.cleanup_called
    assert diar.finalized  # transcript gets finalized and saved
    assert win._recorder is None  # next button press starts fresh, no toggle trap


def test_auto_stop_after_manual_stop_is_noop(monkeypatch):
    win = _bare_window(monkeypatch)
    win._start()
    rec = win._recorder
    cb = rec.on_auto_stop
    win._stop()  # user pressed Stop first
    status_after_stop = win.status.text()
    cb()
    _app.processEvents()
    assert win.status.text() == status_after_stop  # no double-finalize


def test_manual_stop_with_no_recorder_is_noop(monkeypatch):
    win = _bare_window(monkeypatch)
    win._stop()  # must not raise
    assert win._recorder is None
