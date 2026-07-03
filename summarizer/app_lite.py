"""Lite transcript client: record -> live transcript -> Me/Remote tag -> copy/upload.

Never imports summarizer.summarizer or summarizer.db.
"""

from __future__ import annotations

import logging
import time

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel,
)

from . import config, theme
from .i18n import t
from .recorder import AudioRecorder
from .workers import LiveTranscriber, DiarizeTranscribeWorker, TranscribeWorker

_logger = logging.getLogger("app_lite")


class LiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("lite_title"))
        self._recorder = None
        self._diar_recorder = None
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
        self.record_btn.clicked.connect(self._toggle)
        row.addWidget(self.record_btn)
        self.copy_btn = QPushButton(t("lite_copy"))
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.setEnabled(False)
        row.addWidget(self.copy_btn)
        lay.addLayout(row)

        self.setCentralWidget(central)
        self.resize(560, 420)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._live = LiveTranscriber(self)
        self._live.text_appended.connect(self._append_live)

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
        self._live.start(self._recorder, wm)

    def _on_meeting_armed(self, meeting: dict):
        if self._recorder and self._recorder.is_recording():
            return  # already recording
        self._agent_meeting = meeting
        self._start()
        self.status.setText(t("lite_agent_recording", title=meeting.get("title", "")))

    def _append_live(self, text: str):
        current = self.transcript.toPlainText()
        sep = " " if current else ""
        self.transcript.setPlainText(current + sep + text)
        sb = self.transcript.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _tick(self):
        if self._start_ts is None:
            return
        secs = int(time.monotonic() - self._start_ts)
        self.record_btn.setText(t("stop_recording", time=f"{secs // 60}:{secs % 60:02d}"))

    def _stop(self):
        self._timer.stop()
        self._live.stop()
        self.record_btn.setText(t("start_recording"))
        self.record_btn.setStyleSheet(theme.btn_primary())
        duration = int(time.monotonic() - self._start_ts) if self._start_ts else 0
        self._start_ts = None

        mixed = self._recorder.stop()
        sources = self._recorder.get_source_files()
        self._diar_recorder = self._recorder
        self._recorder = None
        self._last_duration = duration

        if not mixed:
            self._cleanup_sources()
            self._agent_meeting = None
            self.status.setText(t("status_recording_failed"))
            return

        self.status.setText(t("status_transcribing"))
        cfg = config.load()
        wm = cfg.get("whisper_model", "base")
        mic = sources.get("mic") or []
        sysf = sources.get("system")
        if mic and sysf:
            worker = DiarizeTranscribeWorker(wm, mic[0], sysf)
            worker.finished.connect(self._on_transcript)
            worker.error.connect(self._on_plain_fallback)
            self._track(worker)
            worker.start()
        else:
            self._plain_transcribe(mixed, wm)

    def _plain_transcribe(self, mixed, wm):
        worker = TranscribeWorker(mixed, wm)
        worker.finished.connect(self._on_transcript)
        worker.error.connect(lambda e: (self._cleanup_sources(), self.status.setText(t("lite_error", err=e))))
        self._track(worker)
        worker.start()

    def _on_plain_fallback(self, err):
        self._cleanup_sources()
        self.status.setText(t("lite_error", err=err))

    def _on_transcript(self, text: str):
        self._cleanup_sources()
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

    def _cleanup_sources(self):
        if self._diar_recorder:
            self._diar_recorder.cleanup_sources()
            self._diar_recorder = None

    def _copy(self):
        QGuiApplication.clipboard().setText(self.transcript.toPlainText())
        self.status.setText(t("lite_copied"))

    def _track(self, worker):
        self._workers.append(worker)
        worker.finished.connect(lambda *_: self._untrack(worker))
        if hasattr(worker, "error"):
            worker.error.connect(lambda *_: self._untrack(worker))

    def _untrack(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)

    def closeEvent(self, event):
        if self._poller:
            self._poller.stop()
            self._poller.wait(2000)
        super().closeEvent(event)


def main():
    import sys
    from PyQt6.QtWidgets import QApplication

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    theme.apply_palette(app)
    win = LiteWindow()
    win.show()
    sys.exit(app.exec())
