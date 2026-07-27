"""One-click update flow in the Transcriber (lite) main window."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMainWindow, QProgressBar, QPushButton,
)

from summarizer import app_lite, updater

_app = QApplication.instance() or QApplication([])


# ── worker ───────────────────────────────────────────────────────────────


def _run_worker(monkeypatch, self_update_impl):
    monkeypatch.setattr(updater, "self_update", self_update_impl)
    monkeypatch.setattr(
        updater, "download_and_open",
        lambda url, progress_cb=None: progress_cb and progress_cb(100, 100),
    )
    w = app_lite._LiteUpdateDownloadWorker("https://x/y.dmg")
    got = {"done": None, "progress": [], "error": None}
    w.done.connect(lambda restarting: got.__setitem__("done", restarting))
    w.progress.connect(got["progress"].append)
    w.error.connect(lambda e: got.__setitem__("error", e))
    w.run()  # synchronous: don't spin up the thread in tests
    return got


def test_worker_self_update_reports_progress_and_restart(monkeypatch):
    def fake_self_update(url, progress_cb=None):
        progress_cb(50, 100)
        progress_cb(100, 100)
        return "/tmp/staged.app"

    got = _run_worker(monkeypatch, fake_self_update)
    assert got["done"] is True  # restart required
    assert got["progress"] == [50, 100]
    assert got["error"] is None


def test_worker_falls_back_to_open_dmg_outside_bundle(monkeypatch):
    def refuse(url, progress_cb=None):
        raise RuntimeError("not running from an installed .app bundle")

    got = _run_worker(monkeypatch, refuse)
    assert got["done"] is False  # manual drag-install path, no restart


# ── window ───────────────────────────────────────────────────────────────


class _FakeWorker(QObject):
    done = pyqtSignal(bool)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal()

    instances = []

    def __init__(self, url, parent=None):
        super().__init__()
        _FakeWorker.instances.append(self)

    def start(self):
        self.progress.emit(42)
        self.done.emit(True)


def _bare_window(monkeypatch):
    monkeypatch.setattr(app_lite, "_LiteUpdateDownloadWorker", _FakeWorker)
    win = app_lite.LiteWindow.__new__(app_lite.LiteWindow)
    QMainWindow.__init__(win)
    win._recorder = None
    win._workers = []
    win._update_url = "https://x/y.dmg"
    win.status = QLabel()
    win.update_btn = QPushButton()
    win.update_progress = QProgressBar()
    win.update_progress.setVisible(False)
    return win


def test_update_button_shows_progress_and_restarts(monkeypatch):
    win = _bare_window(monkeypatch)
    restarted = []
    win._restart_for_update = lambda: restarted.append(True)
    win._download_update()
    assert win.update_progress.value() == 42
    # restart is scheduled via a short single-shot; flush Qt timers
    deadline = QTimer()
    for _ in range(50):
        _app.processEvents()
        if restarted:
            break
        import time as _t
        _t.sleep(0.05)
    assert restarted


def test_update_refused_while_recording(monkeypatch):
    win = _bare_window(monkeypatch)

    class _Rec:
        def is_recording(self):
            return True

    win._recorder = _Rec()
    before = len(_FakeWorker.instances)
    win._download_update()
    assert len(_FakeWorker.instances) == before  # no worker spawned mid-recording
