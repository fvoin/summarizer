"""Summarizer — macOS PyQt6 application."""

import os
import queue
import sys
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl, QSize, QTimer, QMimeData
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import (
    QDragEnterEvent, QDropEvent, QFont, QIcon, QPainter, QPixmap, QColor, QPen,
    QPainterPath,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QLineEdit,
    QFileDialog, QMessageBox, QDialog, QFormLayout, QSpinBox,
    QGroupBox, QSplitter, QProgressBar, QSizePolicy, QSystemTrayIcon,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea, QCheckBox,
)

import logging

from . import config
from .recorder import AudioRecorder
from .transcriber import Transcriber, download_model
from .summarizer import (
    summarize, list_contexts, load_general_context, save_general_context,
    create_context, TRANSCRIPT_EXTENSIONS, AUDIO_EXTENSIONS,
)
from .updater import check_for_update, download_and_open
from .i18n import t
from . import theme
from .theme import C
from .tray import TrayIcon
from .agent import AgentPoller, PostCompleteWorker

_logger = logging.getLogger("app")


def _ask_yes_no(parent, title: str, text: str) -> bool:
    """Show a Yes/No question dialog with localized buttons. Returns True if Yes."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    yes_btn = box.addButton(t("btn_yes"), QMessageBox.ButtonRole.YesRole)
    box.addButton(t("btn_no"), QMessageBox.ButtonRole.NoRole)
    box.exec()
    return box.clickedButton() == yes_btn


# ── Vector icon helpers ──────────────────────────────────────────────────

def _make_eye_icon(size: int = 24, color: QColor = QColor("#4A90D9")) -> QIcon:
    """Draw a high-quality eye icon using 2x rendering for retina sharpness."""
    scale = 2
    s = size * scale
    pm = QPixmap(s, s)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    # Work in logical coords (size x size)
    cx, cy = size / 2, size / 2
    ew = size * 0.42   # eye half-width
    eh = size * 0.22   # eye half-height

    # Outer eye shape
    pen = QPen(color, size * 0.065)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    eye = QPainterPath()
    eye.moveTo(cx - ew, cy)
    eye.cubicTo(cx - ew * 0.5, cy - eh * 1.6, cx + ew * 0.5, cy - eh * 1.6, cx + ew, cy)
    eye.cubicTo(cx + ew * 0.5, cy + eh * 1.6, cx - ew * 0.5, cy + eh * 1.6, cx - ew, cy)
    p.drawPath(eye)

    # Iris circle
    p.setPen(pen)
    ir = size * 0.16
    p.drawEllipse(int(cx - ir), int(cy - ir), int(ir * 2), int(ir * 2))

    # Pupil dot
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    pr = size * 0.07
    p.drawEllipse(int(cx - pr), int(cy - pr), int(pr * 2), int(pr * 2))

    p.end()
    return QIcon(pm)


class _ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def _make_history_icon(size: int = 32, color: QColor = QColor("#4A90D9")) -> QIcon:
    """Draw a simple clock icon for history."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, size * 0.07, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    m = size * 0.15
    p.drawEllipse(int(m), int(m), int(size - m * 2), int(size - m * 2))
    cx, cy = size / 2, size / 2
    p.drawLine(int(cx), int(cy), int(cx), int(cy - size * 0.22))
    p.drawLine(int(cx), int(cy), int(cx + size * 0.18), int(cy))
    p.end()
    return QIcon(pm)


def _make_chat_icon(size: int = 32, color: QColor = QColor("#4A90D9")) -> QIcon:
    """Draw a simple chat bubble icon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, size * 0.07, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Rounded rectangle bubble
    m = size * 0.15
    p.drawRoundedRect(int(m), int(m), int(size - m * 2), int(size * 0.6), size * 0.12, size * 0.12)
    # Small triangle tail
    tail_x = size * 0.3
    tail_y = m + size * 0.6
    path = QPainterPath()
    path.moveTo(tail_x, tail_y - 1)
    path.lineTo(tail_x - size * 0.05, tail_y + size * 0.15)
    path.lineTo(tail_x + size * 0.12, tail_y - 1)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


def _make_rec_dot_icon(size: int = 64, color: QColor = QColor("#D94A4A")) -> QIcon:
    """Draw a filled red circle (record indicator)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    margin = size * 0.2
    p.drawEllipse(int(margin), int(margin), int(size - margin * 2), int(size - margin * 2))
    p.end()
    return QIcon(pm)


def _make_stop_icon(size: int = 64, color: QColor = QColor("#ffffff")) -> QIcon:
    """Draw a square stop icon (white for use on red button)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    margin = size * 0.25
    s = size - margin * 2
    p.drawRoundedRect(int(margin), int(margin), int(s), int(s), 3, 3)
    p.end()
    return QIcon(pm)


def _make_gear_icon(size: int = 32, color: QColor = QColor("#7B68EE")) -> QIcon:
    """Draw a gear/cog icon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)

    cx, cy = size / 2, size / 2
    import math
    outer_r = size * 0.42
    inner_r = size * 0.28
    teeth = 8
    path = QPainterPath()
    for i in range(teeth * 2):
        angle = math.pi * 2 * i / (teeth * 2) - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.closeSubpath()

    hole = QPainterPath()
    hole.addEllipse(cx - size * 0.12, cy - size * 0.12, size * 0.24, size * 0.24)
    path = path.subtracted(hole)

    p.drawPath(path)
    p.end()
    return QIcon(pm)


