"""Lite transcript client: record -> live transcript -> Me/Remote tag -> copy/upload.

Never imports summarizer.summarizer or summarizer.db.
"""

from __future__ import annotations

import logging
import time

from PyQt6.QtGui import QGuiApplication, QColor
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QDialog, QLineEdit, QProgressBar, QStackedWidget, QFormLayout,
)

from . import config, theme
from .i18n import t
from .recorder import AudioRecorder
from .workers import RealtimeDiarizer
from .transcriber import download_model
from .widgets import MicPicker
from .updater import check_for_update, download_and_open
from .tray import TrayIcon

_logger = logging.getLogger("app_lite")


class _LiteUpdateCheckWorker(QThread):
    """Check GitHub for a newer release (edition-aware via config.EDITION)."""
    found = pyqtSignal(dict)

    def run(self):
        try:
            info = check_for_update()
            if info:
                self.found.emit(info)
        except Exception as e:
            _logger.warning("update check failed: %s", e)


class _LiteUpdateDownloadWorker(QThread):
    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            download_and_open(self._url)
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class LiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("lite_title"))
        self.setStyleSheet(theme.window_style())
        self._recorder = None
        self._start_ts = None
        self._last_duration = 0
        self._workers = []

        central = QWidget()
        lay = QVBoxLayout(central)

        self.status = QLabel(t("lite_ready"))
        lay.addWidget(self.status)

        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(t("lite_placeholder"))
        lay.addWidget(self.transcript, 1)

        row = QHBoxLayout()
        self.record_btn = QPushButton(t("start_recording"))
        self.record_btn.setStyleSheet(theme.btn_primary())
        self.record_btn.clicked.connect(self._toggle)
        row.addWidget(self.record_btn)
        self.copy_btn = QPushButton(t("lite_copy"))
        self.copy_btn.setStyleSheet(theme.btn_secondary())
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.setEnabled(False)
        row.addWidget(self.copy_btn)
        self.settings_btn = QPushButton(t("tray_settings"))
        self.settings_btn.setStyleSheet(theme.btn_secondary())
        self.settings_btn.setIcon(theme.gear_icon(22, QColor(theme.C["text_secondary"])))
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.clicked.connect(self._open_settings)
        row.addWidget(self.settings_btn)
        self.update_btn = QPushButton(t("lite_update_btn"))
        self.update_btn.setStyleSheet(theme.btn_secondary())
        self.update_btn.setVisible(False)
        self.update_btn.clicked.connect(self._download_update)
        row.addWidget(self.update_btn)
        lay.addLayout(row)

        self.setCentralWidget(central)
        self.resize(560, 420)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._rt_diar = None  # RealtimeDiarizer for the active recording

        self._agent_meeting = None
        self._poller = None
        cfg = config.load()
        if cfg.get("agent_enabled") and cfg.get("agent_url") and cfg.get("agent_token"):
            from .agent import AgentPoller
            self._poller = AgentPoller(self)
            self._poller.meeting_armed.connect(self._on_meeting_armed)
            self._poller.error.connect(lambda e: _logger.warning("agent: %s", e))
            self._poller.start()
            self.status.setText(t("lite_agent_waiting"))

        # Check for a newer release (downloads the lite DMG when the user opts in).
        self._update_url = None
        self._upd_check = _LiteUpdateCheckWorker(self)
        self._upd_check.found.connect(self._on_update_found)
        self._upd_check.start()

        self._setup_tray()

    # ── tray (menu-bar) ───────────────────────────────────────────
    def _setup_tray(self):
        self._tray = TrayIcon(self, app_name=t("lite_title"))
        self._tray.show_action.triggered.connect(self._tray_show)
        self._tray.rec_action.triggered.connect(self._toggle)
        self._tray.settings_action.triggered.connect(self._open_settings)
        self._tray.quit_action.triggered.connect(self._tray_quit)
        self._tray.show()  # Lite lives in the menu bar

    @staticmethod
    def _set_dock_visible(visible: bool):
        try:
            import AppKit
            policy = (AppKit.NSApplicationActivationPolicyRegular if visible
                      else AppKit.NSApplicationActivationPolicyAccessory)
            AppKit.NSApp.setActivationPolicy_(policy)
            if visible:
                AppKit.NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    def _tray_show(self):
        self._set_dock_visible(True)
        self.show()
        self.raise_()
        self.activateWindow()

    def _tray_quit(self):
        if self._poller:
            self._poller.stop()
            self._poller.wait(2000)
        self._tray.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    def _open_settings(self):
        # Reuse the full app's SettingsDialog in lite mode (hides LLM tabs).
        # Lazily imported so lite startup stays free of the LLM modules.
        from .app import SettingsDialog
        SettingsDialog(self, lite=True).exec()
        self._refresh_agent()

    def _refresh_agent(self):
        """Start/stop the agent poller to match the (possibly changed) config."""
        cfg = config.load()
        want = bool(cfg.get("agent_enabled") and cfg.get("agent_url") and cfg.get("agent_token"))
        if want and self._poller is None:
            from .agent import AgentPoller
            self._poller = AgentPoller(self)
            self._poller.meeting_armed.connect(self._on_meeting_armed)
            self._poller.error.connect(lambda e: _logger.warning("agent: %s", e))
            self._poller.start()
            self.status.setText(t("lite_agent_waiting"))
        elif not want and self._poller is not None:
            self._poller.stop()
            self._poller.wait(2000)
            self._poller = None

    # ── recording ────────────────────────────────────────────────
    def _toggle(self):
        if self._recorder and self._recorder.is_recording():
            self._stop()
        else:
            self._start()

    def _start(self):
        cfg = config.load()
        self._recorder = AudioRecorder(
            silence_timeout=cfg.get("silence_timeout", 30),
            input_device=cfg.get("input_device"),
        )
        self._recorder.start()
        self._start_ts = time.monotonic()
        self.transcript.clear()
        self.copy_btn.setEnabled(False)
        self.record_btn.setText(t("stop_recording", time="0:00"))
        self.record_btn.setStyleSheet(theme.btn_recording())
        self.status.setText(t("status_recording"))
        self._timer.start()
        wm = cfg.get("whisper_model", "base")
        from .i18n import locale
        self._rt_diar = RealtimeDiarizer(wm, self._recorder, locale=locale(), parent=self)
        self._rt_diar.partial.connect(self._set_live)
        self._rt_diar.finished.connect(self._on_transcript)
        self._rt_diar.error.connect(self._on_plain_fallback)
        self._rt_diar.start()
        self._tray.set_recording(True)

    def _on_meeting_armed(self, meeting: dict):
        if self._recorder and self._recorder.is_recording():
            return  # already recording
        self._agent_meeting = meeting
        self._start()
        self.status.setText(t("lite_agent_recording", title=meeting.get("title", "")))

    def _set_live(self, text: str):
        """Live (partial) tagged transcript updates during recording."""
        self.transcript.setPlainText(text)
        sb = self.transcript.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _tick(self):
        if self._start_ts is None:
            return
        secs = int(time.monotonic() - self._start_ts)
        self.record_btn.setText(t("stop_recording", time=f"{secs // 60}:{secs % 60:02d}"))

    def _stop(self):
        self._timer.stop()
        self.record_btn.setText(t("start_recording"))
        self.record_btn.setStyleSheet(theme.btn_primary())
        duration = int(time.monotonic() - self._start_ts) if self._start_ts else 0
        self._start_ts = None

        # Stop capture (fills the RT buffers fully); the diarizer reads them.
        self._recorder.stop()
        self._recorder.cleanup_sources()  # RT diarizer uses in-memory buffers
        self._recorder = None  # the RealtimeDiarizer holds its own reference
        self._last_duration = duration
        self._tray.set_recording(False)
        self._tray.set_processing()
        self.status.setText(t("status_transcribing"))

        if self._rt_diar is not None:
            # Transcription happened live during the meeting — just finalize
            # (transcribe the tail + merge). finished -> _on_transcript.
            self._rt_diar.request_finalize()
        else:
            self._tray.set_idle()
            self.status.setText(t("status_recording_failed"))

    def _on_plain_fallback(self, err):
        self._tray.set_idle()
        self.status.setText(t("lite_error", err=err))

    def _on_transcript(self, text: str):
        self._tray.set_idle()
        self.transcript.setPlainText(text)
        self.copy_btn.setEnabled(bool(text.strip()))
        self.status.setText(t("lite_done"))
        self._handle_result(text)

    def _handle_result(self, text: str):
        meeting = self._agent_meeting
        self._agent_meeting = None
        if not meeting:
            return  # manual recording: copy only
        meeting["_duration"] = self._last_duration
        from .agent import PostCompleteWorker
        worker = PostCompleteWorker(text, meeting)
        worker.finished.connect(lambda _r: self.status.setText(t("lite_uploaded")))
        worker.error.connect(lambda e: self.status.setText(t("lite_upload_failed", err=e)))
        self._track(worker)
        worker.start()

    def _copy(self):
        QGuiApplication.clipboard().setText(self.transcript.toPlainText())
        self.status.setText(t("lite_copied"))

    def _on_update_found(self, info: dict):
        self._update_url = info.get("dmg_url")
        if not self._update_url:
            return
        self.status.setText(t("lite_update_avail", ver=info.get("tag", "")))
        self.update_btn.setVisible(True)

    def _download_update(self):
        if not self._update_url:
            return
        self.status.setText(t("lite_updating"))
        self.update_btn.setEnabled(False)
        worker = _LiteUpdateDownloadWorker(self._update_url, self)
        worker.done.connect(lambda: self.status.setText(t("lite_update_done")))
        worker.error.connect(lambda e: self.status.setText(t("lite_error", err=e)))
        self._track(worker)
        worker.start()

    def _track(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda *_: self._untrack(worker))
        if hasattr(worker, "error"):
            worker.error.connect(lambda *_: self._untrack(worker))

    def _untrack(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)

    def closeEvent(self, event):
        # Stay in the menu bar: hide the window instead of quitting so the
        # agent poller keeps auto-recording. Real quit is via the tray menu.
        self.hide()
        self._set_dock_visible(False)
        event.ignore()


class LiteSetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("lite_setup_title"))
        self._cfg = config.load()
        self._model = self._cfg.get("whisper_model", "base")

        self._stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(self._stack)

        # Step 1 — mic
        s1 = QWidget(); l1 = QVBoxLayout(s1)
        l1.addWidget(QLabel(t("lite_setup_mic")))
        self._mic = MicPicker(selected=self._cfg.get("input_device"))
        l1.addWidget(self._mic)
        b1 = QPushButton(t("wizard_next")); b1.clicked.connect(self._to_backend)
        l1.addWidget(b1)
        self._stack.addWidget(s1)

        # Step 2 — backend
        s2 = QWidget(); l2 = QFormLayout(s2)
        self._url = QLineEdit(self._cfg.get("agent_url", ""))
        self._token = QLineEdit(self._cfg.get("agent_token", ""))
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        l2.addRow(t("lite_setup_url"), self._url)
        l2.addRow(t("lite_setup_token"), self._token)
        b2 = QPushButton(t("wizard_next")); b2.clicked.connect(self._to_download)
        l2.addRow(b2)
        self._stack.addWidget(s2)

        # Step 3 — download
        s3 = QWidget(); l3 = QVBoxLayout(s3)
        l3.addWidget(QLabel(t("lite_setup_download")))
        self._bar = QProgressBar()
        l3.addWidget(self._bar)
        self._stack.addWidget(s3)

        self.resize(420, 240)

    def _to_backend(self):
        self._cfg["input_device"] = self._mic.selected_device()
        self._stack.setCurrentIndex(1)

    def _to_download(self):
        self._cfg["agent_url"] = self._url.text().strip()
        self._cfg["agent_token"] = self._token.text().strip()
        self._cfg["agent_enabled"] = bool(self._cfg["agent_url"])
        self._cfg["whisper_model"] = self._model
        config.save(self._cfg)
        self._stack.setCurrentIndex(2)
        if config.is_model_downloaded(self._model):
            self._bar.setValue(100)
            self.accept()
            return
        self._dl = _LiteModelDownloadWorker(self._model)
        self._dl.progress.connect(lambda p: self._bar.setValue(int(p * 100)))
        self._dl.done.connect(self.accept)
        self._dl.error.connect(lambda e: self.reject())
        self._dl.start()


class _LiteModelDownloadWorker(QThread):
    progress = pyqtSignal(float)
    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model_name):
        super().__init__()
        self._model = model_name

    def run(self):
        try:
            download_model(self._model, progress_cb=lambda p: self.progress.emit(p))
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


def should_run_setup() -> bool:
    cfg = config.load()
    model = cfg.get("whisper_model", "base")
    return not cfg.get("agent_url") or not config.is_model_downloaded(model)


def main():
    import sys
    from PyQt6.QtWidgets import QApplication

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    theme.apply_palette(app)
    if should_run_setup():
        wiz = LiteSetupWizard()
        if wiz.exec() != QDialog.DialogCode.Accepted:
            return
    win = LiteWindow()
    win.show()
    sys.exit(app.exec())
