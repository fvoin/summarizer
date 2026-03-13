"""Summarizer — macOS PyQt6 application."""

import os
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
    QGroupBox, QSplitter, QProgressBar,
)

import logging

from . import config
from .recorder import AudioRecorder
from .transcriber import Transcriber, download_model
from .summarizer import (
    summarize, list_contexts, TRANSCRIPT_EXTENSIONS, AUDIO_EXTENSIONS,
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


class SummarizeWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(
        self,
        transcript: str,
        context_name: Optional[str],
        context_inline: Optional[str],
        duration_seconds: Optional[int] = None,
    ):
        super().__init__()
        self.transcript = transcript
        self.context_name = context_name
        self.context_inline = context_inline
        self.duration_seconds = duration_seconds

    def run(self):
        try:
            self.status.emit("Generating summary…")
            _logger.info("SummarizeWorker: context=%s, transcript_len=%d", self.context_name, len(self.transcript))
            result = summarize(
                self.transcript,
                self.context_name,
                self.context_inline,
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


class _LocalLLMRow(QWidget):
    """Row for a local Ollama LLM model: radio + label + status + pull/delete."""
    download_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

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

        self.dl_btn = QPushButton("Download")
        self.dl_btn.setFixedWidth(76)
        self.dl_btn.clicked.connect(lambda: self.download_requested.emit(self.model_key))
        lay.addWidget(self.dl_btn)

        self.del_btn = QPushButton("Delete")
        self.del_btn.setFixedWidth(56)
        self.del_btn.setStyleSheet("color: #cc3333;")
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
            self.progress_bar.setVisible(False)
        else:
            self.status_label.setText("Not downloaded")
            self.status_label.setStyleSheet("color: #888;")
            self.dl_btn.setVisible(True)
            self.del_btn.setVisible(False)

    def set_pulling(self):
        self.dl_btn.setVisible(False)
        self.del_btn.setVisible(False)
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
                    worker.finished.connect(self._on_download_finished)
                    worker.error.connect(self._on_download_error)
            else:
                self._download_workers.pop(model_name, None)

        for model_key, worker in list(self._local_llm_workers.items()):
            if worker.isRunning():
                row = self._local_llm_rows.get(model_key)
                if row:
                    row.set_pulling()
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

        for key, info in config.LOCAL_LLM_MODELS.items():
            downloaded = config.is_local_llm_downloaded(key) if ollama_ok else False
            row = _LocalLLMRow(key, info, is_selected=(current_model == key), is_downloaded=downloaded)
            row.download_requested.connect(self._pull_local_llm)
            row.delete_requested.connect(self._delete_local_llm)
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
        worker.finished.connect(self._on_download_finished)
        worker.error.connect(self._on_download_error)
        self._download_worker = worker
        worker.start()

    def _on_download_finished(self):
        self._update_progress.setVisible(False)
        self._update_btn.setText("Check for Updates")
        self._update_btn.setEnabled(True)

        from pathlib import Path
        dmg_path = Path.home() / "Downloads" / "Summarizer.dmg"

        msg = QMessageBox(self)
        msg.setWindowTitle("Update Ready")
        msg.setText("The new version has been downloaded.")
        msg.setInformativeText(
            "To install:\n"
            "1. Click \"Quit & Open DMG\" below\n"
            "2. Drag Summarizer to Applications\n"
            "3. Launch Summarizer from Applications"
        )
        quit_btn = msg.addButton("Quit & Open DMG", QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() == quit_btn:
            import subprocess
            subprocess.Popen(["open", str(dmg_path)])
            QApplication.quit()

    def _on_download_error(self, msg: str):
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

        self._auto_stop_signal.connect(self._on_auto_stop)
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet(_WINDOW_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(16)
        root.setContentsMargins(20, 16, 20, 16)

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

        # ── context section ──
        ctx_group = QGroupBox("Context")
        ctx_lay = QVBoxLayout(ctx_group)
        ctx_lay.setSpacing(8)

        ctx_row = QHBoxLayout()
        named_lbl = QLabel("Named:")
        named_lbl.setStyleSheet(f"font-size: 12px; color: {_C['text_secondary']};")
        ctx_row.addWidget(named_lbl)
        self.context_combo = QComboBox()
        self.context_combo.setMinimumWidth(180)
        self._refresh_contexts()
        ctx_row.addWidget(self.context_combo, 1)
        add_ctx_btn = QPushButton("+")
        add_ctx_btn.setFixedSize(30, 30)
        add_ctx_btn.setToolTip("Create new named context")
        add_ctx_btn.setStyleSheet(_BTN_SECONDARY + """
            QPushButton { font-size: 16px; font-weight: bold; padding: 0px; }
        """)
        add_ctx_btn.clicked.connect(self._add_context)
        ctx_row.addWidget(add_ctx_btn)
        ctx_lay.addLayout(ctx_row)

        self.inline_ctx = QTextEdit()
        self.inline_ctx.setPlaceholderText("Quick context (i.e. meeting title, names and roles, agenda / goals)")
        self.inline_ctx.setFixedHeight(80)
        self.inline_ctx.setAcceptRichText(False)
        ctx_lay.addWidget(self.inline_ctx)
        root.addWidget(ctx_group)

        # ── record button ──
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
        self.result_text.setReadOnly(True)
        self.result_text.setPlaceholderText("Summary will appear here…")
        self.result_text.setMinimumHeight(180)
        self.result_text.setStyleSheet("""
            QTextEdit {
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                selection-background-color: rgba(74, 144, 217, 0.25);
            }
        """)
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
        root.addLayout(bottom_row)

    # ── context management ───────────────────────────────────────────

    def _refresh_contexts(self):
        prev = self.context_combo.currentData()
        self.context_combo.clear()
        self.context_combo.addItem("(none)", "")
        for name in list_contexts():
            self.context_combo.addItem(name, name)
        if prev:
            idx = self.context_combo.findData(prev)
            if idx >= 0:
                self.context_combo.setCurrentIndex(idx)

    def _add_context(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Context", "Context name:")
        if ok and name.strip():
            self._refresh_contexts()
            idx = self.context_combo.findData(name.strip())
            if idx >= 0:
                self.context_combo.setCurrentIndex(idx)
            else:
                self.context_combo.addItem(name.strip(), name.strip())
                self.context_combo.setCurrentIndex(self.context_combo.count() - 1)

    def _get_context(self) -> tuple[Optional[str], Optional[str]]:
        """Return (context_name, context_inline). Both can be set simultaneously."""
        name = self.context_combo.currentData() or None
        inline = self.inline_ctx.toPlainText().strip() or None
        return name, inline

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

    def _stop_recording(self):
        if not self._recorder:
            return
        self._rec_timer.stop()
        duration = int(time.monotonic() - self._recording_start) if self._recording_start else None
        audio_path = self._recorder.stop()
        self._recorder = None
        self._reset_record_btn()
        if audio_path:
            _logger.info("Recording stopped, audio_path=%s, duration=%ss", audio_path, duration)
            self._set_status("Processing recording…", "busy")
            self._process_audio(audio_path, duration_seconds=duration)
        else:
            _logger.warning("Recording stopped but no audio captured")
            self._set_status("Recording failed — no audio captured", "error")

    def _on_auto_stop(self):
        """Called on main thread when silence auto-stop fires."""
        self._rec_timer.stop()
        duration = int(time.monotonic() - self._recording_start) if self._recording_start else None
        if self._recorder:
            audio_path = self._recorder.stop()
            self._recorder = None
            self._reset_record_btn()
            if audio_path:
                self._set_status("Silence detected — processing…", "busy")
                self._process_audio(audio_path, duration_seconds=duration)
            else:
                self._set_status("Recording stopped but no audio captured", "error")

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
        """Transcribe audio, then summarize."""
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
        ctx_name, _ = self._get_context()
        base = ctx_name or "transcript"
        txt_path = rdir / f"{base}_{ts}.txt"
        try:
            txt_path.write_text(transcript, encoding="utf-8")
            self._current_transcript_path = str(txt_path)
            self.transcript_btn.setEnabled(True)
        except Exception:
            pass

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
        self.transcript_btn.setEnabled(True)
        self._set_busy(True)
        self.result_text.clear()
        self._run_summarize(text)

    def _run_summarize(self, transcript: str, duration_seconds: Optional[int] = None):
        ctx_name, ctx_inline = self._get_context()
        worker = SummarizeWorker(transcript, ctx_name, ctx_inline, duration_seconds=duration_seconds)
        worker.status.connect(self._set_status_busy)
        worker.error.connect(self._on_error)
        worker.finished.connect(self._on_summary_done)
        self._track_worker(worker)
        worker.start()

    def _on_summary_done(self, summary: str):
        self._set_busy(False)
        self.result_text.setPlainText(summary)
        self.copy_btn.setEnabled(True)
        self._set_status("Done", "done")
        self._refresh_contexts()

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

    @staticmethod
    def _mrkdwn_to_html(text: str) -> str:
        """Convert Slack mrkdwn bold/italic to HTML for clipboard."""
        import re
        html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = re.sub(r"(?<!\w)\*([^\n*]+?)\*(?!\w)", r"<b>\1</b>", html)
        html = re.sub(r"(?<!\w)_([^\n_]+?)_(?!\w)", r"<i>\1</i>", html)
        html = html.replace("\n", "<br>")
        return html

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


# ── entry point ──────────────────────────────────────────────────────────

def main():
    config.setup_logging()
    import logging
    _logger = logging.getLogger("app")
    _logger.info("Summarizer starting")

    app = QApplication(sys.argv)
    app.setApplicationName("Summarizer")

    icon_pixmap = _make_app_icon(512)
    app_icon = QIcon(icon_pixmap)
    app.setWindowIcon(app_icon)

    # Save icon to disk for PyInstaller / .app bundling
    icon_path = Path(__file__).parent / "icon.png"
    if not icon_path.exists():
        icon_pixmap.save(str(icon_path), "PNG")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