def _make_copy_icon(size: int = 32, color: QColor = QColor("#4A90D9")) -> QIcon:
    """Draw a clipboard/copy icon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, size * 0.07, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    m = size * 0.12
    w, h = size * 0.55, size * 0.65
    p.drawRoundedRect(int(m), int(size * 0.22), int(w), int(h), 3, 3)
    p.drawRoundedRect(int(size - m - w), int(m), int(w), int(h), 3, 3)
    p.end()
    return QIcon(pm)


def _make_app_icon(size: int = 512) -> QPixmap:
    """Generate a Summarizer app icon with a microphone on a gradient background."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    from PyQt6.QtGui import QLinearGradient
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#4A90D9"))
    grad.setColorAt(1.0, QColor("#7B68EE"))

    corner = size * 0.18
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(0, 0, size, size, corner, corner)

    ic = QColor("#ffffff")
    pen = QPen(ic, size * 0.04, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(ic)

    cx, cy = size / 2, size * 0.38
    rw, rh = size * 0.1, size * 0.18
    p.drawRoundedRect(int(cx - rw), int(cy - rh), int(rw * 2), int(rh * 2), rw, rw)

    p.setBrush(Qt.BrushStyle.NoBrush)
    arc_w, arc_h = size * 0.18, size * 0.2
    p.drawArc(int(cx - arc_w), int(cy), int(arc_w * 2), int(arc_h * 2), 0, -180 * 16)

    stem_top = cy + rh + arc_h * 0.95
    stem_bot = size * 0.72
    p.drawLine(int(cx), int(stem_top), int(cx), int(stem_bot))
    p.drawLine(int(cx - size * 0.1), int(stem_bot), int(cx + size * 0.1), int(stem_bot))

    # sound waves
    p.setBrush(Qt.BrushStyle.NoBrush)
    wave_pen = QPen(QColor(255, 255, 255, 120), size * 0.025, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(wave_pen)
    for i, offset in enumerate([size * 0.22, size * 0.30]):
        arc_rect_w = offset
        arc_rect_h = size * 0.22 + i * size * 0.08
        p.drawArc(int(cx + size * 0.05), int(cy - arc_rect_h / 2), int(arc_rect_w), int(arc_rect_h), 45 * 16, -90 * 16)

    p.end()
    return pm


# ── Worker threads ───────────────────────────────────────────────────────

class TranscribeWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, audio_path: str, whisper_model: str):
        super().__init__()
        self.audio_path = audio_path
        self.whisper_model = whisper_model

    def run(self):
        try:
            self.status.emit(t("status_transcribing"))
            _logger.info("TranscribeWorker: model=%s, audio=%s", self.whisper_model, self.audio_path)
            tr = Transcriber(self.whisper_model)
            text = tr.transcribe(self.audio_path)
            _logger.info("TranscribeWorker: done, %d chars", len(text))
            self.finished.emit(text)
        except Exception as e:
            _logger.exception("TranscribeWorker failed")
            self.error.emit(str(e))


class _ModelPreloadWorker(QThread):
    """Loads the configured Whisper model into the module-level cache at app start."""
    def __init__(self, model_name: str):
        super().__init__()
        self._model_name = model_name

    def run(self):
        try:
            t = Transcriber(self._model_name)
            t._load_model()
            _logger.info("Whisper model '%s' preloaded and cached", self._model_name)
        except Exception as e:
            _logger.warning("Model preload failed: %s", e)


class RealtimeTranscribeWorker(QThread):
    """Transcribes growing audio in real-time, always re-processing the full recording."""
    chunk_ready = pyqtSignal(str, int)  # (text, audio_len) — audio_len = samples that produced this text
    model_ready = pyqtSignal()
    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, whisper_model: str):
        super().__init__()
        self._model_name = whisper_model
        self._queue: queue.Queue = queue.Queue()
        self._transcriber: Optional[Transcriber] = None

    def push_audio(self, audio_data, sample_rate: int):
        """Push the full accumulated audio for transcription."""
        self._queue.put((audio_data, sample_rate))

    def request_final(self, audio_data, sample_rate: int):
        """Push final audio and signal the worker to stop after processing it."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put((audio_data, sample_rate))
        self._queue.put(None)  # sentinel

    def request_stop(self):
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put(None)

    def run(self):
        try:
            self._transcriber = Transcriber(self._model_name)
            self._transcriber._load_model()
            _logger.info("RealtimeTranscribeWorker: model ready (%s)", self._model_name)
            self.model_ready.emit()
        except Exception as e:
            _logger.exception("RealtimeTranscribeWorker: failed to load model")
            self.error.emit(str(e))
            self.done.emit()
            return

        while True:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if item is None:
                break

            # Drain queue: skip stale items, keep only the latest
            latest = item
            is_final = False
            while True:
                try:
                    newer = self._queue.get_nowait()
                    if newer is None:
                        is_final = True
                        break
                    latest = newer
                except queue.Empty:
                    break

            audio_data, sample_rate = latest
            try:
                text = self._transcriber.transcribe_array(audio_data, sample_rate)
                self.chunk_ready.emit(text or "", len(audio_data))
            except Exception as e:
                _logger.warning("RealtimeTranscribeWorker: chunk failed: %s", e)

            if is_final:
                break

        self.done.emit()


class _DeltaTranscribeWorker(QThread):
    """Transcribes a small audio delta (numpy array) and emits the text."""
    finished = pyqtSignal(str)

    def __init__(self, audio_data, sample_rate: int, model_name: str):
        super().__init__()
        self._audio = audio_data
        self._sr = sample_rate
        self._model_name = model_name

    def run(self):
        try:
            t = Transcriber(self._model_name)
            text = t.transcribe_array(self._audio, self._sr)
            self.finished.emit(text or "")
        except Exception as e:
            _logger.warning("Delta transcription failed: %s", e)
            self.finished.emit("")


class SummarizeWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(
        self,
        transcript: str,
        context_name: Optional[str],
        general_text: str = "",
        meeting_text: str = "",
        profile_name: str = "",
        duration_seconds: Optional[int] = None,
    ):
        super().__init__()
        self.transcript = transcript
        self.context_name = context_name
        self.general_text = general_text
        self.meeting_text = meeting_text
        self.profile_name = profile_name
        self.duration_seconds = duration_seconds

    def run(self):
        try:
            self.status.emit(t("status_summarizing"))
            _logger.info("SummarizeWorker: context=%s, profile=%s, transcript_len=%d",
                         self.context_name, self.profile_name, len(self.transcript))
            result = summarize(
                self.transcript,
                self.context_name,
                self.general_text,
                self.meeting_text,
                profile_name=self.profile_name,
                duration_seconds=self.duration_seconds,
            )
            _logger.info("SummarizeWorker: done, result_len=%d", len(result))
            self.finished.emit(result)
        except Exception as e:
            _logger.exception("SummarizeWorker failed")
            self.error.emit(str(e))


# ── Update checker / downloader workers ───────────────────────────────────

class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(dict)   # {"tag", "dmg_url", "notes"}
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            info = check_for_update()
            if info:
                self.update_available.emit(info)
            else:
                self.no_update.emit()
        except Exception as e:
            self.error.emit(str(e))


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int)   # percent 0-100
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, dmg_url: str):
        super().__init__()
        self.dmg_url = dmg_url

    def run(self):
        try:
            def _on_progress(downloaded, total):
                if total > 0:
                    self.progress.emit(int(downloaded * 100 / total))
            download_and_open(self.dmg_url, progress_cb=_on_progress)
            self.finished.emit()
        except Exception as e:
            _logger.exception("Update download failed")
            self.error.emit(str(e))


# ── Model download worker ────────────────────────────────────────────────

class ModelDownloadWorker(QThread):
    finished = pyqtSignal(str)      # model_name
    error = pyqtSignal(str, str)    # model_name, error_msg
    progress = pyqtSignal(str, int) # model_name, percent (0–100)

    def __init__(self, model_name: str):
        super().__init__()
        self.model_name = model_name

    def run(self):
        try:
            self.progress.emit(self.model_name, 0)
            download_model(self.model_name)
            self.progress.emit(self.model_name, 100)
            self.finished.emit(self.model_name)
        except Exception as e:
            self.error.emit(self.model_name, str(e))


# ── Local LLM (Ollama) worker ────────────────────────────────────────────

def _run_streaming(cmd: list, status_signal, timeout: int = 600) -> tuple[int, str]:
    """Run a command, streaming each output line to status_signal. Returns (returncode, full_output)."""
    import subprocess
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines = []
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                lines.append(line)
                status_signal.emit(line[-80:])  # truncate long lines for label
        proc.wait(timeout=timeout)
    except Exception:
        proc.kill()
    return proc.returncode, "\n".join(lines)


class LocalLLMDownloadWorker(QThread):
    finished = pyqtSignal(str)    # model_key
    error = pyqtSignal(str, str)  # model_key, error_msg
    status = pyqtSignal(str)      # status line

    def __init__(self, model_key: str):
        super().__init__()
        self.model_key = model_key

    def run(self):
        info = config.LOCAL_LLM_MODELS.get(self.model_key)
        if not info:
            self.error.emit(self.model_key, "Unknown model")
            return
        try:
            ollama = config.find_ollama()
            if not ollama:
                self.error.emit(self.model_key, "Ollama not found. Use Auto Install first.")
                return
            self.status.emit("Starting Ollama server…")
            config.ensure_ollama_server(ollama)
            self.status.emit(f"Downloading {info['display']} ({info['size_gb']:.1f} GB)…")
            rc, out = _run_streaming([ollama, "pull", info["ollama_name"]], self.status)
            if rc == 0:
                self.finished.emit(self.model_key)
            else:
                last = out.strip().splitlines()[-1] if out.strip() else "Pull failed"
                self.error.emit(self.model_key, f"ollama pull failed:\n{last}")
        except Exception as e:
            self.error.emit(self.model_key, str(e))


class OllamaInstallWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    @staticmethod
    def _find_brew() -> Optional[str]:
        import subprocess
        for path in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew", "brew"]:
            try:
                r = subprocess.run([path, "--version"], capture_output=True, timeout=10)
                if r.returncode == 0:
                    return path
            except Exception:
                continue
        return None

    def run(self):
        try:
            brew = self._find_brew()
            if not brew:
                self.status.emit("Installing Homebrew (this may take a few minutes)…")
                rc, out = _run_streaming(
                    ["/bin/bash", "-c",
                     'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'],
                    self.status, timeout=300,
                )
                brew = self._find_brew()
                if not brew:
                    last = out.strip().splitlines()[-1] if out.strip() else ""
                    self.error.emit(
                        f"Homebrew installation failed.\n{last}\n\n"
                        "Try installing Ollama manually from ollama.com"
                    )
                    return
                self.status.emit("Homebrew installed ✓")

            self.status.emit("Installing Ollama via Homebrew…")
            rc, out = _run_streaming([brew, "install", "ollama"], self.status, timeout=600)
            if rc != 0:
                last = out.strip().splitlines()[-1] if out.strip() else ""
                self.error.emit(f"brew install ollama failed:\n{last}")
                return
            # Verify ollama binary is now reachable
            if not config.find_ollama():
                self.error.emit(
                    "Ollama was installed but the binary wasn't found.\n"
                    "Try opening a new terminal and running: ollama serve"
                )
                return
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ── Settings dialog ──────────────────────────────────────────────────────

class _ModelRow(QWidget):
    """A single row in the whisper model list: radio + label + status + download/delete btn."""
    download_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, model_name: str, info: dict, is_selected: bool, is_downloaded: bool, parent=None):
        super().__init__(parent)
        self.model_name = model_name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)

        from PyQt6.QtWidgets import QRadioButton
        self.radio = QRadioButton()
        self.radio.setChecked(is_selected)
        lay.addWidget(self.radio)

        quality = info.get("quality", "")
        size_mb = info.get("size_mb", 0)
        size_str = f"{size_mb} MB" if size_mb < 1000 else f"{size_mb / 1000:.1f} GB"
        label = QLabel(f"<b>{model_name}</b>  —  {quality}  ({size_str})")
        lay.addWidget(label, 1)

        self.status_label = QLabel()
        lay.addWidget(self.status_label)

        self.dl_btn = QPushButton(t("model_download"))
        self.dl_btn.setMinimumWidth(70)
        self.dl_btn.clicked.connect(lambda: self.download_requested.emit(self.model_name))
        lay.addWidget(self.dl_btn)

        self.del_btn = QPushButton(t("model_delete"))
        self.del_btn.setMinimumWidth(56)
        self.del_btn.setStyleSheet(f"color: {C['error']};")
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.model_name))
        self.del_btn.setVisible(False)
        lay.addWidget(self.del_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(80)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        self._set_downloaded(is_downloaded)

    def _set_downloaded(self, downloaded: bool):
        if downloaded:
            self.status_label.setText(t("model_ready"))
            self.status_label.setStyleSheet(f"color: {C['success']}; font-weight: bold;")
            self.dl_btn.setVisible(False)
            self.del_btn.setVisible(True)
            self.progress_bar.setVisible(False)
        else:
            self.status_label.setText(t("not_downloaded"))
            self.status_label.setStyleSheet(f"color: {C['text_muted']};")
            self.dl_btn.setVisible(True)
            self.del_btn.setVisible(False)

    def set_downloading(self):
        self.dl_btn.setVisible(False)
        self.del_btn.setVisible(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText(t("model_downloading"))
        self.status_label.setStyleSheet(f"color: {C['warning']};")

    def set_download_done(self):
        self.progress_bar.setVisible(False)
        self._set_downloaded(True)

    def set_download_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.dl_btn.setVisible(True)
        self.del_btn.setVisible(False)
        self.status_label.setText(t("model_error"))
        self.status_label.setStyleSheet(f"color: {C['error']};")
        self.status_label.setToolTip(msg)


class SetupWizard(QDialog):
    """Multi-step first-run setup wizard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("wizard_title"))
        self.setMinimumWidth(520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._choice_cloud = True
        self._selected_local_model = "gpt-oss:20b"
        self._selected_whisper = "medium"
        self._download_workers: list = []

        from PyQt6.QtWidgets import QStackedWidget
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        outer.addWidget(self._stack)

        self._stack.addWidget(self._build_step_llm_type())   # 0 — cloud vs local
        self._stack.addWidget(self._build_step_cloud())      # 1 — cloud API key
        self._stack.addWidget(self._build_step_local())      # 2 — local model
        self._stack.addWidget(self._build_step_whisper())    # 3 — whisper model
        self._stack.addWidget(self._build_step_use_case())   # 4 — work vs general
        self._stack.addWidget(self._build_step_download())   # 5 — download progress

    # ── shared helpers ────────────────────────────────────────────────

    def _header(self, layout: QVBoxLayout, title_text: str = "", sub_text: str = ""):
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            lbl = QLabel()
            pm = QPixmap(str(icon_path)).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            lbl.setPixmap(pm)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lbl)
        if title_text:
            tl = QLabel(title_text)
            tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tl.setStyleSheet(f"font-size: 19px; font-weight: 700; color: {C['primary']};")
            layout.addWidget(tl)
        if sub_text:
            sl = QLabel(sub_text)
            sl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sl.setWordWrap(True)
            sl.setStyleSheet(f"font-size: 13px; color: {C['text_secondary']};")
            layout.addWidget(sl)

    def _sep(self, layout: QVBoxLayout):
        s = QWidget()
        s.setFixedHeight(1)
        s.setStyleSheet(f"background: {C['border']};")
        layout.addWidget(s)

    def _nav_row(self, layout: QVBoxLayout, back_idx=-1, next_text="", next_cb=None,
                 skip=False, skip_cb=None, next_enabled=True):
        row = QHBoxLayout()
        if skip:
            sb = QPushButton(t("wizard_skip"))
            sb.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; color: {C['text_secondary']};"
                " font-size: 13px; padding: 8px 16px; }}"
                f" QPushButton:hover {{ color: {C['text']}; }}"
            )
            sb.clicked.connect(skip_cb or self.reject)
            row.addWidget(sb)
        if back_idx >= 0:
            bb = QPushButton(t("wizard_back"))
            bb.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none; color: {C['text_secondary']};"
                " font-size: 13px; padding: 8px 16px; }}"
                f" QPushButton:hover {{ color: {C['text']}; }}"
            )
            bb.clicked.connect(lambda idx=back_idx: self._stack.setCurrentIndex(idx))
            row.addWidget(bb)
        row.addStretch()
        if next_text:
            nb = QPushButton(next_text)
            nb.setMinimumHeight(36)
            nb.setMinimumWidth(120)
            nb.setStyleSheet(theme.btn_secondary())
            nb.setEnabled(next_enabled)
            if next_cb:
                nb.clicked.connect(next_cb)
            row.addWidget(nb)
            self._last_next_btn = nb
        layout.addLayout(row)

    # ── Step 0: Cloud vs Local (radio buttons) ────────────────────────

    def _build_step_llm_type(self) -> QWidget:
        from PyQt6.QtWidgets import QRadioButton
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(28, 24, 28, 20)

        self._header(lay, t("wizard_title"), t("wizard_subtitle"))
        self._sep(lay)
        lay.addSpacing(4)

        lbl = QLabel(t("wizard_llm_type_title"))
        lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {C['primary']};")
        lay.addWidget(lbl)

        self._rb_cloud = QRadioButton(t("wizard_cloud_title"))
        self._rb_cloud.setChecked(True)
        self._rb_cloud.setStyleSheet("font-size: 13px;")
        lay.addWidget(self._rb_cloud)
        cloud_hint = QLabel(t("wizard_cloud_desc"))
        cloud_hint.setStyleSheet(f"font-size: 11px; color: {C['text_secondary']}; margin-left: 24px;")
        lay.addWidget(cloud_hint)

        lay.addSpacing(6)

        self._rb_local = QRadioButton(t("wizard_local_title"))
        self._rb_local.setStyleSheet("font-size: 13px;")
        lay.addWidget(self._rb_local)
        local_hint = QLabel(t("wizard_local_desc"))
        local_hint.setStyleSheet(f"font-size: 11px; color: {C['text_secondary']}; margin-left: 24px;")
        lay.addWidget(local_hint)

        lay.addStretch()
        self._nav_row(lay, skip=True, next_text=t("wizard_next"),
                      next_cb=self._on_type_next)
        return page

    def _on_type_next(self):
        self._choice_cloud = self._rb_cloud.isChecked()
        self._stack.setCurrentIndex(1 if self._choice_cloud else 2)

    # ── Step 1: Cloud API key ─────────────────────────────────────────

    def _build_step_cloud(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(14)
        lay.setContentsMargins(28, 24, 28, 20)

        self._header(lay, t("wizard_cloud_step_title"))
        self._sep(lay)

        gemini_lbl = QLabel(t("wizard_gemini_label"))
        gemini_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        lay.addWidget(gemini_lbl)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText(t("wizard_key_placeholder"))
        self._key_input.setMinimumHeight(36)
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(self._key_input)

        hint = QLabel(t("wizard_key_hint", color=C["primary"]))
        hint.setOpenExternalLinks(True)
        hint.setStyleSheet("font-size: 11px;")
        lay.addWidget(hint)

        lay.addStretch()
        self._nav_row(lay, back_idx=0, next_text=t("wizard_next"),
                      next_cb=self._on_cloud_next, next_enabled=False)
        self._cloud_next_btn = self._last_next_btn
        self._key_input.textChanged.connect(
            lambda: self._cloud_next_btn.setEnabled(bool(self._key_input.text().strip())))
        return page

    def _on_cloud_next(self):
        key = self._key_input.text().strip()
        if not key:
            return
        cfg = config.load()
        cfg["api_key"] = key
        if not cfg.get("model"):
            cfg["model"] = "gemini-3-flash-preview"
        config.save(cfg)
        self._stack.setCurrentIndex(3)  # → whisper

    # ── Step 2: Local model selection ─────────────────────────────────

    def _build_step_local(self) -> QWidget:
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(28, 24, 28, 20)

        self._header(lay, t("wizard_local_step_title"))
        sub = QLabel(t("wizard_local_step_desc"))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"font-size: 12px; color: {C['text_secondary']};")
        lay.addWidget(sub)
        self._sep(lay)

        self._local_bg = QButtonGroup(self)
        for key, info in config.LOCAL_LLM_MODELS.items():
            row_w = QWidget()
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(8, 4, 8, 4)
            rb = QRadioButton()
            rb.setChecked(key == "gpt-oss:20b")
            rb._model_key = key
            self._local_bg.addButton(rb)
            row_h.addWidget(rb)
            disp = info["display"]
            sz = info["size_gb"]
            qual = info["quality"]
            lbl_text = f"<b>{disp}</b>  —  {qual}  ({sz} GB)"
            if key == "gpt-oss:20b":
                color = C["success"]
                rec = t("wizard_recommended")
                lbl_text += f"  <span style='color:{color}; font-size: 11px;'> ★ {rec}</span>"
            lbl = QLabel(lbl_text)
            row_h.addWidget(lbl, 1)
            lay.addWidget(row_w)

        lay.addStretch()
        self._nav_row(lay, back_idx=0, next_text=t("wizard_next"),
                      next_cb=self._on_local_next)
        return page

    def _on_local_next(self):
        for btn in self._local_bg.buttons():
            if btn.isChecked():
                self._selected_local_model = btn._model_key
                break
        cfg = config.load()
        cfg["model"] = self._selected_local_model
        config.save(cfg)
        self._stack.setCurrentIndex(3)  # → whisper

    # ── Step 3: Whisper model selection ───────────────────────────────

    def _build_step_whisper(self) -> QWidget:
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)
        lay.setContentsMargins(28, 24, 28, 20)

        self._header(lay, t("wizard_whisper_title"))
        sub = QLabel(t("wizard_whisper_desc"))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 12px; color: {C['text_secondary']};")
        lay.addWidget(sub)
        self._sep(lay)

        self._whisper_bg = QButtonGroup(self)
        for name, info in config.WHISPER_MODELS.items():
            row_w = QWidget()
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(8, 3, 8, 3)
            rb = QRadioButton()
            rb.setChecked(name == "medium")
            rb._wm_name = name
            self._whisper_bg.addButton(rb)
            row_h.addWidget(rb)
            size_mb = info["size_mb"]
            size_str = f"{size_mb} MB" if size_mb < 1000 else f"{size_mb / 1000:.1f} GB"
            quality = info["quality"]
            lbl_text = f"<b>{name}</b>  —  {quality}  ({size_str})"
            is_bundled = config.is_model_downloaded(name) and name == "base"
            if is_bundled:
                bnd_color = C["text_secondary"]
                bnd_text = t("wizard_bundled")
                lbl_text += f"  <span style='color:{bnd_color}; font-size: 11px;'>({bnd_text})</span>"
            if name == "medium":
                color = C["success"]
                rec = t("wizard_recommended")
                lbl_text += f"  <span style='color:{color}; font-size: 11px;'> ★ {rec}</span>"
            lbl = QLabel(lbl_text)
            row_h.addWidget(lbl, 1)
            lay.addWidget(row_w)

        lay.addStretch()
        back_idx = 1 if self._choice_cloud else 2
        # back_idx changes dynamically, so connect with a lambda
        self._nav_row(lay, next_text=t("wizard_next"), next_cb=self._on_whisper_next)
        # Add a manual back button that goes to the right page
        nav_layout = lay.itemAt(lay.count() - 1).layout()
        bb = QPushButton(t("wizard_back"))
        bb.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {C['text_secondary']};"
            " font-size: 13px; padding: 8px 16px; }}"
            f" QPushButton:hover {{ color: {C['text']}; }}"
        )
        bb.clicked.connect(lambda: self._stack.setCurrentIndex(1 if self._choice_cloud else 2))
        nav_layout.insertWidget(0, bb)
        return page

    def _on_whisper_next(self):
        for btn in self._whisper_bg.buttons():
            if btn.isChecked():
                self._selected_whisper = btn._wm_name
                break
        cfg = config.load()
        cfg["whisper_model"] = self._selected_whisper
        config.save(cfg)
        self._stack.setCurrentIndex(4)  # → use case

    # ── Step 4: Work vs General ───────────────────────────────────────

    def _build_step_use_case(self) -> QWidget:
        from PyQt6.QtWidgets import QRadioButton
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(28, 24, 28, 20)

        self._header(lay, t("wizard_use_step_title"))
        self._sep(lay)
        lay.addSpacing(4)

        self._rb_work = QRadioButton(t("wizard_work_title"))
        self._rb_work.setChecked(True)
        self._rb_work.setStyleSheet("font-size: 13px;")
        lay.addWidget(self._rb_work)
        work_hint = QLabel(t("wizard_work_desc"))
        work_hint.setStyleSheet(f"font-size: 11px; color: {C['text_secondary']}; margin-left: 24px;")
        lay.addWidget(work_hint)

        lay.addSpacing(6)

        self._rb_general = QRadioButton(t("wizard_general_title"))
        self._rb_general.setStyleSheet("font-size: 13px;")
        lay.addWidget(self._rb_general)
        gen_hint = QLabel(t("wizard_general_desc"))
        gen_hint.setStyleSheet(f"font-size: 11px; color: {C['text_secondary']}; margin-left: 24px;")
        lay.addWidget(gen_hint)

        lay.addStretch()
        self._nav_row(lay, back_idx=3, next_text=t("wizard_finish"),
                      next_cb=self._on_use_next)
        return page

    def _on_use_next(self):
        kind = "work" if self._rb_work.isChecked() else "general"
        self._on_use_choice(kind)

    def _on_use_choice(self, kind: str):
        cfg = config.load()
        profiles = cfg.get("instruction_profiles", {})

        work_name = t("profile_work")
        general_name = t("profile_general")

        work_instr = config.get_default_instructions()
        general_instr = config.get_general_instructions()

        profiles[work_name] = work_instr
        profiles[general_name] = general_instr

        if kind == "work":
            cfg["active_profile"] = work_name
            cfg["instructions"] = work_instr
        else:
            cfg["active_profile"] = general_name
            cfg["instructions"] = general_instr

        cfg["instruction_profiles"] = profiles
        config.save(cfg)

        # Check what needs downloading
        needs = self._pending_downloads()
        if needs:
            self._populate_download_page(needs)
            self._stack.setCurrentIndex(5)
        else:
            self.accept()

    # ── Step 5: Download progress ─────────────────────────────────────

    def _build_step_download(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)
        lay.setContentsMargins(28, 24, 28, 20)

        self._header(lay, t("wizard_download_title"))
        self._sep(lay)

        self._dl_desc = QLabel(t("wizard_download_desc"))
        self._dl_desc.setStyleSheet(f"font-size: 12px; color: {C['text_secondary']};")
        lay.addWidget(self._dl_desc)

        self._dl_list_layout = QVBoxLayout()
        self._dl_list_layout.setSpacing(6)
        lay.addLayout(self._dl_list_layout)

        lay.addStretch()

        self._dl_status = QLabel()
        self._dl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dl_status.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {C['primary']};")
        lay.addWidget(self._dl_status)

        btn_row = QHBoxLayout()
        skip_btn = QPushButton(t("wizard_skip"))
        skip_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {C['text_secondary']};"
            " font-size: 13px; padding: 8px 16px; }}"
            f" QPushButton:hover {{ color: {C['text']}; }}"
        )
        skip_btn.clicked.connect(self.accept)
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()
        self._dl_action_btn = QPushButton(t("wizard_download_now"))
        self._dl_action_btn.setMinimumHeight(36)
        self._dl_action_btn.setMinimumWidth(140)
        self._dl_action_btn.setStyleSheet(theme.btn_secondary())
        self._dl_action_btn.clicked.connect(self._start_downloads)
        btn_row.addWidget(self._dl_action_btn)
        lay.addLayout(btn_row)
        return page

    def _pending_downloads(self) -> list:
        """Return list of (type, key, label) for models that need downloading."""
        needs = []
        wm = self._selected_whisper
        if not config.is_model_downloaded(wm):
            info = config.WHISPER_MODELS.get(wm, {})
            sz = info.get("size_mb", 0)
            sz_str = f"{sz} MB" if sz < 1000 else f"{sz / 1000:.1f} GB"
            needs.append(("whisper", wm, f"Whisper {wm} ({sz_str})"))
        if not self._choice_cloud:
            key = self._selected_local_model
            info = config.LOCAL_LLM_MODELS.get(key, {})
            if not config.is_local_llm_downloaded(key):
                needs.append(("ollama", key, f"{info.get('display', key)} ({info.get('size_gb', '?')} GB)"))
        return needs

    def _populate_download_page(self, needs: list):
        # Clear existing rows
        while self._dl_list_layout.count():
            item = self._dl_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._dl_rows = {}
        for dtype, key, label in needs:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 2, 4, 2)
            name_lbl = QLabel(f"• {label}")
            name_lbl.setStyleSheet("font-size: 13px;")
            rl.addWidget(name_lbl, 1)
            status_lbl = QLabel("—")
            status_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px;")
            rl.addWidget(status_lbl)
            prog = QProgressBar()
            prog.setRange(0, 0)
            prog.setFixedWidth(100)
            prog.setFixedHeight(8)
            prog.setTextVisible(False)
            prog.setVisible(False)
            rl.addWidget(prog)
            self._dl_rows[key] = {"type": dtype, "status": status_lbl, "progress": prog}
            self._dl_list_layout.addWidget(row)
        self._dl_status.clear()
        self._dl_action_btn.setEnabled(True)
        self._dl_action_btn.setText(t("wizard_download_now"))

    def _start_downloads(self):
        self._dl_action_btn.setEnabled(False)
        self._dl_action_btn.setText(t("wizard_downloading_models"))
        self._dl_pending = len(self._dl_rows)
        self._dl_errors = []
        for key, info in self._dl_rows.items():
            info["status"].setText(t("model_downloading"))
            info["status"].setStyleSheet(f"color: {C['warning']};")
            info["progress"].setVisible(True)
            if info["type"] == "whisper":
                worker = ModelDownloadWorker(key)
                worker.finished.connect(lambda name: self._on_dl_item_done(name))
                worker.error.connect(lambda name, msg: self._on_dl_item_error(name, msg))
                self._download_workers.append(worker)
                worker.start()
            else:
                worker = LocalLLMDownloadWorker(key)
                worker.finished.connect(lambda name: self._on_dl_item_done(name))
                worker.error.connect(lambda name, msg: self._on_dl_item_error(name, msg))
                self._download_workers.append(worker)
                worker.start()

    def _on_dl_item_done(self, key: str):
        if key in self._dl_rows:
            self._dl_rows[key]["status"].setText(t("model_ready"))
            self._dl_rows[key]["status"].setStyleSheet(f"color: {C['success']}; font-weight: bold;")
            self._dl_rows[key]["progress"].setVisible(False)
        self._dl_pending -= 1
        if self._dl_pending <= 0:
            self._on_all_downloads_done()

    def _on_dl_item_error(self, key: str, msg: str):
        if key in self._dl_rows:
            self._dl_rows[key]["status"].setText(t("model_error"))
            self._dl_rows[key]["status"].setStyleSheet(f"color: {C['error']};")
            self._dl_rows[key]["status"].setToolTip(msg)
            self._dl_rows[key]["progress"].setVisible(False)
        self._dl_errors.append(msg)
        self._dl_pending -= 1
        if self._dl_pending <= 0:
            self._on_all_downloads_done()

    def _on_all_downloads_done(self):
        if self._dl_errors:
            self._dl_status.setText(t("wizard_download_error", error=self._dl_errors[0][:80]))
            self._dl_status.setStyleSheet(f"font-size: 12px; color: {C['danger']};")
        else:
            self._dl_status.setText(t("wizard_download_complete"))
            self._dl_status.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {C['success']};")
        self._dl_action_btn.setText(t("wizard_finish"))
        self._dl_action_btn.setEnabled(True)
        self._dl_action_btn.clicked.disconnect()
        self._dl_action_btn.clicked.connect(self.accept)


