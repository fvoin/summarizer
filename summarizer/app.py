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
from PyQt6.QtGui import (
    QDragEnterEvent, QDropEvent, QFont, QIcon, QPainter, QPixmap, QColor, QPen,
    QPainterPath,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QLineEdit,
    QFileDialog, QMessageBox, QDialog, QFormLayout, QSpinBox,
    QGroupBox, QSplitter, QProgressBar, QSizePolicy,
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

_logger = logging.getLogger("app")

# ── Color palette & shared styles ────────────────────────────────────────

_C = {
    "primary":       "#4A90D9",
    "primary_hover": "#3A7BC8",
    "primary_text":  "#ffffff",
    "accent":        "#7B68EE",
    "danger":        "#D94A4A",
    "danger_hover":  "#C43A3A",
    "bg":            "#ECECEC",
    "surface":       "#ffffff",
    "border":        "#D1D1D6",
    "text":          "#1D1D1F",
    "text_secondary":"#6E6E73",
    "text_muted":    "#AEAEB2",
    "success":       "#2D8A4E",
    "warning":       "#B08800",
}

_BTN_PRIMARY = f"""
    QPushButton {{
        background-color: {_C['primary']};
        color: {_C['primary_text']};
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        font-size: 15px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {_C['primary_hover']};
    }}
    QPushButton:pressed {{
        background-color: #2E6BB5;
    }}
    QPushButton:disabled {{
        background-color: {_C['border']};
        color: {_C['text_muted']};
    }}
"""

_BTN_RECORDING = f"""
    QPushButton {{
        background-color: {_C['danger']};
        color: {_C['primary_text']};
        border: none;
        border-radius: 8px;
        padding: 10px 20px;
        font-size: 15px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {_C['danger_hover']};
    }}
"""

_BTN_SECONDARY = f"""
    QPushButton {{
        background-color: transparent;
        color: {_C['primary']};
        border: none;
        border-radius: 6px;
        padding: 7px 14px;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: rgba(74, 144, 217, 0.1);
    }}
    QPushButton:pressed {{
        background-color: rgba(74, 144, 217, 0.18);
    }}
    QPushButton:disabled {{
        color: {_C['text_muted']};
    }}
"""

_WINDOW_STYLE = f"""
    QProgressBar {{
        background-color: #D5D5DA;
        border: none;
        border-radius: 4px;
        height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: {_C['primary']};
        border-radius: 4px;
    }}
"""


# ── Vector icon helpers ──────────────────────────────────────────────────

def _make_mic_icon(size: int = 64, color: QColor = QColor("#4A90D9")) -> QIcon:
    """Draw a simple microphone icon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, size * 0.06, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(color)

    cx, cy = size / 2, size * 0.35
    rw, rh = size * 0.18, size * 0.28
    p.drawRoundedRect(int(cx - rw), int(cy - rh), int(rw * 2), int(rh * 2), rw, rw)

    p.setBrush(Qt.BrushStyle.NoBrush)
    arc_w, arc_h = size * 0.3, size * 0.3
    p.drawArc(int(cx - arc_w), int(cy - arc_h * 0.3), int(arc_w * 2), int(arc_h * 2), 0, -180 * 16)

    p.drawLine(int(cx), int(cy + rh + arc_h * 0.7), int(cx), int(size * 0.85))
    p.drawLine(int(cx - size * 0.15), int(size * 0.85), int(cx + size * 0.15), int(size * 0.85))
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
            self.status.emit("Transcribing audio…")
            _logger.info("TranscribeWorker: model=%s, audio=%s", self.whisper_model, self.audio_path)
            t = Transcriber(self.whisper_model)
            text = t.transcribe(self.audio_path)
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
                if text:
                    self.chunk_ready.emit(text, len(audio_data))
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
            self.status.emit("Generating summary…")
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

        self.dl_btn = QPushButton("Download")
        self.dl_btn.setFixedWidth(80)
        self.dl_btn.clicked.connect(lambda: self.download_requested.emit(self.model_name))
        lay.addWidget(self.dl_btn)

        self.del_btn = QPushButton("Delete")
        self.del_btn.setFixedWidth(56)
        self.del_btn.setStyleSheet("color: #cc3333;")
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
            self.status_label.setText("Ready")
            self.status_label.setStyleSheet("color: #2d8a4e; font-weight: bold;")
            self.dl_btn.setVisible(False)
            self.del_btn.setVisible(True)
            self.progress_bar.setVisible(False)
        else:
            self.status_label.setText("Not downloaded")
            self.status_label.setStyleSheet("color: #888;")
            self.dl_btn.setVisible(True)
            self.del_btn.setVisible(False)

    def set_downloading(self):
        self.dl_btn.setVisible(False)
        self.del_btn.setVisible(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Downloading…")
        self.status_label.setStyleSheet("color: #b08800;")

    def set_download_done(self):
        self.progress_bar.setVisible(False)
        self._set_downloaded(True)

    def set_download_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.dl_btn.setVisible(True)
        self.del_btn.setVisible(False)
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: #cc3333;")
        self.status_label.setToolTip(msg)


class QuickSetupDialog(QDialog):
    """First-run setup wizard: prompt for a Gemini API key."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Summarizer")
        self.setFixedWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(28, 28, 28, 24)

        # Icon + title row
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            icon_lbl = QLabel()
            pm = QPixmap(str(icon_path)).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(pm)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(icon_lbl)

        title = QLabel("Welcome to Summarizer")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {_C['primary']};")
        root.addWidget(title)

        sub = QLabel("Let's set up your AI model to get started.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"font-size: 13px; color: {_C['text_secondary']};")
        root.addWidget(sub)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #D1D1D6;")
        root.addWidget(sep)

        # Gemini key section
        gemini_lbl = QLabel("Gemini API Key  <span style='color:#6e6e73; font-weight:400;'>(recommended — free)</span>")
        gemini_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        root.addWidget(gemini_lbl)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("Paste your Gemini API key here…")
        self._key_input.setMinimumHeight(36)
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        root.addWidget(self._key_input)

        hint = QLabel(
            'Get a free key at <a href="https://aistudio.google.com/apikey" '
            f'style="color:{_C["primary"]};">aistudio.google.com/apikey</a>'
        )
        hint.setOpenExternalLinks(True)
        hint.setStyleSheet("font-size: 11px;")
        root.addWidget(hint)

        # Offline note
        offline_box = QWidget()
        offline_box.setStyleSheet(
            f"background: rgba(74,144,217,0.07); border-radius: 6px;"
        )
        ob_lay = QHBoxLayout(offline_box)
        ob_lay.setContentsMargins(12, 8, 12, 8)
        ob_lbl = QLabel(
            "No API key? You can also use <b>local models</b> (fully offline) — "
            "download them later in Settings → Models."
        )
        ob_lbl.setWordWrap(True)
        ob_lbl.setStyleSheet("font-size: 11px; background: transparent;")
        ob_lay.addWidget(ob_lbl)
        root.addWidget(offline_box)

        root.addSpacing(4)

        # Buttons
        btn_row = QHBoxLayout()
        skip_btn = QPushButton("Skip for now")
        skip_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {_C['text_secondary']};"
            " font-size: 13px; padding: 8px 16px; }}"
            f" QPushButton:hover {{ color: {_C['text']}; }}"
        )
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)
        btn_row.addStretch()

        self._save_btn = QPushButton("Save && Start")
        self._save_btn.setMinimumHeight(36)
        self._save_btn.setMinimumWidth(120)
        self._save_btn.setStyleSheet(_BTN_PRIMARY)
        self._save_btn.clicked.connect(self._save)
        btn_row.addWidget(self._save_btn)
        root.addLayout(btn_row)

        self._key_input.textChanged.connect(self._on_key_changed)
        self._on_key_changed()

    def _on_key_changed(self):
        self._save_btn.setEnabled(bool(self._key_input.text().strip()))

    def _save(self):
        key = self._key_input.text().strip()
        if not key:
            return
        cfg = config.load()
        cfg["api_key"] = key
        # Ensure Gemini Flash is the default model if none set
        if not cfg.get("model"):
            cfg["model"] = "gemini-3-flash-preview"
        config.save(cfg)
        self.accept()


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
        self.setWindowTitle(f"Test — {display_name}")
        self.resize(480, 420)
        self._model = model_key
        self._messages: list[dict] = []
        self._worker: Optional[_OllamaChatWorker] = None

        vlay = QVBoxLayout(self)

        self._chat_view = QTextEdit()
        self._chat_view.setReadOnly(True)
        self._chat_view.setPlaceholderText("Send a message to start chatting…")
        vlay.addWidget(self._chat_view, 1)

        hlay = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a message…")
        self._input.returnPressed.connect(self._send)
        hlay.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setFixedWidth(60)
        self._send_btn.setStyleSheet(
            f"background: {_C['primary']}; color: white; border: none; border-radius: 4px; padding: 4px 8px;"
        )
        self._send_btn.clicked.connect(self._send)
        hlay.addWidget(self._send_btn)
        vlay.addLayout(hlay)

    def _send(self):
        text = self._input.text().strip()
        if not text or self._worker is not None:
            return
        self._input.clear()
        self._messages.append({"role": "user", "content": text})
        self._chat_view.append(f"<p style='color:{_C['primary']};'><b>You:</b> {text}</p>")
        self._chat_view.append(f"<p style='color:#555;'><b>{self._model}:</b> ")
        self._set_busy(True)

        self._worker = _OllamaChatWorker(self._model, list(self._messages))
        self._assistant_buf = ""
        self._worker.reply_chunk.connect(self._on_chunk)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_chunk(self, text: str):
        self._assistant_buf += text
        cursor = self._chat_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self._chat_view.setTextCursor(cursor)
        self._chat_view.ensureCursorVisible()

    def _on_error(self, msg: str):
        self._chat_view.append(f"<p style='color:#cc3333;'>Error: {msg}</p>")

    def _on_done(self):
        if self._assistant_buf:
            self._messages.append({"role": "assistant", "content": self._assistant_buf})
        self._chat_view.append("</p>")
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._send_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        if not busy:
            self._input.setFocus()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        super().closeEvent(event)


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

        _flat_btn = (
            "QPushButton { background: transparent; border: none; border-radius: 4px;"
            " padding: 2px 6px; font-size: 12px; font-weight: 500; color: %s; }"
            " QPushButton:hover { background: rgba(0,0,0,0.06); }"
            " QPushButton:pressed { background: rgba(0,0,0,0.12); }"
        )

        self.test_btn = QPushButton("Test")
        self.test_btn.setFixedWidth(44)
        self.test_btn.setStyleSheet(_flat_btn % _C["primary"])
        self.test_btn.clicked.connect(lambda: self.test_requested.emit(self.model_key))
        self.test_btn.setVisible(False)
        lay.addWidget(self.test_btn)

        self.dl_btn = QPushButton("Download")
        self.dl_btn.setFixedWidth(76)
        self.dl_btn.setStyleSheet(_flat_btn % _C["primary"])
        self.dl_btn.clicked.connect(lambda: self.download_requested.emit(self.model_key))
        lay.addWidget(self.dl_btn)

        self.del_btn = QPushButton("Delete")
        self.del_btn.setFixedWidth(56)
        self.del_btn.setStyleSheet(_flat_btn % "#cc3333")
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
            self.status_label.setText("Ready")
            self.status_label.setStyleSheet("color: #2d8a4e; font-weight: bold;")
            self.dl_btn.setVisible(False)
            self.del_btn.setVisible(True)
            self.test_btn.setVisible(True)
            self.progress_bar.setVisible(False)
        else:
            self.status_label.setText("Not downloaded")
            self.status_label.setStyleSheet("color: #888;")
            self.dl_btn.setVisible(True)
            self.del_btn.setVisible(False)
            self.test_btn.setVisible(False)

    def set_pulling(self):
        self.dl_btn.setVisible(False)
        self.del_btn.setVisible(False)
        self.test_btn.setVisible(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Downloading…")
        self.status_label.setStyleSheet("color: #b08800;")

    def set_pull_done(self):
        self.progress_bar.setVisible(False)
        self._set_downloaded(True)

    def set_pull_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.dl_btn.setVisible(True)
        self.del_btn.setVisible(False)
        self.test_btn.setVisible(False)
        self.status_label.setText("Error")
        self.status_label.setStyleSheet("color: #cc3333;")
        self.status_label.setToolTip(msg)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, bg_whisper: dict = None, bg_llm: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(580)
        self.setMinimumHeight(720)
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
                        r.status_label.setStyleSheet("color: #b08800;"),
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
        models_inner = QWidget()
        models_vlay = QVBoxLayout(models_inner)
        models_vlay.setContentsMargins(8, 8, 8, 8)
        models_vlay.setSpacing(10)

        # AI Model group
        llm_group = QGroupBox("AI Model")
        llm_vlay = QVBoxLayout(llm_group)
        llm_vlay.setSpacing(2)

        self._all_model_radio_group = QButtonGroup(self)
        current_model = self.cfg.get("model", "")

        cloud_lbl = QLabel("☁  Cloud")
        cloud_lbl.setStyleSheet("color: #6e6e73; font-size: 11px; font-weight: bold; margin-top: 4px;")
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
        self._custom_rb = QRadioButton("Custom:")
        self._all_model_radio_group.addButton(self._custom_rb)
        custom_row_h.addWidget(self._custom_rb)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("model name…")
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
        creds_h.addWidget(QLabel("API Key:"))
        self.key_edit = QLineEdit(self.cfg.get("api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("your API key")
        creds_h.addWidget(self.key_edit, 2)
        creds_h.addWidget(QLabel("Base URL:"))
        self.base_url_edit = QLineEdit(self.cfg.get("base_url", ""))
        self.base_url_edit.setPlaceholderText("(optional)")
        creds_h.addWidget(self.base_url_edit, 2)
        llm_vlay.addWidget(creds_w)

        # Local (Ollama) sub-section
        local_lbl = QLabel("⚡  Local (Ollama)")
        local_lbl.setStyleSheet("color: #6e6e73; font-size: 11px; font-weight: bold; margin-top: 6px;")
        llm_vlay.addWidget(local_lbl)

        ollama_ok = config.is_ollama_available()
        if not ollama_ok:
            hint = QLabel("Ollama not found — click Download to auto-install, or visit <a href='https://ollama.com'>ollama.com</a>")
            hint.setOpenExternalLinks(True)
            hint.setStyleSheet("color: #888; font-size: 10px; margin-left: 12px;")
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
        whisper_group = QGroupBox("Whisper Model (speech recognition)")
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
        tabs.addTab(models_scroll, "Models")

        # ── TAB: Instructions ─────────────────────────────────────────────
        instr_tab = QWidget()
        instr_outer = QVBoxLayout(instr_tab)
        instr_outer.setContentsMargins(8, 8, 8, 8)
        instr_outer.setSpacing(6)

        profile_row = QHBoxLayout()
        profile_row.setSpacing(6)
        self.profile_combo = QComboBox()
        self._reload_profile_combo()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        profile_row.addWidget(self.profile_combo, 1)

        new_profile_btn = QPushButton("New")
        new_profile_btn.setFixedWidth(50)
        new_profile_btn.clicked.connect(self._new_profile)
        profile_row.addWidget(new_profile_btn)

        self.del_profile_btn = QPushButton("Delete")
        self.del_profile_btn.setFixedWidth(56)
        self.del_profile_btn.clicked.connect(self._delete_profile)
        profile_row.addWidget(self.del_profile_btn)
        instr_outer.addLayout(profile_row)

        active_profile = self.cfg.get("active_profile", config.DEFAULT_PROFILE_NAME)
        self.instructions_edit = QTextEdit()
        self.instructions_edit.setPlainText(config.get_profile(active_profile))
        self.instructions_edit.setPlaceholderText("System instructions for the LLM agent…")
        instr_outer.addWidget(self.instructions_edit, 1)

        tabs.addTab(instr_tab, "Instructions")

        # ── TAB: General ──────────────────────────────────────────────────
        general_tab = QWidget()
        general_form = QFormLayout(general_tab)
        general_form.setContentsMargins(12, 12, 12, 12)
        general_form.setSpacing(8)

        self.context_limit_spin = QSpinBox()
        self.context_limit_spin.setRange(500, 50000)
        self.context_limit_spin.setSingleStep(500)
        self.context_limit_spin.setValue(int(self.cfg.get("context_limit", 5000)))
        self.context_limit_spin.setSuffix(" chars")
        general_form.addRow("Context Limit:", self.context_limit_spin)

        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(5, 300)
        self.silence_spin.setValue(int(self.cfg.get("silence_timeout", 30)))
        self.silence_spin.setSuffix(" sec")
        general_form.addRow("Silence Timeout:", self.silence_spin)

        self.device_combo = QComboBox()
        self.device_combo.addItem("Default", None)
        for dev in AudioRecorder.list_devices():
            self.device_combo.addItem(dev["name"], dev["id"])
        saved_dev = self.cfg.get("input_device")
        if saved_dev is not None:
            for i in range(self.device_combo.count()):
                if self.device_combo.itemData(i) == saved_dev:
                    self.device_combo.setCurrentIndex(i)
                    break
        general_form.addRow("Input Device:", self.device_combo)

        self.save_audio_check = QCheckBox("Save recorded audio files to recordings dir")
        self.save_audio_check.setChecked(bool(self.cfg.get("save_audio", False)))
        general_form.addRow("Save Audio:", self.save_audio_check)

        self.transcribe_only_check = QCheckBox("Transcribe only (no summarization)")
        self.transcribe_only_check.setChecked(bool(self.cfg.get("transcribe_only", False)))
        general_form.addRow("Mode:", self.transcribe_only_check)

        self.sound_on_done_check = QCheckBox("Play sound when done")
        self.sound_on_done_check.setChecked(bool(self.cfg.get("sound_on_done", True)))
        general_form.addRow("Sound:", self.sound_on_done_check)

        self.recordings_edit = QLineEdit(self.cfg.get("recordings_dir", ""))
        self.recordings_edit.setPlaceholderText("(default: ~/.summarizer/recordings)")
        general_form.addRow("Recordings Dir:", self.recordings_edit)

        logs_btn = QPushButton("Open Log File")
        logs_btn.setToolTip(str(config.get_log_path()))
        logs_btn.clicked.connect(self._open_logs)
        general_form.addRow("Diagnostics:", logs_btn)

        update_row = QHBoxLayout()
        version_label = QLabel(f"v{config.APP_VERSION}")
        version_label.setStyleSheet("color: #888; font-size: 12px;")
        update_row.addWidget(version_label)
        self._update_btn = QPushButton("Check for Updates")
        self._update_btn.clicked.connect(self._check_for_updates)
        update_row.addWidget(self._update_btn)
        self._update_progress = QProgressBar()
        self._update_progress.setMaximumHeight(18)
        self._update_progress.setVisible(False)
        update_row.addWidget(self._update_progress)
        update_row.addStretch()
        general_form.addRow("Version:", update_row)

        tabs.addTab(general_tab, "General")

        # ── Save / Cancel row ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        outer.addLayout(btn_row)

    def _open_logs(self):
        log_path = config.get_log_path()
        if not log_path.exists():
            QMessageBox.information(self, "Logs", "No log file yet — run the app first.")
            return
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))

    def _check_for_updates(self):
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Checking…")
        worker = UpdateCheckWorker()
        worker.update_available.connect(self._on_update_available)
        worker.no_update.connect(self._on_no_update)
        worker.error.connect(self._on_update_error)
        self._update_worker = worker
        worker.start()

    def _on_update_available(self, info: dict):
        self._update_btn.setText("Check for Updates")
        self._update_btn.setEnabled(True)
        tag = info["tag"]
        notes = info.get("notes", "")
        preview = notes[:300] + "…" if len(notes) > 300 else notes
        msg = f"A new version {tag} is available.\n\n{preview}\n\nDownload now?"
        reply = QMessageBox.question(self, "Update Available", msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._start_download(info["dmg_url"])

    def _on_no_update(self):
        self._update_btn.setText("Check for Updates")
        self._update_btn.setEnabled(True)
        QMessageBox.information(self, "Up to Date",
                                f"You are running the latest version (v{config.APP_VERSION}).")

    def _on_update_error(self, msg: str):
        self._update_btn.setText("Check for Updates")
        self._update_btn.setEnabled(True)
        QMessageBox.warning(self, "Update Check Failed", msg)

    def _start_download(self, dmg_url: str):
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Downloading…")
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
        self._update_btn.setText("Check for Updates")
        self._update_btn.setEnabled(True)

        from pathlib import Path
        dmg_path = Path.home() / "Downloads" / "Summarizer.dmg"

        dlg = QDialog(self)
        dlg.setWindowTitle("Update Ready")
        dlg.setFixedWidth(400)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)
        lay.setContentsMargins(24, 20, 24, 20)

        title_lbl = QLabel("New version downloaded!")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 700;")
        lay.addWidget(title_lbl)

        info_lbl = QLabel(
            "To install:\n"
            "1. Click \"Quit & Open DMG\" below\n"
            "2. Drag Summarizer to Applications\n"
            "3. Launch Summarizer from Applications"
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("font-size: 13px;")
        lay.addWidget(info_lbl)

        lay.addSpacing(4)

        btn_row = QHBoxLayout()
        later_btn = QPushButton("Later")
        later_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" color: {_C['text_secondary']}; font-size: 13px; padding: 8px 14px; }}"
            f" QPushButton:hover {{ color: {_C['text']}; }}"
        )
        later_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(later_btn)
        btn_row.addStretch()

        quit_btn = QPushButton("Quit & Open DMG")
        quit_btn.setMinimumHeight(34)
        quit_btn.setStyleSheet(_BTN_PRIMARY)
        quit_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(quit_btn)
        lay.addLayout(btn_row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            import subprocess
            subprocess.Popen(["open", str(dmg_path)])
            QApplication.quit()

    def _on_update_download_error(self, msg: str):
        self._update_progress.setVisible(False)
        self._update_btn.setText("Check for Updates")
        self._update_btn.setEnabled(True)
        QMessageBox.warning(self, "Download Failed", msg)

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
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
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
        answer = QMessageBox.question(
            self, "Delete Profile",
            f"Delete profile «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
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
                self, "Bundled Model",
                f"'{model_name}' is bundled with the app and cannot be deleted.",
            )
            return
        answer = QMessageBox.question(
            self, "Delete Whisper Model",
            f"Delete '{model_name}' model files from disk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            config.delete_whisper_model(model_name)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
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
        msg.setWindowTitle("Ollama Required")
        msg.setText(
            "Ollama is required for local models.\n\n"
            "Auto-install (will install Homebrew too if needed)\n"
            "or download manually from ollama.com."
        )
        brew_btn = msg.addButton("Auto Install", QMessageBox.ButtonRole.AcceptRole)
        web_btn = msg.addButton("Open Download Page", QMessageBox.ButtonRole.HelpRole)
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
            self._set_ollama_install_hint("Installing Ollama…")
            self._install_ollama_worker.start()
        elif msg.clickedButton() == web_btn:
            QDesktopServices.openUrl(QUrl("https://ollama.com/download"))

    def _set_ollama_install_hint(self, text: str):
        for row in self._local_llm_rows.values():
            row.status_label.setText(text)
            row.status_label.setStyleSheet("color: #b08800;")

    def _on_ollama_installed(self):
        for row in self._local_llm_rows.values():
            row.status_label.setText("Ollama ready")
            row.status_label.setStyleSheet("color: #2d8a4e; font-weight: bold;")
        pending = getattr(self, "_pending_pull_model", None)
        if pending:
            self._do_pull_local_llm(pending)
            self._pending_pull_model = None

    def _on_ollama_install_error(self, msg: str):
        for row in self._local_llm_rows.values():
            row.status_label.setText("Not downloaded")
            row.status_label.setStyleSheet("color: #888;")
        QMessageBox.critical(self, "Ollama Install Failed", msg)

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
                r.status_label.setStyleSheet("color: #b08800;"),
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
        QMessageBox.critical(self, "Local Model Error", msg)

    def _delete_local_llm(self, model_key: str):
        info = config.LOCAL_LLM_MODELS.get(model_key, {})
        name = info.get("display", model_key)
        answer = QMessageBox.question(
            self, "Delete Local Model",
            f"Delete '{name}' from Ollama?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
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
            answer = QMessageBox.question(
                self, "Model Not Downloaded",
                f"'{selected_wm}' is not downloaded yet.\n"
                "It will be downloaded automatically on first transcription.\n\n"
                "Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
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
        config.save(self.cfg)
        self.accept()


# ── Main window ──────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    _auto_stop_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Summarizer")
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
        self._build_ui()
        self._preload_model()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(_WINDOW_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(20, 16, 20, 12)

        # ── top bar: title + settings ──
        top = QHBoxLayout()
        title = QLabel("Summarizer")
        title.setFont(QFont(".AppleSystemUIFont", 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_C['primary']};")
        top.addWidget(title)
        top.addStretch()
        settings_btn = QPushButton()
        settings_btn.setIcon(_make_gear_icon(32, QColor(_C["accent"])))
        settings_btn.setIconSize(QSize(22, 22))
        settings_btn.setFixedSize(36, 36)
        settings_btn.setToolTip("Settings")
        settings_btn.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.06);
            }
        """)
        settings_btn.clicked.connect(self._open_settings)
        top.addWidget(settings_btn)
        root.addLayout(top)
        root.addSpacing(4)

        # ── context section ──
        ctx_row = QHBoxLayout()
        named_lbl = QLabel("Context:")
        named_lbl.setStyleSheet(f"font-size: 12px; color: {_C['text_secondary']};")
        ctx_row.addWidget(named_lbl)
        self.context_combo = QComboBox()
        self.context_combo.setMinimumWidth(180)
        self._refresh_contexts()
        ctx_row.addWidget(self.context_combo, 1)
        add_ctx_btn = QPushButton("+")
        add_ctx_btn.setFixedSize(28, 28)
        add_ctx_btn.setToolTip("Create new named context")
        add_ctx_btn.setStyleSheet(_BTN_SECONDARY + """
            QPushButton { font-size: 16px; font-weight: bold; padding: 0px; }
        """)
        add_ctx_btn.clicked.connect(self._add_context)
        ctx_row.addWidget(add_ctx_btn)

        self._edit_ctx_btn = QPushButton("✏")
        self._edit_ctx_btn.setFixedSize(36, 36)
        self._edit_ctx_btn.setToolTip("Edit context file in default editor")
        self._edit_ctx_btn.setStyleSheet(_BTN_SECONDARY + """
            QPushButton { font-size: 18px; padding: 0px; color: #b08800; }
        """)
        self._edit_ctx_btn.clicked.connect(self._edit_context)
        self._edit_ctx_btn.setVisible(False)
        ctx_row.addWidget(self._edit_ctx_btn)

        self._del_ctx_btn = QPushButton("×")
        self._del_ctx_btn.setFixedSize(28, 28)
        self._del_ctx_btn.setToolTip("Delete selected context")
        self._del_ctx_btn.setStyleSheet(_BTN_SECONDARY + """
            QPushButton { font-size: 18px; font-weight: bold; padding: 0px; color: #cc3333; }
        """)
        self._del_ctx_btn.clicked.connect(self._delete_context)
        self._del_ctx_btn.setVisible(False)
        ctx_row.addWidget(self._del_ctx_btn)
        self.context_combo.currentIndexChanged.connect(self._on_context_combo_changed)
        root.addLayout(ctx_row)

        self._gen_lbl = QLabel("General context")
        self._gen_lbl.setStyleSheet(f"font-size: 11px; color: {_C['text_secondary']}; margin: 0;")
        self._gen_lbl.setContentsMargins(0, 0, 0, 0)
        self._gen_lbl.setVisible(False)
        root.addWidget(self._gen_lbl)
        self.general_ctx = QTextEdit()
        self.general_ctx.setPlaceholderText("Key info: meeting type, goals, usual participants, key terms…")
        self.general_ctx.setMinimumHeight(68)
        self.general_ctx.setMaximumHeight(90)
        self.general_ctx.setAcceptRichText(False)
        self.general_ctx.setVisible(False)
        self.general_ctx.setSizePolicy(self.general_ctx.sizePolicy().horizontalPolicy(),
                                        QSizePolicy.Policy.Preferred)
        root.addWidget(self.general_ctx)

        self._mtg_lbl = QLabel("This meeting context")
        self._mtg_lbl.setStyleSheet(f"font-size: 11px; color: {_C['text_secondary']}; margin: 0;")
        self._mtg_lbl.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._mtg_lbl)
        self.meeting_ctx = QTextEdit()
        self.meeting_ctx.setPlaceholderText("Agenda, attendees, specific details for this meeting…")
        self.meeting_ctx.setMinimumHeight(68)
        self.meeting_ctx.setMaximumHeight(90)
        self.meeting_ctx.setAcceptRichText(False)
        self.meeting_ctx.setSizePolicy(self.meeting_ctx.sizePolicy().horizontalPolicy(),
                                        QSizePolicy.Policy.Preferred)
        root.addWidget(self.meeting_ctx)

        # ── instructions profile row ──
        profile_row = QHBoxLayout()
        profile_row.setSpacing(6)
        profile_lbl = QLabel("Instructions:")
        profile_lbl.setStyleSheet(f"font-size: 11px; color: {_C['text_secondary']};")
        profile_row.addWidget(profile_lbl)
        self.profile_select = QComboBox()
        self.profile_select.setMinimumWidth(140)
        self._reload_main_profile_combo()
        self.profile_select.currentIndexChanged.connect(self._on_main_profile_changed)
        profile_row.addWidget(self.profile_select)
        profile_row.addStretch()
        root.addLayout(profile_row)

        # ── record button ──
        root.addSpacing(6)
        self._mic_icon = _make_mic_icon(48, QColor(_C["primary_text"]))
        self._stop_icon = _make_stop_icon(48)
        self.record_btn = QPushButton("  Start Recording")
        self.record_btn.setIcon(self._mic_icon)
        self.record_btn.setIconSize(QSize(22, 22))
        self.record_btn.setMinimumHeight(50)
        self.record_btn.setStyleSheet(_BTN_PRIMARY)
        self.record_btn.clicked.connect(self._toggle_recording)
        root.addWidget(self.record_btn)

        # ── file buttons ──
        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        open_wav = QPushButton("Summarize Audio File")
        open_wav.setStyleSheet(_BTN_SECONDARY)
        open_wav.clicked.connect(self._open_audio)
        open_txt = QPushButton("Summarize Transcript")
        open_txt.setStyleSheet(_BTN_SECONDARY)
        open_txt.clicked.connect(self._open_transcript)
        file_row.addWidget(open_wav)
        file_row.addWidget(open_txt)
        root.addLayout(file_row)

        # ── drop zone ──
        self.drop_label = QLabel("or drag & drop audio / transcript files here")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet(f"""
            color: {_C['text_muted']};
            font-size: 12px;
            padding: 2px;
        """)
        root.addWidget(self.drop_label)

        # ── status row ──
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"""
            background-color: transparent;
            color: {_C['text_secondary']};
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
        self.result_text.setPlaceholderText("Summary will appear here…")
        self.result_text.setMinimumHeight(120)
        self.result_text.setStyleSheet("""
            QTextEdit {
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                selection-background-color: rgba(74, 144, 217, 0.25);
            }
        """)
        self.result_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.result_text, 1)

        # ── bottom buttons ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        self.copy_btn = QPushButton("  Copy Summary")
        self.copy_btn.setIcon(_make_copy_icon(24, QColor(_C["primary"])))
        self.copy_btn.setIconSize(QSize(16, 16))
        self.copy_btn.setStyleSheet(_BTN_SECONDARY)
        self.copy_btn.clicked.connect(self._copy_summary)
        self.copy_btn.setEnabled(False)
        bottom_row.addWidget(self.copy_btn)

        self.transcript_btn = QPushButton("  Open Transcript")
        self.transcript_btn.setStyleSheet(_BTN_SECONDARY)
        self.transcript_btn.clicked.connect(self._open_transcript_file)
        self.transcript_btn.setEnabled(False)
        bottom_row.addWidget(self.transcript_btn)

        bottom_row.addStretch()

        self.update_ctx_btn = QPushButton("Update Context")
        self.update_ctx_btn.setStyleSheet(_BTN_PRIMARY + """
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

    def _is_transcribe_only(self) -> bool:
        return bool(config.load().get("transcribe_only", False))

    def _apply_mode_ui(self):
        """Update UI labels based on transcribe-only mode."""
        if self._is_transcribe_only():
            self.copy_btn.setText("  Copy Transcript")
            self.result_text.setPlaceholderText("Transcript will appear here…")
        else:
            self.copy_btn.setText("  Copy Summary")
            self.result_text.setPlaceholderText("Summary will appear here…")

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
        self._edit_ctx_btn.setVisible(has_selection)
        self._del_ctx_btn.setVisible(has_selection)
        self._gen_lbl.setVisible(has_selection)
        self.general_ctx.setVisible(has_selection)

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
        self.context_combo.addItem("(none)", "")
        for name in list_contexts():
            self.context_combo.addItem(name, name)
        if prev:
            idx = self.context_combo.findData(prev)
            if idx >= 0:
                self.context_combo.setCurrentIndex(idx)
        self.context_combo.blockSignals(False)
        self._on_context_combo_changed()

    def _add_context(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Context", "Context name:")
        if ok and name.strip():
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
        answer = QMessageBox.question(
            self, "Delete Context",
            f"Delete context '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
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
        from PyQt6.QtGui import QDesktopServices
        rdir = config.get_recordings_dir()
        ctx_file = rdir / f"{name}_context.txt"
        ctx_file.touch(exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx_file)))

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
        self.record_btn.setText("  Stop  0:00")
        self.record_btn.setIcon(self._stop_icon)
        self.record_btn.setStyleSheet(_BTN_RECORDING)
        self._rec_timer.start()
        self._set_status("Recording…", "recording")

        # Start real-time transcription
        self._rt_model_ready = False
        self._rt_sample_rate = self._recorder.sample_rate
        self._rt_committed_len = 0
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("Live transcript will appear here while recording…")
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
            self._set_status("Recording failed — no audio captured", "error")
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
            self._set_status(f"{status_prefix}Finishing last few seconds…", "busy")
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
            self._set_status(f"{status_prefix}Processing recording…", "busy")
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
            self._on_error(
                "No speech detected in the recording.\n\n"
                "Possible reasons:\n"
                "- The recording was too short\n"
                "- Microphone didn't capture audio (check Input Device in Settings)\n"
                "- Audio was too quiet"
            )
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

        if self._is_transcribe_only():
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
            self._finish_recording_with_rt(duration, "Silence detected — ")

    def _update_rec_elapsed(self):
        if self._recording_start is None:
            return
        elapsed = int(time.monotonic() - self._recording_start)
        mins, secs = divmod(elapsed, 60)
        self.record_btn.setText(f"  Stop  {mins}:{secs:02d}")

    def _reset_record_btn(self):
        self._recording_start = None
        self.record_btn.setText("  Start Recording")
        self.record_btn.setIcon(self._mic_icon)
        self.record_btn.setStyleSheet(_BTN_PRIMARY)

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

    def _open_audio(self):
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Open Audio File", "", f"Audio ({exts})")
        if path:
            self._process_audio(path)

    def _open_transcript(self):
        exts = " ".join(f"*{e}" for e in sorted(TRANSCRIPT_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Open Transcript", "", f"Text ({exts})")
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
        self._set_status("Unsupported file type", "error")

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
            self._on_error(
                "No speech detected in the recording.\n\n"
                "Possible reasons:\n"
                "- The recording was too short\n"
                "- Microphone didn't capture audio (check Input Device in Settings)\n"
                "- Audio was too quiet"
            )
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

        if self._is_transcribe_only():
            self._finish_with_transcript(transcript)
        else:
            self._run_summarize(transcript, duration_seconds=getattr(self, "_pending_duration", None))
        self._pending_duration = None

    def _process_transcript_file(self, file_path: str):
        """Read transcript and summarize."""
        try:
            text = Path(file_path).read_text(encoding="utf-8").strip()
        except Exception as e:
            self._on_error(f"Failed to read file: {e}")
            return
        if not text:
            self._on_error("File is empty")
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
        self._set_status("Done", "done")
        if config.load().get("sound_on_done", True):
            self._play_done_sound()

    def _on_summary_done(self, summary: str):
        self._set_busy(False)
        self._saved_summary = summary
        self._summary_context_name = self.context_combo.currentData() or None
        self.result_text.setPlainText(summary)
        self.copy_btn.setEnabled(True)
        self.transcript_btn.setEnabled(bool(self._current_transcript_path))
        self.update_ctx_btn.setVisible(False)
        self._set_status("Done", "done")
        self._refresh_contexts()
        if config.load().get("sound_on_done", True):
            self._play_done_sound()

    def _on_result_text_changed(self):
        if not self._saved_summary or not self._summary_context_name:
            return
        current = self.result_text.toPlainText()
        self.update_ctx_btn.setVisible(current != self._saved_summary)

    def _update_context_entry(self):
        from .summarizer import update_latest_context_entry
        name = self._summary_context_name
        if not name:
            return
        new_text = self.result_text.toPlainText().strip()
        if not new_text:
            return
        try:
            update_latest_context_entry(name, new_text)
            self._saved_summary = new_text
            self.update_ctx_btn.setVisible(False)
            self._set_status("Context updated", "done")
        except Exception as e:
            _logger.error("Failed to update context: %s", e)
            QMessageBox.warning(self, "Error", f"Could not update context: {e}")

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
        QMessageBox.critical(self, "Error", msg)

    # ── helpers ──────────────────────────────────────────────────────

    def _set_status(self, msg: str, kind: str = "info"):
        colors = {
            "info":      (_C["text_secondary"], "transparent"),
            "recording": ("#ffffff",            _C["danger"]),
            "busy":      (_C["primary"],        f"rgba(74, 144, 217, 0.1)"),
            "done":      (_C["success"],        f"rgba(45, 138, 78, 0.1)"),
            "error":     ("#ffffff",            _C["danger"]),
        }
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
            self._set_status("Copied to clipboard", "done")

    def _open_transcript_file(self):
        if self._current_transcript_path and Path(self._current_transcript_path).exists():
            import subprocess
            subprocess.Popen(["open", self._current_transcript_path])
        else:
            self._set_status("No transcript file available", "error")

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


# ── entry point ──────────────────────────────────────────────────────────

def main():
    config.setup_logging()
    import logging
    _logger = logging.getLogger("app")
    _logger.info("Summarizer starting")

    app = QApplication(sys.argv)
    app.setApplicationName("Summarizer")

    icon_path = Path(__file__).parent / "icon.png"
    if icon_path.exists():
        app_icon = QIcon(str(icon_path))
    else:
        app_icon = QIcon(_make_app_icon(512))
    app.setWindowIcon(app_icon)

    window = MainWindow()
    window.show()

    # Show quick setup on first run (no API key configured yet)
    cfg = config.load()
    is_first_run = not cfg.get("api_key", "").strip() and not cfg.get("setup_done")
    if is_first_run:
        dlg = QuickSetupDialog(window)
        dlg.exec()
        # Mark setup as seen so we don't show again even if key is skipped
        cfg2 = config.load()
        cfg2["setup_done"] = True
        config.save(cfg2)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