class _OllamaChatWorker(QThread):
    """Send a single message to an Ollama model in a background thread."""
    reply_chunk = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model_name: str, messages: list):
        super().__init__()
        self._model = model_name
        self._messages = messages

    def run(self):
        try:
            from openai import OpenAI
            ollama = config.find_ollama()
            if ollama:
                config.ensure_ollama_server(ollama)
            client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
            stream = client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    self.reply_chunk.emit(delta.content)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()


class OllamaChatDialog(QDialog):
    """Small modal chat window for testing a local LLM."""

    def __init__(self, model_key: str, display_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("chat_title", name=display_name))
        self.resize(480, 420)
        self._model = model_key
        self._messages: list[dict] = []
        self._worker: Optional[_OllamaChatWorker] = None

        vlay = QVBoxLayout(self)

        self._chat_view = QTextEdit()
        self._chat_view.setReadOnly(True)
        self._chat_view.setPlaceholderText(t("chat_placeholder"))
        vlay.addWidget(self._chat_view, 1)

        hlay = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(t("chat_placeholder"))
        self._input.returnPressed.connect(self._send)
        hlay.addWidget(self._input, 1)

        self._send_btn = QPushButton(t("chat_send"))
        self._send_btn.setStyleSheet(theme.btn_secondary())
        self._send_btn.clicked.connect(self._send)
        hlay.addWidget(self._send_btn)
        vlay.addLayout(hlay)

        # Thinking indicator
        self._thinking_timer = QTimer(self)
        self._thinking_dots = 0
        self._thinking_anchor = 0
        self._thinking_timer.timeout.connect(self._update_thinking)

    def _update_thinking(self):
        self._thinking_dots = (self._thinking_dots % 3) + 1
        dots = "." * self._thinking_dots
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        pos = cursor.position()
        cursor.setPosition(self._thinking_anchor)
        cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
        cursor.insertText(dots)
        self._chat_view.setTextCursor(cursor)
        sb = self._chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _send(self):
        text = self._input.text().strip()
        if not text or self._worker is not None:
            return
        self._input.clear()
        self._messages.append({"role": "user", "content": text})
        self._chat_view.append(f"<b style='color:{C['primary']};'>You:</b> {text}")
        self._chat_view.append(f"<b style='color:{C['chat_assistant']};'>{self._model}:</b> ")
        # Mark anchor for thinking dots
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._thinking_anchor = cursor.position()
        self._set_busy(True)
        self._thinking_dots = 0
        self._thinking_timer.start(400)

        self._worker = _OllamaChatWorker(self._model, list(self._messages))
        self._assistant_buf = ""
        self._worker.reply_chunk.connect(self._on_chunk)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_chunk(self, text: str):
        if self._thinking_timer.isActive():
            self._thinking_timer.stop()
            cursor = self._chat_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            pos = cursor.position()
            cursor.setPosition(self._thinking_anchor)
            cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        self._assistant_buf += text
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self._chat_view.setTextCursor(cursor)
        self._chat_view.ensureCursorVisible()

    def _on_error(self, msg: str):
        self._thinking_timer.stop()
        self._chat_view.append(f"<span style='color:{C['error']};'>Error: {msg}</span>")

    def _on_done(self):
        self._thinking_timer.stop()
        if self._assistant_buf:
            self._messages.append({"role": "assistant", "content": self._assistant_buf})
            try:
                cursor = self._chat_view.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                pos = cursor.position()
                anchor = min(self._thinking_anchor, pos)
                cursor.setPosition(anchor)
                cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                cursor.insertHtml(_mrkdwn_to_display_html(self._assistant_buf))
            except Exception:
                pass
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._send_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        if not busy:
            self._input.setFocus()

    def closeEvent(self, event):
        self._thinking_timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        super().closeEvent(event)


class _LLMChatWorker(QThread):
    """Send messages to any configured LLM (cloud or local) in a background thread."""
    reply_chunk = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, system: str, messages: list):
        super().__init__()
        self._system = system
        self._messages = messages

    def run(self):
        try:
            cfg = config.load()
            config.apply_env(cfg)
            model = cfg.get("model", "gemini-2.5-pro")
            m = model.lower()

            msgs = [{"role": "system", "content": self._system}] + self._messages

            if m in config.LOCAL_LLM_MODELS or "ollama:" in m:
                self._call_openai_compat("http://localhost:11434/v1", "ollama", model, msgs)
            elif "gemini" in m:
                self._call_gemini(model, msgs)
            elif "claude" in m:
                self._call_anthropic(model, msgs)
            else:
                self._call_openai_compat(None, None, model, msgs)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def _call_openai_compat(self, base_url, api_key, model, msgs):
        from openai import OpenAI
        kwargs = {}
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key
        if "ollama" in (api_key or ""):
            ollama = config.find_ollama()
            if ollama:
                config.ensure_ollama_server(ollama)
        client = OpenAI(**kwargs)
        resp = client.chat.completions.create(model=model, messages=msgs)
        self.reply_chunk.emit(resp.choices[0].message.content.strip())

    def _call_gemini(self, model, msgs):
        import google.generativeai as genai
        import os
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key, transport="rest")
        system = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
        user_parts = []
        for m in msgs[1:]:
            user_parts.append(f"{m['role'].title()}: {m['content']}")
        gmodel = genai.GenerativeModel(model, system_instruction=system)
        response = gmodel.generate_content("\n\n".join(user_parts))
        self.reply_chunk.emit(response.text)

    def _call_anthropic(self, model, msgs):
        import anthropic
        system = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
        api_msgs = [m for m in msgs if m["role"] != "system"]
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model, max_tokens=4096, system=system, messages=api_msgs,
        )
        self.reply_chunk.emit(response.content[0].text)


class ContextChatDialog(QDialog):
    """Chat dialog for asking questions about meeting context."""

    def __init__(self, context_text: str, summary_text: str = "", context_name: str = "", parent=None):
        super().__init__(parent)
        title = t("context_chat_title")
        if context_name:
            title = f"{title} — {context_name}"
        self.setWindowTitle(title)
        self.resize(560, 480)
        self._system = t("context_chat_system", context=context_text)
        if summary_text:
            self._system += f"\n\nLast summary:\n{summary_text}"
        self._messages: list[dict] = []
        self._worker: Optional[_LLMChatWorker] = None

        vlay = QVBoxLayout(self)

        self._chat_view = QTextEdit()
        self._chat_view.setReadOnly(True)
        self._chat_view.setPlaceholderText(t("chat_placeholder"))
        vlay.addWidget(self._chat_view, 1)

        hlay = QHBoxLayout()
        self._input = QTextEdit()
        self._input.setPlaceholderText(t("chat_placeholder"))
        self._input.setMinimumHeight(32)
        self._input.setMaximumHeight(100)
        self._input.setFixedHeight(32)
        self._input.setAcceptRichText(False)
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.installEventFilter(self)
        hlay.addWidget(self._input, 1)

        self._send_btn = QPushButton(t("chat_send"))
        self._send_btn.setStyleSheet(theme.btn_secondary())
        self._send_btn.clicked.connect(self._send)
        hlay.addWidget(self._send_btn)
        vlay.addLayout(hlay)

        # Thinking indicator
        self._thinking_timer = QTimer(self)
        self._thinking_dots = 0
        self._thinking_anchor = 0
        self._thinking_timer.timeout.connect(self._update_thinking)

    def eventFilter(self, obj, event):
        """Enter sends, Shift+Enter inserts newline, auto-resize height."""
        if obj is self._input and event.type() == event.Type.KeyPress:
            from PyQt6.QtCore import QEvent
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    return False  # let Qt insert newline
                self._send()
                return True
        # Auto-resize input height based on content
        if obj is self._input and event.type() == event.Type.KeyRelease:
            doc_height = int(self._input.document().size().height()) + 8
            new_h = max(32, min(100, doc_height))
            self._input.setFixedHeight(new_h)
        return super().eventFilter(obj, event)

    def _append_text(self, html: str):
        """Append HTML without extra <p> wrapper."""
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertHtml(html)
        self._chat_view.setTextCursor(cursor)
        self._chat_view.ensureCursorVisible()

    def _update_thinking(self):
        self._thinking_dots = (self._thinking_dots % 3) + 1
        dots = "." * self._thinking_dots
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        pos = cursor.position()
        cursor.setPosition(self._thinking_anchor)
        cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
        cursor.insertText(dots)
        self._chat_view.setTextCursor(cursor)
        sb = self._chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _send(self):
        text = self._input.toPlainText().strip()
        if not text or self._worker is not None:
            return
        self._input.clear()
        self._messages.append({"role": "user", "content": text})
        self._chat_view.append(f"<b style='color:{C['primary']};'>You:</b> {text}")
        self._chat_view.append(f"<b style='color:{C['chat_assistant']};'>AI:</b> ")
        # Mark position for thinking dots
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._thinking_anchor = cursor.position()
        self._set_busy(True)
        self._thinking_dots = 0
        self._thinking_timer.start(400)

        self._worker = _LLMChatWorker(self._system, list(self._messages))
        self._assistant_buf = ""
        self._worker.reply_chunk.connect(self._on_chunk)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_chunk(self, text: str):
        # Stop thinking animation and clear dots on first chunk
        if self._thinking_timer.isActive():
            self._thinking_timer.stop()
            cursor = self._chat_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            pos = cursor.position()
            cursor.setPosition(self._thinking_anchor)
            cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        self._assistant_buf += text
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self._chat_view.setTextCursor(cursor)
        self._chat_view.ensureCursorVisible()

    def _on_error(self, msg: str):
        self._thinking_timer.stop()
        self._append_text(f"<br><span style='color:{C['error']};'>Error: {msg}</span><br>")

    def _on_done(self):
        self._thinking_timer.stop()
        if self._assistant_buf:
            self._messages.append({"role": "assistant", "content": self._assistant_buf})
            try:
                cursor = self._chat_view.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                pos = cursor.position()
                anchor = min(self._thinking_anchor, pos)
                cursor.setPosition(anchor)
                cursor.setPosition(pos, cursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                cursor.insertHtml(_mrkdwn_to_display_html(self._assistant_buf))
            except Exception:
                pass
        self._append_text("<br>")
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._send_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        if not busy:
            self._send_btn.setText(t("chat_send"))
            self._input.setFocus()

    def closeEvent(self, event):
        self._thinking_timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        super().closeEvent(event)


def _mrkdwn_to_display_html(text: str) -> str:
    """Convert mrkdwn/markdown bold/italic/headers to HTML for display."""
    import re
    body = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Headers: # text, ## text, ### text, #### text → bold
    body = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", body, flags=re.MULTILINE)
    # **bold** (markdown double asterisk)
    body = re.sub(r"\*\*([^\n*]+?)\*\*", r"<b>\1</b>", body)
    # *bold* (slack mrkdwn single asterisk)
    body = re.sub(r"(?<!\w)\*([^\n*]+?)\*(?!\w)", r"<b>\1</b>", body)
    # _italic_
    body = re.sub(r"(?<!\w)_([^\n_]+?)_(?!\w)", r"<i>\1</i>", body)
    body = body.replace("\n", "<br>")
    return body


class _TextViewDialog(QDialog):
    """Text viewer/editor with optional save callback. Shows rendered markdown."""

    def __init__(self, title: str, text: str, parent=None,
                 save_cb=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(560, 420)
        self._save_cb = save_cb
        self._raw_text = text
        self._editing = False

        vlay = QVBoxLayout(self)
        self._view = QTextEdit()
        self._view.setReadOnly(True)
        self._view.setHtml(_mrkdwn_to_display_html(text))
        vlay.addWidget(self._view, 1)

        if save_cb:
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            self._edit_btn = QPushButton(t("ctx_editor_edit"))
            self._edit_btn.setStyleSheet(theme.btn_secondary())
            self._edit_btn.clicked.connect(self._toggle_edit)
            btn_row.addWidget(self._edit_btn)
            self._save_btn = QPushButton(t("ctx_editor_save"))
            self._save_btn.setStyleSheet(theme.btn_secondary())
            self._save_btn.clicked.connect(self._save)
            self._save_btn.setVisible(False)
            btn_row.addWidget(self._save_btn)
            vlay.addLayout(btn_row)

    def _toggle_edit(self):
        self._editing = not self._editing
        if self._editing:
            self._view.setReadOnly(False)
            self._view.setPlainText(self._raw_text)
            self._edit_btn.setVisible(False)
            self._save_btn.setVisible(True)
        else:
            self._raw_text = self._view.toPlainText()
            self._view.setReadOnly(True)
            self._view.setHtml(_mrkdwn_to_display_html(self._raw_text))
            self._edit_btn.setVisible(True)
            self._save_btn.setVisible(False)

    def _save(self):
        if self._save_cb:
            self._raw_text = self._view.toPlainText()
            self._save_cb(self._raw_text)
        self.accept()


class ContextEditorDialog(QDialog):
    """Editor for a context: persistent context + meeting history table."""

    def __init__(self, context_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("ctx_editor_title", name=context_name))
        self.resize(700, 500)
        self._name = context_name

        from . import db

        vlay = QVBoxLayout(self)

        # Persistent context
        lbl = QLabel(t("ctx_editor_persistent"))
        lbl.setStyleSheet(f"font-size: 12px; color: {C['text_secondary']};")
        vlay.addWidget(lbl)
        self._ctx_edit = QTextEdit()
        self._ctx_edit.setPlainText(db.load_general_context(context_name))
        self._ctx_edit.setMaximumHeight(120)
        vlay.addWidget(self._ctx_edit)

        # Meetings list (same style as HistoryDialog)
        vlay.addSpacing(12)
        mtg_lbl = QLabel(t("ctx_editor_meetings"))
        mtg_lbl.setStyleSheet(f"font-size: 12px; color: {C['text_secondary']};")
        vlay.addWidget(mtg_lbl)

        meetings = db.list_meetings(context_name=context_name)
        if meetings:
            _no_border = "border: none; background: transparent;"

            # Column header
            header_row = QHBoxLayout()
            header_row.setContentsMargins(8, 0, 8, 4)
            header_row.setSpacing(12)
            for label_text, width in [
                (t("history_col_date"), 120),
                (t("history_col_duration"), 90),
            ]:
                h_lbl = QLabel(f"<b>{label_text}</b>")
                h_lbl.setFixedWidth(width)
                h_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; {_no_border}")
                header_row.addWidget(h_lbl)
            header_row.addStretch()
            for label_text in [t("history_context"), t("history_transcript"), t("history_summary")]:
                h_lbl = QLabel(f"<b>{label_text}</b>")
                h_lbl.setFixedWidth(90)
                h_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                h_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; {_no_border}")
                header_row.addWidget(h_lbl)
            vlay.addLayout(header_row)

            # Scrollable rows
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(scroll.Shape.NoFrame)
            inner = QWidget()
            inner_lay = QVBoxLayout(inner)
            inner_lay.setSpacing(0)
            inner_lay.setContentsMargins(0, 0, 0, 0)

            eye = _make_eye_icon(16, QColor(C["primary"]))
            for m in meetings:
                row = QWidget()
                row.setStyleSheet(f"border-bottom: 1px solid {C['border']};")
                hlay = QHBoxLayout(row)
                hlay.setContentsMargins(8, 6, 8, 6)
                hlay.setSpacing(12)

                ts = m.get("started_at", "")[:16].replace("T", " ")
                dur = m.get("duration_seconds", 0)
                dur_str = f"{dur // 60}m {dur % 60}s" if dur else "—"

                date_lbl = QLabel(ts)
                date_lbl.setStyleSheet(f"color: {C['text_secondary']}; {_no_border}")
                date_lbl.setFixedWidth(120)
                hlay.addWidget(date_lbl)

                dur_lbl = QLabel(dur_str)
                dur_lbl.setStyleSheet(f"color: {C['text_muted']}; {_no_border}")
                dur_lbl.setFixedWidth(90)
                hlay.addWidget(dur_lbl)

                hlay.addStretch()

                for field, tip in [
                    ("meeting_context", t("history_context")),
                    ("transcript", t("history_transcript")),
                    ("summary", t("history_summary")),
                ]:
                    btn_wrap = QWidget()
                    btn_wrap.setFixedWidth(90)
                    btn_wrap.setStyleSheet(_no_border)
                    blay = QHBoxLayout(btn_wrap)
                    blay.setContentsMargins(0, 0, 0, 0)
                    blay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    has_content = bool(m.get(field, "").strip())
                    if has_content:
                        btn = QPushButton()
                        btn.setIcon(eye)
                        btn.setIconSize(QSize(16, 16))
                        btn.setFixedSize(28, 28)
                        btn.setToolTip(tip)
                        btn.setStyleSheet(theme.ghost_btn() + f" QPushButton {{ {_no_border} }}")
                        btn.clicked.connect(lambda _, mid=m["id"], f=field: self._view_text(mid, f))
                        blay.addWidget(btn)
                    hlay.addWidget(btn_wrap)

                inner_lay.addWidget(row)

            inner_lay.addStretch()
            scroll.setWidget(inner)
            vlay.addWidget(scroll, 1)
        else:
            empty = QLabel(t("ctx_editor_no_meetings"))
            empty.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vlay.addWidget(empty, 1)

        # Save button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton(t("ctx_editor_save"))
        save_btn.setStyleSheet(theme.btn_secondary())
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        vlay.addLayout(btn_row)

    def _view_text(self, meeting_id: int, field: str):
        from . import db
        m = db.get_meeting(meeting_id)
        if not m:
            return
        text = m.get(field, "")
        field_labels = {
            "meeting_context": t("history_context"),
            "transcript": t("history_transcript"),
            "summary": t("history_summary"),
        }
        type_label = field_labels.get(field, field)
        title = t("history_view_title", type=type_label, title=self._name)

        def save_cb(new_text, mid=meeting_id, f=field):
            conn = db.get_connection()
            conn.execute(f"UPDATE meetings SET {f} = ? WHERE id = ?", (new_text, mid))
            conn.commit()

        dlg = _TextViewDialog(title, text, self, save_cb=save_cb)
        dlg.exec()

    def _save(self):
        from . import db
        db.save_general_context(self._name, self._ctx_edit.toPlainText().strip())
        self.accept()


class HistoryDialog(QDialog):
    """Dialog showing all recorded meetings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("history_title"))
        self.resize(700, 500)

        from . import db

        vlay = QVBoxLayout(self)
        vlay.setContentsMargins(12, 12, 12, 12)
        self._meetings = db.list_meetings()

        if not self._meetings:
            empty = QLabel(t("history_empty"))
            empty.setStyleSheet(f"color: {C['text_muted']}; font-size: 13px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vlay.addWidget(empty, 1)
            return

        # Column header
        _no_border = "border: none; background: transparent;"
        header_row = QHBoxLayout()
        header_row.setContentsMargins(8, 0, 8, 4)
        header_row.setSpacing(12)
        for label_text, width in [
            (t("history_col_context"), 240),
            (t("history_col_date"), 120),
            (t("history_col_duration"), 90),
        ]:
            lbl = QLabel(f"<b>{label_text}</b>")
            lbl.setFixedWidth(width)
            lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; {_no_border}")
            header_row.addWidget(lbl)
        header_row.addStretch()
        for label_text in [t("history_transcript"), t("history_summary")]:
            lbl = QLabel(f"<b>{label_text}</b>")
            lbl.setFixedWidth(90)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; {_no_border}")
            header_row.addWidget(lbl)
        vlay.addLayout(header_row)

        # Scrollable rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setSpacing(0)
        inner_lay.setContentsMargins(0, 0, 0, 0)

        eye = _make_eye_icon(16, QColor(C["primary"]))
        for m in self._meetings:
            row = QWidget()
            row.setStyleSheet(f"border-bottom: 1px solid {C['border']};")
            hlay = QHBoxLayout(row)
            hlay.setContentsMargins(8, 6, 8, 6)
            hlay.setSpacing(12)

            ctx = m.get("context_name") or "—"
            ts = m.get("started_at", "")[:16].replace("T", " ")
            dur = m.get("duration_seconds", 0)
            if dur:
                mins, secs = divmod(dur, 60)
                dur_str = f"{mins}m {secs}s"
            else:
                dur_str = "—"

            ctx_lbl = _ClickableLabel(f"<b>{ctx}</b>")
            ctx_lbl.setFixedWidth(240)
            ctx_lbl.setToolTip(t("history_change_series_tt"))
            ctx_lbl.setStyleSheet(
                f"QLabel {{ border: none; background: transparent; }}"
                f"QLabel:hover {{ color: {C['primary']}; }}"
            )
            ctx_lbl.clicked.connect(lambda mid=m["id"], lbl=ctx_lbl: self._change_series(mid, lbl))
            hlay.addWidget(ctx_lbl)

            date_lbl = QLabel(ts)
            date_lbl.setStyleSheet(f"color: {C['text_secondary']}; {_no_border}")
            date_lbl.setFixedWidth(120)
            hlay.addWidget(date_lbl)

            dur_lbl = QLabel(dur_str)
            dur_lbl.setStyleSheet(f"color: {C['text_muted']}; {_no_border}")
            dur_lbl.setFixedWidth(90)
            hlay.addWidget(dur_lbl)

            hlay.addStretch()

            for field, tip in [("transcript", t("history_transcript")), ("summary", t("history_summary"))]:
                btn_wrap = QWidget()
                btn_wrap.setFixedWidth(90)
                btn_wrap.setStyleSheet(_no_border)
                blay = QHBoxLayout(btn_wrap)
                blay.setContentsMargins(0, 0, 0, 0)
                blay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                has_content = bool(m.get(field, "").strip())
                if has_content:
                    btn = QPushButton()
                    btn.setIcon(eye)
                    btn.setIconSize(QSize(16, 16))
                    btn.setFixedSize(28, 28)
                    btn.setToolTip(tip)
                    btn.setStyleSheet(theme.ghost_btn() + f" QPushButton {{ {_no_border} }}")
                    btn.clicked.connect(lambda _, mid=m["id"], title=ctx, f=field: self._view_text(mid, f, title))
                    blay.addWidget(btn)
                hlay.addWidget(btn_wrap)

            inner_lay.addWidget(row)

        inner_lay.addStretch()
        scroll.setWidget(inner)
        vlay.addWidget(scroll, 1)

    def _view_text(self, meeting_id: int, field: str, title: str):
        from . import db
        m = db.get_meeting(meeting_id)
        if not m:
            return
        text = m.get(field, "")
        dlg_title = t("history_view_title", type=t(f"history_{field}"), title=title)

        def save_cb(new_text, mid=meeting_id, f=field):
            conn = db.get_connection()
            conn.execute(f"UPDATE meetings SET {f} = ? WHERE id = ?", (new_text, mid))
            conn.commit()

        dlg = _TextViewDialog(dlg_title, text, self, save_cb=save_cb)
        dlg.exec()

    def _change_series(self, meeting_id: int, label: QLabel):
        from . import db
        from PyQt6.QtWidgets import QInputDialog

        existing = db.list_contexts()
        current = next((mm.get("context_name") for mm in self._meetings if mm["id"] == meeting_id), None)

        dlg = QDialog(self)
        dlg.setWindowTitle(t("history_change_series"))
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        combo = QComboBox()
        NEW_SENTINEL = "__NEW__"
        combo.addItem(t("history_no_series"), None)
        for name in existing:
            combo.addItem(name, name)
        combo.addItem(t("history_new_series"), NEW_SENTINEL)

        if current and current in existing:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(0)  # No series
        lay.addWidget(combo)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton(t("btn_yes"))
        ok_btn.setStyleSheet(theme.btn_secondary())
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton(t("btn_no"))
        cancel_btn.setStyleSheet(theme.btn_secondary())
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        choice = combo.currentData()
        if choice == NEW_SENTINEL:
            name, ok = QInputDialog.getText(self, t("new_context_title"), t("new_context_prompt"))
            if not ok:
                return
            name = name.strip()
            if not name:
                return
            new_ctx = name
        else:
            new_ctx = choice  # None or existing name

        if new_ctx == current:
            return

        db.update_meeting_context(meeting_id, new_ctx)

        for mm in self._meetings:
            if mm["id"] == meeting_id:
                mm["context_name"] = new_ctx
                break
        label.setText(f"<b>{new_ctx or t('history_no_series_short')}</b>")


class _LocalLLMRow(QWidget):
    """Row for a local Ollama LLM model: radio + label + status + pull/delete."""
    download_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    test_requested = pyqtSignal(str)

    def __init__(self, model_key: str, info: dict, is_selected: bool, is_downloaded: bool, parent=None):
        super().__init__(parent)
        self.model_key = model_key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 2, 4, 2)

        from PyQt6.QtWidgets import QRadioButton
        self.radio = QRadioButton()
        self.radio.setChecked(is_selected)
        lay.addWidget(self.radio)

        size_str = f"{info['size_gb']:.1f} GB"
        label = QLabel(f"<b>{info['display']}</b>  —  {info['quality']}  ({size_str})")
        lay.addWidget(label, 1)

        self.status_label = QLabel()
        lay.addWidget(self.status_label)

        self.test_btn = QPushButton(t("model_test"))
        self.test_btn.setMinimumWidth(40)
        self.test_btn.setStyleSheet(theme.flat_btn())
        self.test_btn.clicked.connect(lambda: self.test_requested.emit(self.model_key))
        self.test_btn.setVisible(False)
        lay.addWidget(self.test_btn)

        self.dl_btn = QPushButton(t("model_download"))
        self.dl_btn.setMinimumWidth(70)
        self.dl_btn.setStyleSheet(theme.flat_btn())
        self.dl_btn.clicked.connect(lambda: self.download_requested.emit(self.model_key))
        lay.addWidget(self.dl_btn)

        self.del_btn = QPushButton(t("model_delete"))
        self.del_btn.setMinimumWidth(56)
        self.del_btn.setStyleSheet(theme.flat_btn(C["error"]))
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.model_key))
        self.del_btn.setVisible(False)
        lay.addWidget(self.del_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(80)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        self._set_downloaded(is_downloaded)

    def _set_downloaded(self, downloaded: bool):
        if downloaded:
            self.status_label.setText(t("model_ready"))
            self.status_label.setStyleSheet(f"color: {C['success']}; font-weight: bold;")
            self.dl_btn.setVisible(False)
            self.del_btn.setVisible(True)
            self.test_btn.setVisible(True)
            self.progress_bar.setVisible(False)
        else:
            self.status_label.setText(t("not_downloaded"))
            self.status_label.setStyleSheet(f"color: {C['text_muted']};")
            self.dl_btn.setVisible(True)
            self.del_btn.setVisible(False)
            self.test_btn.setVisible(False)

    def set_pulling(self):
        self.dl_btn.setVisible(False)
        self.del_btn.setVisible(False)
        self.test_btn.setVisible(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText(t("model_pulling"))
        self.status_label.setStyleSheet(f"color: {C['warning']};")

    def set_pull_done(self):
        self.progress_bar.setVisible(False)
        self._set_downloaded(True)

    def set_pull_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.dl_btn.setVisible(True)
        self.del_btn.setVisible(False)
        self.test_btn.setVisible(False)
        self.status_label.setText(t("model_error"))
        self.status_label.setStyleSheet(f"color: {C['error']};")
        self.status_label.setToolTip(msg)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, bg_whisper: dict = None, bg_llm: dict = None):
        super().__init__(parent)
        self.setWindowTitle(t("settings_title"))
        self.setMinimumWidth(580)
        self.setMinimumHeight(820)
        self.cfg = config.load()
        # Workers are stored on MainWindow and survive dialog close
        self._download_workers: dict[str, ModelDownloadWorker] = bg_whisper if bg_whisper is not None else {}
        self._model_rows: dict[str, _ModelRow] = {}
        self._local_llm_workers: dict[str, LocalLLMDownloadWorker] = bg_llm if bg_llm is not None else {}
        self._local_llm_rows: dict[str, _LocalLLMRow] = {}
        self._build_ui()
        self._reconnect_bg_workers()

    def _reconnect_bg_workers(self):
        """Re-attach signals of still-running background workers to the new UI rows."""
        for model_name, worker in list(self._download_workers.items()):
            if worker.isRunning():
                row = self._model_rows.get(model_name)
                if row:
                    row.set_downloading()
                    try:
                        worker.finished.disconnect()
                        worker.error.disconnect()
                    except TypeError:
                        pass
                    worker.finished.connect(self._on_download_finished)
                    worker.error.connect(self._on_download_error)
            else:
                self._download_workers.pop(model_name, None)

        for model_key, worker in list(self._local_llm_workers.items()):
            if worker.isRunning():
                row = self._local_llm_rows.get(model_key)
                if row:
                    row.set_pulling()
                    try:
                        worker.finished.disconnect()
                        worker.error.disconnect()
                        worker.status.disconnect()
                    except TypeError:
                        pass
                    worker.finished.connect(self._on_local_llm_finished)
                    worker.error.connect(self._on_local_llm_error)
                    worker.status.connect(lambda s, r=row: (
                        r.status_label.setText(s[-60:]),
                        r.status_label.setStyleSheet(f"color: {C['warning']};"),
                    ))
            else:
                self._local_llm_workers.pop(model_key, None)

    def _build_ui(self):
        from PyQt6.QtWidgets import QTabWidget, QButtonGroup, QRadioButton, QCheckBox, QScrollArea

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(8)

        tabs = QTabWidget()
        outer.addWidget(tabs)

        # ── TAB: Models ───────────────────────────────────────────────────
        models_scroll = QScrollArea()
        models_scroll.setWidgetResizable(True)
        models_scroll.setFrameShape(models_scroll.Shape.NoFrame)
        models_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        models_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        models_inner = QWidget()
        models_vlay = QVBoxLayout(models_inner)
        models_vlay.setContentsMargins(8, 8, 8, 8)
        models_vlay.setSpacing(10)

        # AI Model group
        llm_group = QGroupBox(t("ai_model_group"))
        llm_vlay = QVBoxLayout(llm_group)
        llm_vlay.setSpacing(2)

        self._all_model_radio_group = QButtonGroup(self)
        current_model = self.cfg.get("model", "")

        cloud_lbl = QLabel(t("cloud_label"))
        cloud_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; font-weight: bold; margin-top: 4px;")
        llm_vlay.addWidget(cloud_lbl)

        self._cloud_rows: list[tuple[str, QRadioButton]] = []
        for model_id, display_name in config.CLOUD_LLM_PRESETS:
            row_w = QWidget()
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(12, 1, 4, 1)
            rb = QRadioButton(display_name)
            rb.setChecked(current_model == model_id)
            self._all_model_radio_group.addButton(rb)
            row_h.addWidget(rb, 1)
            llm_vlay.addWidget(row_w)
            self._cloud_rows.append((model_id, rb))

        custom_row_w = QWidget()
        custom_row_h = QHBoxLayout(custom_row_w)
        custom_row_h.setContentsMargins(12, 1, 4, 1)
        self._custom_rb = QRadioButton(t("custom_label"))
        self._all_model_radio_group.addButton(self._custom_rb)
        custom_row_h.addWidget(self._custom_rb)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText(t("model_placeholder"))
        self.model_edit.setFixedHeight(22)
        custom_row_h.addWidget(self.model_edit, 1)
        llm_vlay.addWidget(custom_row_w)

        preset_ids = [m for m, _ in config.CLOUD_LLM_PRESETS]
        local_ids = list(config.LOCAL_LLM_MODELS.keys())
        if current_model in preset_ids or current_model in local_ids:
            self.model_edit.setText("")
        else:
            self.model_edit.setText(current_model)
            self._custom_rb.setChecked(True)
        self._custom_rb.toggled.connect(lambda on: self.model_edit.setEnabled(on))
        self.model_edit.setEnabled(self._custom_rb.isChecked())

        # API Key + Base URL
        creds_w = QWidget()
        creds_h = QHBoxLayout(creds_w)
        creds_h.setContentsMargins(12, 6, 4, 4)
        creds_h.addWidget(QLabel(t("api_key_label")))
        self.key_edit = QLineEdit(self.cfg.get("api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText(t("api_key_placeholder"))
        creds_h.addWidget(self.key_edit, 2)
        creds_h.addWidget(QLabel(t("base_url_label")))
        self.base_url_edit = QLineEdit(self.cfg.get("base_url", ""))
        self.base_url_edit.setPlaceholderText(t("base_url_placeholder"))
        creds_h.addWidget(self.base_url_edit, 2)
        llm_vlay.addWidget(creds_w)

        # Local (Ollama) sub-section
        local_lbl = QLabel(t("local_label"))
        local_lbl.setStyleSheet(f"color: {C['text_secondary']}; font-size: 11px; font-weight: bold; margin-top: 6px;")
        llm_vlay.addWidget(local_lbl)

        ollama_ok = config.is_ollama_available()
        if not ollama_ok:
            hint = QLabel(t("ollama_not_found"))
            hint.setOpenExternalLinks(True)
            hint.setStyleSheet(f"color: {C['text_muted']}; font-size: 10px; margin-left: 12px;")
            llm_vlay.addWidget(hint)

        pulled = config.list_ollama_models() if ollama_ok else []
        for key, info in config.LOCAL_LLM_MODELS.items():
            downloaded = config.is_local_llm_downloaded(key, _pulled=pulled) if ollama_ok else False
            row = _LocalLLMRow(key, info, is_selected=(current_model == key), is_downloaded=downloaded)
            row.download_requested.connect(self._pull_local_llm)
            row.delete_requested.connect(self._delete_local_llm)
            row.test_requested.connect(self._test_local_llm)
            self._all_model_radio_group.addButton(row.radio)
            llm_vlay.addWidget(row)
            self._local_llm_rows[key] = row

        models_vlay.addWidget(llm_group)

        # Whisper model group
        whisper_group = QGroupBox(t("whisper_group"))
        whisper_lay = QVBoxLayout(whisper_group)
        current_wm = self.cfg.get("whisper_model", "base")
        if not config.is_model_downloaded(current_wm):
            downloaded_list = config.list_downloaded_models()
            if downloaded_list:
                current_wm = downloaded_list[0]

        self._radio_group = QButtonGroup(self)
        for i, (name, info) in enumerate(config.WHISPER_MODELS.items()):
            is_dl = config.is_model_downloaded(name)
            row = _ModelRow(name, info, is_selected=(name == current_wm), is_downloaded=is_dl)
            row.download_requested.connect(self._download_model)
            row.delete_requested.connect(self._delete_whisper_model)
            whisper_lay.addWidget(row)
            self._model_rows[name] = row
            self._radio_group.addButton(row.radio, i)

        models_vlay.addSpacing(12)
        models_vlay.addWidget(whisper_group)
        models_vlay.addStretch()
        models_scroll.setWidget(models_inner)
        # Models tab added below after General tab

        # ── TAB: Instructions ─────────────────────────────────────────────
        instr_tab = QWidget()
        instr_outer = QVBoxLayout(instr_tab)
        instr_outer.setContentsMargins(8, 8, 8, 8)
        instr_outer.setSpacing(6)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(6)
        self.profile_combo = theme.FlatComboBox()
        self._reload_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        profile_row.addWidget(self.profile_combo, 1)

        new_profile_btn = QPushButton(t("new_btn"))
        new_profile_btn.setMinimumWidth(50)
        new_profile_btn.clicked.connect(self._new_profile)
        profile_row.addWidget(new_profile_btn)

        self.del_profile_btn = QPushButton(t("delete_btn"))
        self.del_profile_btn.setMinimumWidth(56)
        self.del_profile_btn.clicked.connect(self._delete_profile)
        profile_row.addWidget(self.del_profile_btn)
        instr_outer.addLayout(profile_row)

        active_profile = self.cfg.get("active_profile", config.DEFAULT_PROFILE_NAME)
        self.instructions_edit = QTextEdit()
        self.instructions_edit.setPlainText(config.get_profile(active_profile))
        self.instructions_edit.setPlaceholderText(t("instructions_placeholder"))
        instr_outer.addWidget(self.instructions_edit, 1)

        # Instructions tab added below after General tab

        # ── TAB: General ──────────────────────────────────────────────────
        general_tab = QWidget()
        general_form = QFormLayout(general_tab)
        general_form.setContentsMargins(12, 12, 12, 12)
        general_form.setSpacing(8)

        # Theme selector
        self.theme_combo = theme.FlatComboBox()
        _theme_keys = theme.THEME_NAMES
        _theme_labels = {"light": t("theme_light"), "dark": t("theme_dark"), "nord": t("theme_nord")}
        for key in _theme_keys:
            self.theme_combo.addItem(_theme_labels.get(key, key), key)
        saved_theme = self.cfg.get("theme", "light")
        idx = self.theme_combo.findData(saved_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        theme_layout = QVBoxLayout()
        theme_layout.addWidget(self.theme_combo)
        theme_hint = QLabel(t("theme_restart_hint"))
        theme_hint.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px;")
        theme_layout.addWidget(theme_hint)
        theme_widget = QWidget()
        theme_widget.setLayout(theme_layout)
        general_form.addRow(t("theme_label"), theme_widget)

        self.menubar_check = QCheckBox(t("menubar_check"))
        self.menubar_check.setChecked(bool(self.cfg.get("menubar_enabled", False)))
        general_form.addRow(t("menubar_label"), self.menubar_check)

        self.sound_on_done_check = QCheckBox(t("sound_check"))
        self.sound_on_done_check.setChecked(bool(self.cfg.get("sound_on_done", True)))
        general_form.addRow(t("sound_label"), self.sound_on_done_check)

        update_row = QHBoxLayout()
        update_row.setSpacing(8)
        self._update_btn = QPushButton(t("check_updates"))
        self._update_btn.clicked.connect(self._check_for_updates)
        update_row.addWidget(self._update_btn)
        self._update_progress = QProgressBar()
        self._update_progress.setMaximumHeight(18)
        self._update_progress.setVisible(False)
        update_row.addWidget(self._update_progress)
        update_row.addStretch()
        version_label = QLabel(f"v{config.APP_VERSION}")
        version_label.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px;")
        update_row.addWidget(version_label)
        general_form.addRow("", update_row)

        tabs.addTab(general_tab, t("tab_general"))
        tabs.addTab(models_scroll, t("tab_models"))
        tabs.addTab(instr_tab, t("tab_instructions"))

        # ── TAB: Advanced ─────────────────────────────────────────────────
        adv_tab = QWidget()
        adv_form = QFormLayout(adv_tab)
        adv_form.setSpacing(8)
        adv_form.setContentsMargins(12, 12, 12, 12)

        self.context_limit_spin = QSpinBox()
        self.context_limit_spin.setRange(500, 50000)
        self.context_limit_spin.setSingleStep(500)
        self.context_limit_spin.setValue(int(self.cfg.get("context_limit", 5000)))
        self.context_limit_spin.setSuffix(" chars")
        adv_form.addRow(t("context_limit_label"), self.context_limit_spin)

        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(5, 300)
        self.silence_spin.setValue(int(self.cfg.get("silence_timeout", 30)))
        self.silence_spin.setSuffix(" sec")
        adv_form.addRow(t("silence_timeout_label"), self.silence_spin)

        self.device_combo = theme.FlatComboBox()
        self.device_combo.addItem(t("device_default"), None)
        for dev in AudioRecorder.list_devices():
            self.device_combo.addItem(dev["name"], dev["id"])
        saved_dev = self.cfg.get("input_device")
        if saved_dev is not None:
            for i in range(self.device_combo.count()):
                if self.device_combo.itemData(i) == saved_dev:
                    self.device_combo.setCurrentIndex(i)
                    break
        adv_form.addRow(t("input_device_label"), self.device_combo)

        self.save_audio_check = QCheckBox(t("save_audio_check"))
        self.save_audio_check.setChecked(bool(self.cfg.get("save_audio", False)))
        adv_form.addRow(t("save_audio_label"), self.save_audio_check)

        self.transcribe_only_check = QCheckBox(t("transcribe_only_check"))
        self.transcribe_only_check.setChecked(bool(self.cfg.get("transcribe_only", False)))
        adv_form.addRow(t("mode_label"), self.transcribe_only_check)

        self.recordings_edit = QLineEdit(self.cfg.get("recordings_dir", ""))
        self.recordings_edit.setPlaceholderText(t("recordings_dir_placeholder"))
        adv_form.addRow(t("recordings_dir_label"), self.recordings_edit)

        logs_btn = QPushButton(t("open_log"))
        logs_btn.setToolTip(str(config.get_log_path()))
        logs_btn.clicked.connect(self._open_logs)
        adv_form.addRow(t("diagnostics_label"), logs_btn)

        adv_form.addRow(QLabel(""))  # spacer

        # Recording Agent group
        agent_group = QGroupBox(t("agent_group"))
        agent_vlay = QVBoxLayout(agent_group)
        agent_inner = QFormLayout()
        agent_inner.setSpacing(8)

        self.agent_url_edit = QLineEdit(self.cfg.get("agent_url", ""))
        self.agent_url_edit.setPlaceholderText(t("agent_url_placeholder"))
        agent_inner.addRow(t("agent_url_label"), self.agent_url_edit)

        self.agent_token_edit = QLineEdit(self.cfg.get("agent_token", ""))
        self.agent_token_edit.setPlaceholderText(t("agent_token_placeholder"))
        self.agent_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        agent_inner.addRow(t("agent_token_label"), self.agent_token_edit)

        self.agent_enabled_check = QCheckBox(t("agent_enabled_check"))
        self.agent_enabled_check.setChecked(bool(self.cfg.get("agent_enabled", False)))
        agent_inner.addRow("", self.agent_enabled_check)

        agent_vlay.addLayout(agent_inner)

        test_row = QHBoxLayout()
        self._agent_test_btn = QPushButton(t("agent_test_btn"))
        self._agent_test_btn.clicked.connect(self._test_agent_connection)
        test_row.addWidget(self._agent_test_btn)
        self._agent_test_status = QLabel("")
        self._agent_test_status.setWordWrap(True)
        self._agent_test_status.setStyleSheet(f"font-size: 11px; color: {C['text_secondary']};")
        test_row.addWidget(self._agent_test_status, 1)
        agent_vlay.addLayout(test_row)

        adv_form.addRow(agent_group)

        tabs.addTab(adv_tab, t("tab_advanced"))

        # ── Save / Cancel row ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        save_btn = QPushButton(t("save_btn"))
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton(t("cancel_btn"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

    def _open_logs(self):
        log_path = config.get_log_path()
        if not log_path.exists():
            QMessageBox.information(self, t("logs_title"), t("logs_no_file"))
            return
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))

    def _check_for_updates(self):
        self._update_btn.setEnabled(False)
        self._update_btn.setText(t("checking_updates"))
        worker = UpdateCheckWorker()
        worker.update_available.connect(self._on_update_available)
        worker.no_update.connect(self._on_no_update)
        worker.error.connect(self._on_update_error)
        self._update_worker = worker
        worker.start()

    def _on_update_available(self, info: dict):
        self._update_btn.setText(t("check_updates"))
        self._update_btn.setEnabled(True)
        tag = info["tag"]
        notes = info.get("notes", "")
        preview = notes[:300] + "…" if len(notes) > 300 else notes
        msg = t("update_available_msg", tag=tag, notes=preview)
        if _ask_yes_no(self, t("update_available_title"), msg):
            self._start_download(info["dmg_url"])

    def _on_no_update(self):
        self._update_btn.setText(t("check_updates"))
        self._update_btn.setEnabled(True)
        QMessageBox.information(self, t("up_to_date_title"),
                                t("up_to_date_msg", version=config.APP_VERSION))

    def _on_update_error(self, msg: str):
        self._update_btn.setText(t("check_updates"))
        self._update_btn.setEnabled(True)
        QMessageBox.warning(self, t("update_check_failed"), msg)

    def _start_download(self, dmg_url: str):
        self._update_btn.setEnabled(False)
        self._update_btn.setText(t("downloading_update"))
        self._update_progress.setValue(0)
        self._update_progress.setVisible(True)
        worker = UpdateDownloadWorker(dmg_url)
        worker.progress.connect(self._update_progress.setValue)
        worker.finished.connect(self._on_update_download_finished)
        worker.error.connect(self._on_update_download_error)
        self._download_worker = worker
        worker.start()

    def _on_update_download_finished(self):
        self._update_progress.setVisible(False)
        self._update_btn.setText(t("check_updates"))
        self._update_btn.setEnabled(True)

        from pathlib import Path
        dmg_path = Path.home() / "Downloads" / "Summarizer.dmg"

        dlg = QDialog(self)
        dlg.setWindowTitle(t("update_ready_title"))
        dlg.setFixedWidth(400)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 20, 24, 20)

        title_lbl = QLabel(t("update_ready_msg"))
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(title_lbl)

        info_lbl = QLabel(t("update_install_instructions"))
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("font-size: 13px;")
        lay.addWidget(info_lbl)

        lay.addSpacing(4)

        btn_row = QHBoxLayout()
        later_btn = QPushButton(t("later_btn"))
        later_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {C['text_secondary']}; font-size: 13px; padding: 8px 14px; }}"
            f" QPushButton:hover {{ color: {C['text']}; }}"
        )
        later_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(later_btn)
        btn_row.addStretch()

        quit_btn = QPushButton(t("quit_open_dmg"))
        quit_btn.setMinimumHeight(34)
        quit_btn.setStyleSheet(theme.btn_primary())
        quit_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(quit_btn)
        lay.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            import subprocess
            subprocess.Popen(["open", str(dmg_path)])
            parent = self.parent()
            if parent and hasattr(parent, '_stop_agent'):
                parent._stop_agent()
            QApplication.quit()

    def _on_update_download_error(self, msg: str):
        self._update_progress.setVisible(False)
        self._update_btn.setText(t("check_updates"))
        self._update_btn.setEnabled(True)
        QMessageBox.warning(self, t("download_failed"), msg)

    def _reload_profile_combo(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        active = self.cfg.get("active_profile", config.DEFAULT_PROFILE_NAME)
        for name in config.list_profiles():
            self.profile_combo.addItem(name, name)
        idx = self.profile_combo.findData(active)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.profile_combo.blockSignals(False)
        self._update_delete_btn()

    def _update_delete_btn(self):
        if not hasattr(self, "del_profile_btn"):
            return
        name = self.profile_combo.currentData()
        self.del_profile_btn.setEnabled(
            bool(name) and name != config.DEFAULT_PROFILE_NAME
        )

    def _on_profile_selected(self):
        name = self.profile_combo.currentData()
        if name:
            self._save_current_profile_text()
            self.instructions_edit.setPlainText(config.get_profile(name))
            self.cfg["active_profile"] = name
        self._update_delete_btn()

    def _save_current_profile_text(self):
        name = self.cfg.get("active_profile", config.DEFAULT_PROFILE_NAME)
        text = self.instructions_edit.toPlainText().strip()
        if name and text:
            config.save_profile(name, text)

    def _new_profile(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, t("new_profile_title"), t("new_profile_prompt"))
        if not ok or not name.strip():
            return
        name = name.strip()
        config.save_profile(name, config.DEFAULT_INSTRUCTIONS)
        self.cfg["active_profile"] = name
        self._reload_profile_combo()
        idx = self.profile_combo.findData(name)
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)
        self.instructions_edit.setPlainText(config.DEFAULT_INSTRUCTIONS)

    def _delete_profile(self):
        name = self.profile_combo.currentData()
        if not name or name == config.DEFAULT_PROFILE_NAME:
            return
        if not _ask_yes_no(self, t("delete_profile_title"), t("delete_profile_confirm", name=name)):
            return
        config.delete_profile(name)
        new_cfg = config.load()
        self.cfg["active_profile"] = new_cfg["active_profile"]
        self._reload_profile_combo()
        self.instructions_edit.setPlainText(
            config.get_profile(self.cfg["active_profile"])
        )

    def _get_selected_whisper_model(self) -> str:
        for name, row in self._model_rows.items():
            if row.radio.isChecked():
                return name
        return "base"

    def _get_selected_model(self) -> str:
        """Return the model id from whichever radio is checked in the AI Model group."""
        for model_id, rb in self._cloud_rows:
            if rb.isChecked():
                return model_id
        for key, row in self._local_llm_rows.items():
            if row.radio.isChecked():
                return key
        # custom
        return self.model_edit.text().strip()

    def _get_selected_local_llm(self) -> Optional[str]:
        for key, row in self._local_llm_rows.items():
            if row.radio.isChecked():
                return key
        return None

    # ── Whisper download / delete ─────────────────────────────────────

    def _download_model(self, model_name: str):
        if model_name in self._download_workers:
            return
        row = self._model_rows.get(model_name)
        if row:
            row.set_downloading()
        worker = ModelDownloadWorker(model_name)
        worker.finished.connect(self._on_download_finished)
        worker.error.connect(self._on_download_error)
        self._download_workers[model_name] = worker
        worker.start()

    def _on_download_finished(self, model_name: str):
        self._download_workers.pop(model_name, None)
        row = self._model_rows.get(model_name)
        if row:
            row.set_download_done()

    def _on_download_error(self, model_name: str, msg: str):
        self._download_workers.pop(model_name, None)
        row = self._model_rows.get(model_name)
        if row:
            row.set_download_error(msg)

    def _delete_whisper_model(self, model_name: str):
        if config.is_model_bundled(model_name):
            QMessageBox.information(
                self, t("bundled_model_title"),
                t("bundled_model_msg", name=model_name),
            )
            return
        if not _ask_yes_no(self, t("delete_whisper_title"), t("delete_whisper_confirm", name=model_name)):
            return
        try:
            config.delete_whisper_model(model_name)
        except Exception as e:
            QMessageBox.critical(self, t("error_title"), str(e))
            return
        row = self._model_rows.get(model_name)
        if row:
            row._set_downloaded(False)

    # ── Local LLM pull / delete ───────────────────────────────────────

    def _pull_local_llm(self, model_key: str):
        if model_key in self._local_llm_workers:
            return
        if not config.is_ollama_available():
            self._offer_ollama_install(model_key)
            return
        self._do_pull_local_llm(model_key)

    def _offer_ollama_install(self, pending_model_key: str):
        from PyQt6.QtGui import QDesktopServices
        msg = QMessageBox(self)
        msg.setWindowTitle(t("ollama_required_title"))
        msg.setText(t("ollama_required_msg"))
        brew_btn = msg.addButton(t("auto_install_btn"), QMessageBox.ButtonRole.AcceptRole)
        web_btn = msg.addButton(t("open_download_page"), QMessageBox.ButtonRole.HelpRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()

        if msg.clickedButton() == brew_btn:
            self._pending_pull_model = pending_model_key
            self._install_ollama_worker = OllamaInstallWorker()
            self._install_ollama_worker.status.connect(
                lambda s: self._set_ollama_install_hint(s)
            )
            self._install_ollama_worker.finished.connect(self._on_ollama_installed)
            self._install_ollama_worker.error.connect(self._on_ollama_install_error)
            self._set_ollama_install_hint(t("installing_ollama"))
            self._install_ollama_worker.start()
        elif msg.clickedButton() == web_btn:
            QDesktopServices.openUrl(QUrl("https://ollama.com/download"))

    def _set_ollama_install_hint(self, text: str):
        for row in self._local_llm_rows.values():
            row.status_label.setText(text)
            row.status_label.setStyleSheet(f"color: {C['warning']};")

    def _on_ollama_installed(self):
        for row in self._local_llm_rows.values():
            row.status_label.setText(t("ollama_ready"))
            row.status_label.setStyleSheet(f"color: {C['success']}; font-weight: bold;")
        pending = getattr(self, "_pending_pull_model", None)
        if pending:
            self._do_pull_local_llm(pending)
            self._pending_pull_model = None

    def _on_ollama_install_error(self, msg: str):
        for row in self._local_llm_rows.values():
            row.status_label.setText(t("not_downloaded"))
            row.status_label.setStyleSheet(f"color: {C['text_muted']};")
        QMessageBox.critical(self, t("ollama_install_failed"), msg)

    def _do_pull_local_llm(self, model_key: str):
        row = self._local_llm_rows.get(model_key)
        if row:
            row.set_pulling()
        worker = LocalLLMDownloadWorker(model_key)
        worker.finished.connect(self._on_local_llm_finished)
        worker.error.connect(self._on_local_llm_error)
        if row:
            worker.status.connect(lambda s, r=row: (
                r.status_label.setText(s[-60:]),
                r.status_label.setStyleSheet(f"color: {C['warning']};"),
            ))
        self._local_llm_workers[model_key] = worker
        worker.start()

    def _on_local_llm_finished(self, model_key: str):
        self._local_llm_workers.pop(model_key, None)
        row = self._local_llm_rows.get(model_key)
        if row:
            row.set_pull_done()

    def _on_local_llm_error(self, model_key: str, msg: str):
        self._local_llm_workers.pop(model_key, None)
        row = self._local_llm_rows.get(model_key)
        if row:
            row.set_pull_error(msg)
        QMessageBox.critical(self, t("local_model_error"), msg)

    def _delete_local_llm(self, model_key: str):
        info = config.LOCAL_LLM_MODELS.get(model_key, {})
        name = info.get("display", model_key)
        if not _ask_yes_no(self, t("delete_local_title"), t("delete_local_confirm", name=name)):
            return
        config.delete_local_llm(model_key)
        row = self._local_llm_rows.get(model_key)
        if row:
            row._set_downloaded(False)

    def _test_local_llm(self, model_key: str):
        info = config.LOCAL_LLM_MODELS.get(model_key, {})
        display = info.get("display", model_key)
        ollama_name = info.get("ollama_name", model_key)
        dlg = OllamaChatDialog(ollama_name, display, parent=self)
        dlg.exec()

    def _save(self):
        selected_wm = self._get_selected_whisper_model()
        if not config.is_model_downloaded(selected_wm):
            if not _ask_yes_no(self, t("model_not_downloaded_title"), t("model_not_downloaded_msg", name=selected_wm)):
                return
        active_profile = self.profile_combo.currentData() or config.DEFAULT_PROFILE_NAME
        instructions_text = self.instructions_edit.toPlainText().strip()
        config.save_profile(active_profile, instructions_text)

        self.cfg["model"] = self._get_selected_model()
        self.cfg["api_key"] = self.key_edit.text().strip()
        self.cfg["base_url"] = self.base_url_edit.text().strip()
        self.cfg["active_profile"] = active_profile
        self.cfg["instructions"] = instructions_text
        cfg_full = config.load()
        self.cfg["instruction_profiles"] = cfg_full.get("instruction_profiles", {})
        self.cfg["whisper_model"] = selected_wm
        self.cfg["save_audio"] = self.save_audio_check.isChecked()
        self.cfg["sound_on_done"] = self.sound_on_done_check.isChecked()
        self.cfg["transcribe_only"] = self.transcribe_only_check.isChecked()
        self.cfg["context_limit"] = self.context_limit_spin.value()
        self.cfg["silence_timeout"] = self.silence_spin.value()
        self.cfg["input_device"] = self.device_combo.currentData()
        self.cfg["recordings_dir"] = self.recordings_edit.text().strip()
        self.cfg["theme"] = self.theme_combo.currentData() or "light"
        self.cfg["menubar_enabled"] = self.menubar_check.isChecked()
        self.cfg["agent_url"] = self.agent_url_edit.text().strip().rstrip("/")
        self.cfg["agent_token"] = self.agent_token_edit.text().strip()
        self.cfg["agent_enabled"] = self.agent_enabled_check.isChecked()
        config.save(self.cfg)
        self.accept()

    def _test_agent_connection(self):
        import json
        import ssl
        import urllib.request
        import certifi

        url = self.agent_url_edit.text().strip().rstrip("/")
        token = self.agent_token_edit.text().strip()
        if not url or not token:
            self._agent_test_status.setText(t("agent_test_fail", error="URL and token required"))
            self._agent_test_status.setStyleSheet(f"font-size: 11px; color: {C['error']};")
            return

        self._agent_test_btn.setEnabled(False)
        self._agent_test_status.setText("…")
        QApplication.processEvents()

        try:
            ctx = ssl.create_default_context(cafile=certifi.where())
            req = urllib.request.Request(
                f"{url}/api/auto-record/upcoming",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "Summarizer"},
            )
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode())
            if isinstance(data, dict):
                for key in ("meetings", "data", "items", "results"):
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
            count = len(data) if isinstance(data, list) else 0
            self._agent_test_status.setText(t("agent_test_ok", count=count))
            self._agent_test_status.setStyleSheet(f"font-size: 11px; color: {C['success']};")
        except Exception as e:
            self._agent_test_status.setText(t("agent_test_fail", error=str(e)[:100]))
            self._agent_test_status.setStyleSheet(f"font-size: 11px; color: {C['error']};")
        finally:
            self._agent_test_btn.setEnabled(True)


# ── Main window ──────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    _auto_stop_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("app_title"))
        self.setMinimumSize(560, 620)
        self.setAcceptDrops(True)

        self._recorder: Optional[AudioRecorder] = None
        self._workers: list = []
        self._current_transcript: Optional[str] = None
        self._current_transcript_path: Optional[str] = None
        self._recording_start: Optional[float] = None

        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._update_rec_elapsed)

        # Real-time transcription
        self._rt_worker: Optional[RealtimeTranscribeWorker] = None
        self._rt_model_ready = False
        self._rt_sample_rate = 44100
        self._rt_committed_len = 0   # audio samples already transcribed and shown on screen
        self._rt_timer = QTimer(self)
        self._rt_timer.setInterval(10000)   # push audio every 10 seconds
        self._rt_timer.timeout.connect(self._on_rt_tick)

        self._prev_context_name = None
        self._profile_select_blocked = False
        self._saved_summary: Optional[str] = None
        self._summary_context_name: Optional[str] = None
        self._auto_stop_signal.connect(self._on_auto_stop)
        self._agent_poller: Optional[AgentPoller] = None
        self._agent_meeting: Optional[dict] = None
        self._agent_armed_ids: set = set()  # persists across poller restarts
        self._build_ui()
        self._preload_model()
        self._setup_tray()
        self._start_agent_if_enabled()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(theme.window_style())

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(20, 16, 20, 12)

        # ── top bar: title + settings ──
        top = QHBoxLayout()
        title = QLabel("Summarizer")
        title.setFont(QFont(".AppleSystemUIFont", 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C['primary']};")
        top.addWidget(title)
        top.addStretch()
        history_btn = QPushButton()
        history_btn.setIcon(_make_history_icon(32, QColor(C["text_secondary"])))
        history_btn.setIconSize(QSize(22, 22))
        history_btn.setFixedSize(36, 36)
        history_btn.setToolTip(t("history_tooltip"))
        history_btn.setStyleSheet(theme.ghost_btn())
        history_btn.clicked.connect(self._open_history)
        top.addWidget(history_btn)
        settings_btn = QPushButton()
        settings_btn.setIcon(_make_gear_icon(32, QColor(C["text_secondary"])))
        settings_btn.setIconSize(QSize(22, 22))
        settings_btn.setFixedSize(36, 36)
        settings_btn.setToolTip(t("settings_tooltip"))
        settings_btn.setStyleSheet(theme.ghost_btn())
        settings_btn.clicked.connect(self._open_settings)
        top.addWidget(settings_btn)
        root.addLayout(top)
        root.addSpacing(4)

        # ── context section ──
        _lbl_w = 90
        _combo_w = 220
        ctx_row = QHBoxLayout()
        named_lbl = QLabel(t("context_label"))
        named_lbl.setFixedWidth(_lbl_w)
        named_lbl.setStyleSheet(f"font-size: 12px; color: {C['text_secondary']};")
        ctx_row.addWidget(named_lbl)
        self.context_combo = theme.FlatComboBox()
        self.context_combo.setFixedWidth(_combo_w)
        self._refresh_contexts()
        ctx_row.addWidget(self.context_combo)
        add_ctx_btn = QPushButton("+")
        add_ctx_btn.setFixedSize(28, 28)
        add_ctx_btn.setToolTip(t("context_add_tooltip"))
        add_ctx_btn.setStyleSheet(theme.btn_secondary() + """
            QPushButton { font-size: 16px; font-weight: bold; padding: 0px; }
        """)
        add_ctx_btn.clicked.connect(self._add_context)
        ctx_row.addWidget(add_ctx_btn)

        # Context action buttons in a fixed-width container
        self._ctx_actions = QWidget()
        self._ctx_actions.setFixedWidth(100)
        act_lay = QHBoxLayout(self._ctx_actions)
        act_lay.setContentsMargins(0, 0, 0, 0)
        act_lay.setSpacing(2)

        self._edit_ctx_btn = QPushButton("✏")
        self._edit_ctx_btn.setFixedSize(28, 28)
        self._edit_ctx_btn.setToolTip(t("context_edit_tooltip"))
        self._edit_ctx_btn.setStyleSheet(theme.btn_secondary() + f"""
            QPushButton {{ font-size: 16px; padding: 0px; color: {C['warning']}; }}
        """)
        self._edit_ctx_btn.clicked.connect(self._edit_context)
        act_lay.addWidget(self._edit_ctx_btn)

        self._del_ctx_btn = QPushButton("×")
        self._del_ctx_btn.setFixedSize(28, 28)
        self._del_ctx_btn.setToolTip(t("context_delete_tooltip"))
        self._del_ctx_btn.setStyleSheet(theme.btn_secondary() + f"""
            QPushButton {{ font-size: 16px; font-weight: bold; padding: 0px; color: {C['error']}; }}
        """)
        self._del_ctx_btn.clicked.connect(self._delete_context)
        act_lay.addWidget(self._del_ctx_btn)

        self._chat_ctx_btn = QPushButton()
        self._chat_ctx_btn.setFixedSize(28, 28)
        self._chat_ctx_btn.setIcon(_make_chat_icon(32, QColor(C["primary"])))
        self._chat_ctx_btn.setIconSize(QSize(18, 18))
        self._chat_ctx_btn.setToolTip(t("context_chat_tooltip"))
        self._chat_ctx_btn.setStyleSheet(theme.ghost_btn())
        self._chat_ctx_btn.clicked.connect(self._open_context_chat)
        act_lay.addWidget(self._chat_ctx_btn)

        self._ctx_actions.setVisible(False)
        ctx_row.addWidget(self._ctx_actions)
        ctx_row.addStretch()
        self.context_combo.currentIndexChanged.connect(self._on_context_combo_changed)
        root.addLayout(ctx_row)

        # ── instructions profile row ──
        profile_row = QHBoxLayout()
        profile_row.setSpacing(6)
        profile_lbl = QLabel(t("instructions_label"))
        profile_lbl.setFixedWidth(_lbl_w)
        profile_lbl.setStyleSheet(f"font-size: 12px; color: {C['text_secondary']};")
        profile_row.addWidget(profile_lbl)
        self.profile_select = theme.FlatComboBox()
        self.profile_select.setFixedWidth(_combo_w)
        self._reload_main_profile_combo()
        self.profile_select.currentIndexChanged.connect(self._on_main_profile_changed)
        profile_row.addWidget(self.profile_select)
        profile_row.addStretch()
        root.addLayout(profile_row)
        root.addSpacing(12)

        # General context is hidden — editable via context editor dialog
        self._gen_lbl = QLabel()
        self._gen_lbl.setVisible(False)
        self.general_ctx = QTextEdit()
        self.general_ctx.setVisible(False)

        self._mtg_lbl = QLabel(t("meeting_context_label"))
        self._mtg_lbl.setStyleSheet(f"font-size: 11px; color: {C['text_secondary']}; margin: 0;")
        self._mtg_lbl.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._mtg_lbl)
        self.meeting_ctx = QTextEdit()
        self.meeting_ctx.setPlaceholderText(t("meeting_context_placeholder"))
        self.meeting_ctx.setMinimumHeight(68)
        self.meeting_ctx.setMaximumHeight(90)
        self.meeting_ctx.setAcceptRichText(False)
        self.meeting_ctx.setSizePolicy(self.meeting_ctx.sizePolicy().horizontalPolicy(),
                                        QSizePolicy.Policy.Preferred)
        root.addWidget(self.meeting_ctx)

        # ── record button ──
        root.addSpacing(6)
        self._mic_icon = _make_rec_dot_icon(48, QColor(C["danger"]))
        self._stop_icon = _make_stop_icon(48)
        self.record_btn = QPushButton(t("start_recording"))
        self.record_btn.setIcon(self._mic_icon)
        self.record_btn.setIconSize(QSize(22, 22))
        self.record_btn.setMinimumHeight(50)
        self.record_btn.setStyleSheet(theme.btn_primary())
        self.record_btn.clicked.connect(self._toggle_recording)
        root.addWidget(self.record_btn)

        # ── drop zone (clickable) ──
        self.drop_label = QPushButton(t("drop_hint"))
        self.drop_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.drop_label.setStyleSheet(f"""
            QPushButton {{
                color: {C['text_muted']};
                font-size: 12px;
                padding: 4px;
                border: none;
                background: transparent;
            }}
            QPushButton:hover {{
                color: {C['primary']};
            }}
        """)
        self.drop_label.clicked.connect(self._open_file)
        root.addWidget(self.drop_label)

        # ── status row ──
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"""
            background-color: transparent;
            color: {C['text_secondary']};
            font-size: 12px;
            padding: 4px 0px;
        """)
        status_row.addWidget(self.status_label, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(6)
        self.progress.setFixedWidth(120)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        status_row.addWidget(self.progress)
        root.addLayout(status_row)

        # ── result area ──
        self.result_text = QTextEdit()
        self.result_text.setPlaceholderText(t("summary_placeholder"))
        self.result_text.setMinimumHeight(120)
        self.result_text.setStyleSheet(f"""
            QTextEdit {{
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                background-color: {C['surface']};
                color: {C['text']};
                selection-background-color: {C['selection']};
            }}
        """)
        self.result_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.result_text, 1)

        # ── bottom buttons ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        self.copy_btn = QPushButton(t("copy_summary"))
        self.copy_btn.setIcon(_make_copy_icon(24, QColor(C["primary"])))
        self.copy_btn.setIconSize(QSize(16, 16))
        self.copy_btn.setStyleSheet(theme.btn_secondary())
        self.copy_btn.clicked.connect(self._copy_summary)
        self.copy_btn.setEnabled(False)
        bottom_row.addWidget(self.copy_btn)

        self.transcript_btn = QPushButton(t("open_transcript"))
        self.transcript_btn.setStyleSheet(theme.btn_secondary())
        self.transcript_btn.clicked.connect(self._open_transcript_file)
        self.transcript_btn.setEnabled(False)
        bottom_row.addWidget(self.transcript_btn)

        bottom_row.addStretch()

        self.update_ctx_btn = QPushButton(t("update_context"))
        self.update_ctx_btn.setStyleSheet(theme.btn_primary() + """
            QPushButton { padding: 6px 14px; font-size: 12px; border-radius: 6px; }
        """)
        self.update_ctx_btn.setMinimumHeight(30)
        self.update_ctx_btn.clicked.connect(self._update_context_entry)
        self.update_ctx_btn.setVisible(False)
        bottom_row.addWidget(self.update_ctx_btn)

        root.addLayout(bottom_row)
        root.setStretch(root.count() - 1, 0)

        self.result_text.textChanged.connect(self._on_result_text_changed)
        self._apply_mode_ui()

    # ── tray icon ────────────────────────────────────────────────────

    def _setup_tray(self):
        self._tray = TrayIcon(self)
        self._tray.show_action.triggered.connect(self._tray_show)
        self._tray.rec_action.triggered.connect(self._toggle_recording)
        self._tray.settings_action.triggered.connect(self._open_settings)
        self._tray.quit_action.triggered.connect(self._tray_quit)
        if config.load().get("menubar_enabled", False):
            self._tray.show()

    @staticmethod
    def _set_dock_visible(visible: bool):
        try:
            import AppKit
            policy = (AppKit.NSApplicationActivationPolicyRegular if visible
                      else AppKit.NSApplicationActivationPolicyAccessory)
            AppKit.NSApp.setActivationPolicy_(policy)
            if visible:
                # Re-apply dock icon (macOS resets it on policy change)
                icon_path = Path(__file__).parent / "icon.png"
                if icon_path.exists():
                    ns_image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(icon_path))
                    if ns_image:
                        AppKit.NSApp.setApplicationIconImage_(ns_image)
                AppKit.NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            pass

    def _tray_show(self):
        self._set_dock_visible(True)
        self.show()
        self.raise_()
        self.activateWindow()
        # Re-apply dock icon after a short delay (policy change needs to settle)
        QTimer.singleShot(100, self._reapply_dock_icon)

    def _reapply_dock_icon(self):
        try:
            import AppKit
            icon_path = Path(__file__).parent / "icon.png"
            if icon_path.exists():
                ns_image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(icon_path))
                if ns_image:
                    AppKit.NSApp.setApplicationIconImage_(ns_image)
        except Exception:
            pass

    def _tray_quit(self):
        self._stop_agent()
        self._tray.hide()
        QApplication.quit()

    def _refresh_tray(self):
        """Show/hide tray based on current config."""
        if config.load().get("menubar_enabled", False):
            self._tray.show()
        else:
            self._tray.hide()

    def closeEvent(self, event):
        if self._tray.isVisible():
            self.hide()
            self._set_dock_visible(False)
            event.ignore()
        else:
            self._stop_agent()
            self._tray.hide()
            event.accept()

    # ── agent integration ────────────────────────────────────────────

    def _start_agent_if_enabled(self):
        cfg = config.load()
        if cfg.get("agent_enabled") and cfg.get("agent_url") and cfg.get("agent_token"):
            if self._agent_poller is None:
                self._agent_poller = AgentPoller(self)
                self._agent_poller._armed_ids = self._agent_armed_ids  # share persistent set
                self._agent_poller.meeting_armed.connect(self._on_agent_meeting)
                self._agent_poller.error.connect(self._on_agent_error)
                self._agent_poller.start()
                _logger.info("Agent poller started")

    def _stop_agent(self):
        if self._agent_poller:
            self._agent_poller.stop()
            self._agent_poller.wait(3000)
            self._agent_poller = None
            _logger.info("Agent poller stopped")

    def _restart_agent(self):
        self._stop_agent()
        self._start_agent_if_enabled()

    def _on_agent_meeting(self, meeting: dict):
        """A meeting is ready to record — start recording immediately."""
        if self._recorder and self._recorder.is_recording():
            _logger.info("Already recording, skipping agent meeting %s", meeting.get("id"))
            return
        import copy
        self._agent_meeting = copy.deepcopy(meeting)
        title = self._agent_meeting.get("title", "Meeting")
        _logger.info("Agent: auto-recording '%s'", title)
        self._tray.showMessage("Summarizer", t("agent_notify_recording", title=title))
        self._toggle_recording()
        if self._recorder and self._recorder.is_recording():
            self._set_status(t("status_recording_agent", title=title), "recording")

    def _on_agent_error(self, msg: str):
        _logger.error("Agent error: %s", msg)

    def _agent_upload_transcript(self, transcript: str):
        """Upload transcript to backend after auto-record finishes."""
        if not self._agent_meeting:
            _logger.info("Agent upload skipped: no agent meeting active")
            return
        meeting = self._agent_meeting
        self._agent_meeting = None
        title = meeting.get("title", "Meeting")
        _logger.info("Agent uploading transcript for '%s' (%d chars)", title, len(transcript))
        worker = PostCompleteWorker(transcript, meeting, self)
        worker.finished.connect(lambda data: self._on_agent_upload_done(data, meeting))
        worker.error.connect(lambda e: self._on_agent_upload_error(e, meeting))
        self._track_worker(worker)
        worker.start()

    def _on_agent_upload_done(self, data: dict, meeting: dict):
        title = meeting.get("title", "Meeting")
        _logger.info("Agent upload done for '%s': %s", title, data)
        self._tray.showMessage("Summarizer", t("agent_notify_uploaded", title=title))

    def _on_agent_upload_error(self, error: str, meeting: dict):
        title = meeting.get("title", "Meeting")
        _logger.error("Agent upload failed for '%s': %s", title, error)
        self._tray.showMessage("Summarizer", t("agent_notify_error", error=error[:80]))

    def _is_transcribe_only(self) -> bool:
        return bool(config.load().get("transcribe_only", False))

    def _apply_mode_ui(self):
        """Update UI labels based on transcribe-only mode."""
        if self._is_transcribe_only():
            self.copy_btn.setText(t("copy_transcript"))
            self.result_text.setPlaceholderText(t("transcript_placeholder"))
        else:
            self.copy_btn.setText(t("copy_summary"))
            self.result_text.setPlaceholderText(t("summary_placeholder"))

    # ── context management ───────────────────────────────────────────

    def _on_context_combo_changed(self):
        if not hasattr(self, "_del_ctx_btn"):
            return
        # Save general context for previously selected context
        prev = getattr(self, "_prev_context_name", None)
        if prev:
            gen_text = self.general_ctx.toPlainText().strip()
            save_general_context(prev, gen_text)

        name = self.context_combo.currentData()
        has_selection = bool(name)
        self._ctx_actions.setVisible(has_selection)

        if has_selection:
            general = load_general_context(name)
            self.general_ctx.setPlainText(general)
            saved_profile = config.get_context_profile(name)
        else:
            self.general_ctx.clear()
            saved_profile = config.load().get("active_profile", config.DEFAULT_PROFILE_NAME)

        # Update profile dropdown without triggering save
        self._profile_select_blocked = True
        self.profile_select.blockSignals(True)
        idx = self.profile_select.findData(saved_profile)
        if idx >= 0:
            self.profile_select.setCurrentIndex(idx)
        self.profile_select.blockSignals(False)
        self._profile_select_blocked = False

        self._prev_context_name = name if has_selection else None

    def _reload_main_profile_combo(self):
        self._profile_select_blocked = True
        self.profile_select.blockSignals(True)
        self.profile_select.clear()
        for name in config.list_profiles():
            self.profile_select.addItem(name, name)
        # Select current active profile
        active = config.load().get("active_profile", config.DEFAULT_PROFILE_NAME)
        idx = self.profile_select.findData(active)
        if idx >= 0:
            self.profile_select.setCurrentIndex(idx)
        self.profile_select.blockSignals(False)
        self._profile_select_blocked = False

    def _on_main_profile_changed(self):
        if self._profile_select_blocked:
            return
        name = self.context_combo.currentData()
        profile = self.profile_select.currentData()
        if not profile:
            return
        if name:
            config.set_context_profile(name, profile)
        else:
            cfg = config.load()
            cfg["active_profile"] = profile
            cfg["instructions"] = config.get_profile(profile)
            config.save(cfg)

    def _refresh_contexts(self):
        self.context_combo.blockSignals(True)
        prev = self.context_combo.currentData()
        self.context_combo.clear()
        self.context_combo.addItem(t("context_none"), "")
        for name in list_contexts():
            self.context_combo.addItem(name, name)
        if prev:
            idx = self.context_combo.findData(prev)
            if idx >= 0:
                self.context_combo.setCurrentIndex(idx)
        self.context_combo.blockSignals(False)
        self._on_context_combo_changed()

    def _add_context(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(t("new_context_title"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(t("new_context_prompt")))
        name_edit = QLineEdit()
        lay.addWidget(name_edit)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton(t("btn_yes"))
        ok_btn.setStyleSheet(theme.btn_secondary())
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton(t("btn_no"))
        cancel_btn.setStyleSheet(theme.btn_secondary())
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)
        name_edit.returnPressed.connect(dlg.accept)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = name_edit.text().strip()
        if name:
            create_context(name.strip())
            self._prev_context_name = None
            self._refresh_contexts()
            idx = self.context_combo.findData(name.strip())
            if idx >= 0:
                self.context_combo.setCurrentIndex(idx)

    def _delete_context(self):
        name = self.context_combo.currentData()
        if not name:
            return
        if not _ask_yes_no(self, t("delete_context_title"), t("delete_context_confirm", name=name)):
            return
        self._prev_context_name = None
        rdir = config.get_recordings_dir()
        ctx_file = rdir / f"{name}_context.txt"
        if ctx_file.exists():
            ctx_file.unlink()
        self._refresh_contexts()

    def _edit_context(self):
        name = self.context_combo.currentData()
        if not name:
            return
        dlg = ContextEditorDialog(name, parent=self)
        dlg.exec()
        # Reload general context after editing
        from .summarizer import load_general_context
        self.general_ctx.setPlainText(load_general_context(name))

    def _open_context_chat(self):
        """Open a chat dialog with the current meeting series context from db."""
        from . import db
        name = self.context_combo.currentData()
        if not name:
            return

        # Build context from db
        parts = []
        general = db.load_general_context(name)
        if general:
            parts.append(f"Persistent context:\n{general}")

        # Recent meetings with meeting_context + summary
        meetings = db.list_meetings(context_name=name, limit=20)
        history = []
        for m in meetings:
            if m.get("summary"):
                lines = [f"[{m['started_at']}]"]
                mtg_ctx = m.get("meeting_context", "").strip()
                if mtg_ctx:
                    lines.append(f"Meeting context: {mtg_ctx}")
                lines.append(f"Summary: {m['summary']}")
                history.append("\n".join(lines))
        if history:
            parts.append(f"Recent meeting summaries:\n\n" + "\n\n".join(history))

        # Current meeting context from UI
        meeting = self.meeting_ctx.toPlainText().strip()
        if meeting:
            parts.append(f"Current meeting context:\n{meeting}")

        context_text = "\n\n".join(parts) if parts else "No context available."
        summary = self.result_text.toPlainText().strip()
        dlg = ContextChatDialog(context_text, summary_text=summary, context_name=name, parent=self)
        dlg.exec()

    def _get_context(self) -> tuple[Optional[str], str, str, str]:
        """Return (context_name, general_text, meeting_text, profile_name)."""
        name = self.context_combo.currentData() or None
        general = self.general_ctx.toPlainText().strip()
        meeting = self.meeting_ctx.toPlainText().strip()
        profile = self.profile_select.currentData() or config.DEFAULT_PROFILE_NAME
        return name, general, meeting, profile

    # ── model preloading ─────────────────────────────────────────────

    def _preload_model(self):
        """Start loading the Whisper model into cache in the background at startup."""
        cfg = config.load()
        wm = cfg.get("whisper_model", "base")
        if not config.is_model_downloaded(wm):
            downloaded = config.list_downloaded_models()
            if downloaded:
                wm = downloaded[0]
            else:
                return  # no model available yet
        _logger.info("Preloading Whisper model '%s' in background", wm)
        worker = _ModelPreloadWorker(wm)
        self._track_worker(worker)
        worker.start()

    # ── recording ────────────────────────────────────────────────────

    def _toggle_recording(self):
        if self._recorder and self._recorder.is_recording():
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        cfg = config.load()
        _logger.info("Starting recording (input_device=%s)", cfg.get("input_device"))
        self._recorder = AudioRecorder(
            silence_timeout=cfg.get("silence_timeout", 30),
            input_device=cfg.get("input_device"),
        )
        self._recorder.start(on_auto_stop=lambda: self._auto_stop_signal.emit())
        self._recording_start = time.monotonic()
        self._recording_wall_time = datetime.now()
        self.record_btn.setText(t("stop_recording", time="0:00"))
        self.record_btn.setIcon(self._stop_icon)
        self.record_btn.setStyleSheet(theme.btn_recording())
        self._rec_timer.start()
        self._set_status(t("status_recording"), "recording")
        self._tray.set_recording(True)

        # Start real-time transcription
        self._rt_model_ready = False
        self._rt_sample_rate = self._recorder.sample_rate
        self._rt_committed_len = 0
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText(t("live_transcript_placeholder"))
        self.result_text.clear()
        wm = cfg.get("whisper_model", "base")
        if not config.is_model_downloaded(wm):
            downloaded = config.list_downloaded_models()
            if downloaded:
                wm = downloaded[0]
        self._rt_worker = RealtimeTranscribeWorker(wm)
        self._rt_worker.model_ready.connect(self._on_rt_model_ready)
        self._rt_worker.chunk_ready.connect(self._on_rt_chunk)
        self._rt_worker.error.connect(lambda e: _logger.warning("RT worker error: %s", e))
        self._track_worker(self._rt_worker)
        self._rt_worker.start()

    def _cleanup_rt(self):
        """Tear down RT worker and timer. Disconnect signals to prevent late emissions."""
        self._rt_timer.stop()
        if self._rt_worker:
            try:
                self._rt_worker.chunk_ready.disconnect(self._on_rt_chunk)
            except (TypeError, RuntimeError):
                pass
            if self._rt_worker.isRunning():
                self._rt_worker.request_stop()
        self._rt_worker = None
        self._rt_model_ready = False
        self.result_text.setReadOnly(False)
        self._apply_mode_ui()

    def _finish_recording_with_rt(self, duration: Optional[int], status_prefix: str):
        """Stop recording; use existing RT text + transcribe only the delta."""
        existing_text = self.result_text.toPlainText().strip()
        all_audio = self._recorder.get_all_rt_audio()
        sample_rate = self._rt_sample_rate
        committed_len = self._rt_committed_len
        whisper_model = self._rt_worker._model_name if self._rt_worker else "base"

        # Kill RT worker immediately (don't wait for in-progress work)
        self._cleanup_rt()

        audio_file = self._recorder.stop()
        self._recorder = None
        self._reset_record_btn()

        if not audio_file:
            _logger.warning("Recording stopped but no audio captured")
            self._set_status(t("status_recording_failed"), "error")
            return

        _logger.info("Recording stopped, audio_path=%s, duration=%ss", audio_file, duration)

        # Save audio if configured
        cfg = config.load()
        if cfg.get("save_audio", False):
            rdir = config.get_recordings_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = rdir / f"recording_{ts}.wav"
            try:
                shutil.copy2(audio_file, dest)
            except Exception:
                pass

        self._pending_audio_path = audio_file
        self._pending_duration = duration

        # Delta = audio recorded since the last committed (transcribed) position
        delta = None
        if all_audio is not None and len(all_audio) > committed_len + sample_rate:
            delta = all_audio[committed_len:]

        if existing_text and delta is not None:
            # Transcribe only the small delta, then append
            _logger.info("RT: transcribing delta (%d samples, ~%.1fs)",
                         len(delta), len(delta) / sample_rate)
            self._set_status(f"{status_prefix}{t('status_finishing')}", "busy")
            self.progress.setVisible(True)
            self.record_btn.setEnabled(False)
            self._rt_existing_text = existing_text
            worker = _DeltaTranscribeWorker(delta, sample_rate, whisper_model)
            worker.finished.connect(self._on_delta_done)
            self._track_worker(worker)
            worker.start()
        elif existing_text:
            # No significant delta, use text as-is
            _logger.info("RT: no delta, using existing text (%d chars)", len(existing_text))
            self._use_rt_transcript(existing_text)
        else:
            # No RT text at all, fall back to full transcription
            _logger.info("RT: no existing text, falling back to full transcription")
            self._set_status(f"{status_prefix}{t('status_processing')}", "busy")
            self._process_audio(audio_file, duration_seconds=duration)

    def _on_delta_done(self, delta_text: str):
        """Delta transcription finished — append to existing text and proceed."""
        existing = getattr(self, "_rt_existing_text", "")
        if delta_text:
            transcript = existing + " " + delta_text
        else:
            transcript = existing
        self._rt_existing_text = None
        self._use_rt_transcript(transcript)

    def _use_rt_transcript(self, transcript: str):
        """Use the RT-produced transcript for summary (or display in transcribe-only mode)."""
        audio = getattr(self, "_pending_audio_path", None)
        duration = getattr(self, "_pending_duration", None)
        self._pending_audio_path = None
        self._pending_duration = None

        # Clean up temp audio file
        if audio and Path(audio).exists() and ("/tmp/" in audio or "/T/" in audio):
            try:
                os.unlink(audio)
            except OSError:
                pass

        if not transcript.strip():
            _logger.warning("RT transcript is empty")
            self._set_busy(False)
            self._on_error(t("error_no_speech"))
            return

        _logger.info("Using RT transcript (%d chars), transcribe_only=%s",
                     len(transcript), self._is_transcribe_only())
        self._current_transcript = transcript

        # Save transcript file
        rdir = config.get_recordings_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ctx_name, _, _, _ = self._get_context()
        base = ctx_name or "transcript"
        txt_path = rdir / f"{base}_{ts}.txt"
        try:
            txt_path.write_text(transcript, encoding="utf-8")
            self._current_transcript_path = str(txt_path)
        except Exception:
            pass

        self._persist_meeting_record(transcript, duration)

        # If this was an agent-triggered recording, upload transcript
        _logger.info("RT path: _agent_meeting=%s", "SET" if self._agent_meeting else "None")
        was_agent = self._agent_meeting is not None
        if self._agent_meeting:
            self._agent_meeting["_duration"] = duration or 0
            self._agent_upload_transcript(transcript)

        if self._is_transcribe_only() or was_agent:
            self._finish_with_transcript(transcript)
        else:
            self._set_busy(True)
            self.result_text.clear()
            self._run_summarize(transcript, duration_seconds=duration)

    def _stop_recording(self):
        if not self._recorder:
            return
        self._rec_timer.stop()
        self._rt_timer.stop()
        duration = int(time.monotonic() - self._recording_start) if self._recording_start else None
        self._finish_recording_with_rt(duration, "")

    def _on_auto_stop(self):
        """Called on main thread when silence auto-stop fires."""
        self._rec_timer.stop()
        self._rt_timer.stop()
        duration = int(time.monotonic() - self._recording_start) if self._recording_start else None
        if self._recorder:
            self._finish_recording_with_rt(duration, t("status_silence"))

    def _update_rec_elapsed(self):
        if self._recording_start is None:
            return
        elapsed = int(time.monotonic() - self._recording_start)
        mins, secs = divmod(elapsed, 60)
        self.record_btn.setText(t("stop_recording", time=f"{mins}:{secs:02d}"))

    def _reset_record_btn(self):
        self._recording_start = None
        self.record_btn.setText(t("start_recording"))
        self.record_btn.setIcon(self._mic_icon)
        self.record_btn.setStyleSheet(theme.btn_primary())
        self._tray.set_recording(False)

    # ── real-time transcription ───────────────────────────────────────

    def _on_rt_model_ready(self):
        """Whisper model loaded — start the 5-second chunk timer."""
        # Guard: only activate if we're still recording
        if not self._recorder or not self._recorder.is_recording():
            _logger.info("RT model ready but recording already stopped — skipping timer")
            return
        self._rt_model_ready = True
        self._rt_timer.start()
        _logger.info("RT transcription ready, timer started")

    def _on_rt_tick(self):
        """Timer fires every 10 s: push only the new audio delta since last commit."""
        if not self._recorder or not self._rt_worker or not self._rt_model_ready:
            return
        all_audio = self._recorder.get_all_rt_audio()
        if all_audio is None or len(all_audio) == 0:
            return
        delta = all_audio[self._rt_committed_len:]
        if len(delta) < self._rt_sample_rate * 3.0:
            return
        self._rt_worker.push_audio(delta, self._rt_sample_rate)

    def _on_rt_chunk(self, text: str, audio_len: int):
        """Append the new transcription chunk to the displayed text."""
        self._rt_committed_len += audio_len
        if not text:
            return
        current = self.result_text.toPlainText()
        separator = " " if current else ""
        self.result_text.blockSignals(True)
        self.result_text.setPlainText(current + separator + text)
        self.result_text.blockSignals(False)
        sb = self.result_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── file open ────────────────────────────────────────────────────

    def _open_file(self):
        """Open a file dialog for both audio and transcript files."""
        audio_exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXTENSIONS))
        text_exts = " ".join(f"*{e}" for e in sorted(TRANSCRIPT_EXTENSIONS))
        all_exts = f"{audio_exts} {text_exts}"
        path, _ = QFileDialog.getOpenFileName(
            self, t("open_audio_title"), "",
            f"All supported ({all_exts});;Audio ({audio_exts});;Text ({text_exts})",
        )
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            self._process_audio(path)
        elif ext in TRANSCRIPT_EXTENSIONS:
            self._process_transcript_file(path)

    def _open_audio(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, t("open_audio_title"), "", f"Audio ({exts})")
        if path:
            self._process_audio(path)

    def _open_transcript(self):
        exts = " ".join(f"*{e}" for e in sorted(TRANSCRIPT_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, t("open_transcript_title"), "", f"Text ({exts})")
        if path:
            self._process_transcript_file(path)

    # ── drag and drop ────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if not path:
                continue
            ext = Path(path).suffix.lower()
            if ext in AUDIO_EXTENSIONS:
                self._process_audio(path)
                return
            if ext in TRANSCRIPT_EXTENSIONS:
                self._process_transcript_file(path)
                return
        self._set_status(t("status_unsupported_file"), "error")

    # ── processing pipelines ─────────────────────────────────────────

    def _process_audio(self, audio_path: str, duration_seconds: Optional[int] = None):
        """Transcribe audio, then summarize (fallback path when RT is not available)."""
        cfg = config.load()
        self._set_busy(True)
        self.result_text.clear()
        self._pending_audio_path = audio_path

        if duration_seconds is None:
            try:
                import soundfile as sf
                info = sf.info(audio_path)
                duration_seconds = int(info.duration)
            except Exception:
                pass
        self._pending_duration = duration_seconds

        if cfg.get("save_audio", False):
            rdir = config.get_recordings_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = rdir / f"recording_{ts}.wav"
            try:
                shutil.copy2(audio_path, dest)
            except Exception:
                pass

        wm = cfg.get("whisper_model", "base")
        if not config.is_model_downloaded(wm):
            downloaded = config.list_downloaded_models()
            if downloaded:
                wm = downloaded[0]
        worker = TranscribeWorker(audio_path, wm)
        worker.status.connect(self._set_status_busy)
        worker.error.connect(self._on_error)
        worker.finished.connect(self._on_transcription_done)
        self._track_worker(worker)
        worker.start()

    def _on_transcription_done(self, transcript: str):
        self._current_transcript = transcript

        # Clean up temp audio file
        audio = getattr(self, "_pending_audio_path", None)
        if audio and Path(audio).exists() and ("/tmp/" in audio or "/T/" in audio):
            try:
                os.unlink(audio)
            except OSError:
                pass
        self._pending_audio_path = None

        if not transcript or not transcript.strip():
            _logger.warning("Transcription returned empty text")
            self._set_busy(False)
            self._on_error(t("error_no_speech"))
            self._pending_duration = None
            return

        # Save transcript file
        rdir = config.get_recordings_dir()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ctx_name, _, _, _ = self._get_context()
        base = ctx_name or "transcript"
        txt_path = rdir / f"{base}_{ts}.txt"
        try:
            txt_path.write_text(transcript, encoding="utf-8")
            self._current_transcript_path = str(txt_path)
        except Exception:
            pass

        self._persist_meeting_record(transcript, getattr(self, "_pending_duration", None))

        # If this was an agent-triggered recording, upload transcript
        _logger.info("Transcription done, _agent_meeting=%s", "SET" if self._agent_meeting else "None")
        was_agent = self._agent_meeting is not None
        if self._agent_meeting:
            self._agent_meeting["_duration"] = getattr(self, "_pending_duration", 0) or 0
            self._agent_upload_transcript(transcript)

        if self._is_transcribe_only() or was_agent:
            self._finish_with_transcript(transcript)
        else:
            self._run_summarize(transcript, duration_seconds=getattr(self, "_pending_duration", None))
        self._pending_duration = None

    def _process_transcript_file(self, file_path: str):
        """Read transcript and summarize."""
        try:
            text = Path(file_path).read_text(encoding="utf-8").strip()
        except Exception as e:
            self._on_error(t("error_read_file", error=e))
            return
        if not text:
            self._on_error(t("error_file_empty"))
            return

        # Copy to recordings
        rdir = config.get_recordings_dir()
        dest = rdir / Path(file_path).name
        if str(dest) != file_path:
            try:
                shutil.copy2(file_path, dest)
            except Exception:
                pass

        self._current_transcript = text
        self._current_transcript_path = file_path
        self._persist_meeting_record(text, None)
        if self._is_transcribe_only():
            self._finish_with_transcript(text)
        else:
            self._set_busy(True)
            self.result_text.clear()
            self._run_summarize(text)

    def _run_summarize(self, transcript: str, duration_seconds: Optional[int] = None):
        ctx_name, general, meeting, profile = self._get_context()
        if ctx_name and general:
            save_general_context(ctx_name, general)
        worker = SummarizeWorker(transcript, ctx_name, general, meeting,
                                 profile_name=profile, duration_seconds=duration_seconds)
        worker.status.connect(self._set_status_busy)
        worker.error.connect(self._on_error)
        worker.finished.connect(self._on_summary_done)
        self._track_worker(worker)
        worker.start()

    def _finish_with_transcript(self, transcript: str):
        """Transcribe-only mode: show transcript directly, skip summarization."""
        self._set_busy(False)
        self.result_text.setPlainText(transcript)
        self.copy_btn.setEnabled(True)
        self.transcript_btn.setEnabled(bool(self._current_transcript_path))
        self._set_status(t("status_done"), "done")
        if config.load().get("sound_on_done", True):
            self._play_done_sound()

    def _persist_meeting_record(self, transcript: str, duration_seconds: Optional[int]) -> None:
        """Insert a meeting row in the DB and remember its id in self._last_meeting_id.

        Runs as soon as transcription completes so the meeting shows up in the
        History dialog even if summarization is skipped (transcribe-only mode)
        or fails. The row is later updated with the summary in _on_summary_done.
        """
        self._last_meeting_id = None
        if not transcript or not transcript.strip():
            return
        try:
            from . import db
            ctx_name, _, meeting_ctx, profile = self._get_context()
            if ctx_name and not db.get_context_id(ctx_name):
                db.create_context(ctx_name)
            self._last_meeting_id = db.save_meeting(
                context_name=ctx_name,
                title=ctx_name or "Meeting",
                started_at=getattr(self, "_recording_wall_time", None),
                duration_seconds=duration_seconds or 0,
                meeting_context=(meeting_ctx or "").strip(),
                transcript=transcript,
                summary="",
                profile_name=profile or "",
            )
        except Exception as e:
            _logger.warning("Failed to insert meeting row: %s", e)

    def _on_summary_done(self, summary: str):
        self._set_busy(False)
        self._saved_summary = summary
        self._summary_context_name = self.context_combo.currentData() or None
        self.result_text.setPlainText(summary)
        self.copy_btn.setEnabled(True)
        self.transcript_btn.setEnabled(bool(self._current_transcript_path))
        self.update_ctx_btn.setVisible(False)
        self._set_status(t("status_done"), "done")
        self._refresh_contexts()
        # Update the meeting row created at transcription time with the summary.
        # Fallback: if the row never got inserted (e.g. earlier failure), insert now.
        try:
            from . import db
            if self._last_meeting_id:
                conn = db.get_connection()
                conn.execute("UPDATE meetings SET summary = ? WHERE id = ?",
                             (summary, self._last_meeting_id))
                conn.commit()
            else:
                self._last_meeting_id = db.save_meeting(
                    context_name=self._summary_context_name,
                    title=self._summary_context_name or "Meeting",
                    started_at=getattr(self, "_recording_wall_time", None),
                    duration_seconds=getattr(self, "_pending_duration", 0) or 0,
                    meeting_context=self.meeting_ctx.toPlainText().strip(),
                    transcript=self._current_transcript or "",
                    summary=summary,
                    profile_name=self.profile_select.currentData() or "",
                )
        except Exception as e:
            _logger.warning("Failed to save meeting summary to db: %s", e)
        if config.load().get("sound_on_done", True):
            self._play_done_sound()

    def _on_result_text_changed(self):
        if not self._saved_summary:
            return
        current = self.result_text.toPlainText()
        self.update_ctx_btn.setVisible(current != self._saved_summary)

    def _update_context_entry(self):
        new_text = self.result_text.toPlainText().strip()
        if not new_text:
            return
        try:
            name = self._summary_context_name
            if name:
                from .summarizer import update_latest_context_entry
                update_latest_context_entry(name, new_text)
            elif self._last_meeting_id:
                from . import db
                conn = db.get_connection()
                conn.execute("UPDATE meetings SET summary = ? WHERE id = ?",
                             (new_text, self._last_meeting_id))
                conn.commit()
            self._saved_summary = new_text
            self.update_ctx_btn.setVisible(False)
            self._set_status(t("status_context_updated"), "done")
        except Exception as e:
            _logger.error("Failed to update: %s", e)
            QMessageBox.warning(self, t("error_title"), str(e))

    @staticmethod
    def _play_done_sound():
        try:
            import subprocess
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _on_error(self, msg: str):
        _logger.error("Error: %s", msg)
        self._set_busy(False)
        self._set_status(f"Error: {msg}", "error")
        QMessageBox.critical(self, t("error_title"), msg)

    # ── helpers ──────────────────────────────────────────────────────

    def _set_status(self, msg: str, kind: str = "info"):
        colors = theme.status_colors()
        fg, bg = colors.get(kind, colors["info"])
        pad = "4px 10px" if bg != "transparent" else "4px 0px"
        radius = "10px" if bg != "transparent" else "0px"
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"""
            color: {fg};
            background-color: {bg};
            font-size: 12px;
            font-weight: {'600' if bg != 'transparent' else 'normal'};
            padding: {pad};
            border-radius: {radius};
        """)

    def _track_worker(self, worker: QThread):
        """Keep a reference to the worker so it doesn't get GC'd while running."""
        self._workers = [w for w in self._workers if w.isRunning()]
        self._workers.append(worker)

    def _set_status_busy(self, msg: str):
        self._set_status(msg, "busy")

    def _set_busy(self, busy: bool):
        self.progress.setVisible(busy)
        self.record_btn.setEnabled(not busy)
        if busy:
            self.copy_btn.setEnabled(False)
            self.transcript_btn.setEnabled(False)
            self.update_ctx_btn.setVisible(False)
            self._saved_summary = None
            self._summary_context_name = None
            self._tray.set_processing()
        else:
            self._tray.set_idle()

    @staticmethod
    def _mrkdwn_to_html(text: str) -> str:
        """Convert Slack mrkdwn bold/italic to HTML for clipboard."""
        import re
        body = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = re.sub(r"(?<!\w)\*([^\n*]+?)\*(?!\w)", r"<b>\1</b>", body)
        body = re.sub(r"(?<!\w)_([^\n_]+?)_(?!\w)", r"<i>\1</i>", body)
        body = body.replace("\n", "<br>")
        return (
            '<html><head><meta charset="utf-8"></head>'
            f"<body>{body}</body></html>"
        )

    def _copy_summary(self):
        text = self.result_text.toPlainText()
        if text:
            mime = QMimeData()
            mime.setText(text)
            mime.setHtml(self._mrkdwn_to_html(text))
            QApplication.clipboard().setMimeData(mime)
            self._set_status(t("status_copied"), "done")

    def _open_transcript_file(self):
        if self._current_transcript_path and Path(self._current_transcript_path).exists():
            import subprocess
            subprocess.Popen(["open", self._current_transcript_path])
        else:
            self._set_status(t("status_no_transcript"), "error")

    def _open_history(self):
        dlg = HistoryDialog(self)
        dlg.exec()

    def _open_settings(self):
        if not hasattr(self, "_bg_whisper_downloads"):
            self._bg_whisper_downloads: dict = {}
        if not hasattr(self, "_bg_llm_downloads"):
            self._bg_llm_downloads: dict = {}
        dlg = SettingsDialog(
            self,
            bg_whisper=self._bg_whisper_downloads,
            bg_llm=self._bg_llm_downloads,
        )
        dlg.exec()
        self._apply_mode_ui()
        self._reload_main_profile_combo()
        # Re-apply context profile selection if a context is active
        name = self.context_combo.currentData()
        if name:
            saved_profile = config.get_context_profile(name)
            self._profile_select_blocked = True
            self.profile_select.blockSignals(True)
            idx = self.profile_select.findData(saved_profile)
            if idx >= 0:
                self.profile_select.setCurrentIndex(idx)
            self.profile_select.blockSignals(False)
            self._profile_select_blocked = False
        self._refresh_tray()
        self._restart_agent()


# ── entry point ──────────────────────────────────────────────────────────

def main():
    config.setup_logging()
    import logging
    _logger = logging.getLogger("app")
    _logger.info("Summarizer starting")

    # Migrate file-based contexts to SQLite
    from . import db
    db.migrate_from_files()

    # Apply theme before creating any widgets
    cfg = config.load()
    theme.apply(cfg.get("theme", "light"))

    class _App(QApplication):
        """Custom QApplication that shows the window on macOS reopen (Dock click)."""
        _main_window = None

        def event(self, event):
            if event.type() == event.Type.ApplicationActivate and self._main_window:
                self._main_window._tray_show()
            return super().event(event)

    app = _App(sys.argv)
    app.setApplicationName("Summarizer")

    # Single-instance guard with QLocalServer
    _server_name = "com.summarizer.single-instance"

    # Try to connect to existing instance
    socket = QLocalSocket()
    socket.connectToServer(_server_name)
    if socket.waitForConnected(500):
        # Another instance is running — ask it to show
        socket.write(b"show")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        _logger.info("Sent show signal to running instance, exiting.")
        sys.exit(0)

    # No existing instance — start server
    # Remove stale socket file (e.g. after crash)
    QLocalServer.removeServer(_server_name)
    _local_server = QLocalServer()
    _local_server.listen(_server_name)

    app.setStyle("Fusion")
    theme.apply_palette(app)

    icon_path = Path(__file__).parent / "icon.png"
    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
    else:
        app_icon = QIcon(_make_app_icon(512))
    app.setWindowIcon(app_icon)

    window = MainWindow()
    window.show()
    app._main_window = window

    # Handle "show" signals from new instances
    def _on_new_connection():
        conn = _local_server.nextPendingConnection()
        if conn:
            conn.waitForReadyRead(1000)
            conn.close()
            _logger.info("Received show signal from new instance")
            window._tray_show()
            # Ensure window comes to front after policy switch
            QTimer.singleShot(200, lambda: (window.raise_(), window.activateWindow()))

    _local_server.newConnection.connect(_on_new_connection)

    # Show quick setup on first run (no API key configured yet)
    cfg = config.load()
    is_first_run = not cfg.get("api_key", "").strip() and not cfg.get("setup_done")
    if is_first_run:
        dlg = SetupWizard(window)
        dlg.exec()
        # Mark setup as seen so we don't show again even if key is skipped
        cfg2 = config.load()
        cfg2["setup_done"] = True
        config.save(cfg2)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
