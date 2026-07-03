"""Transcription QThread workers, shared by the full and lite apps.

This module must not import summarizer.summarizer or summarizer.db so the lite
app can reuse it without pulling in the cloud LLM SDKs or the history layer.
"""

from __future__ import annotations

import logging
import queue
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from .transcriber import Transcriber
from .i18n import t

_logger = logging.getLogger("workers")


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


class DiarizeTranscribeWorker(QThread):
    """Post-recording Me/Remote speaker separation from the two source streams."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, whisper_model: str, mic_path: str, sys_path: str, parent=None):
        super().__init__(parent)
        self._model = whisper_model
        self._mic_path = mic_path
        self._sys_path = sys_path

    def run(self):
        try:
            from . import diarize
            from .i18n import locale

            tr = Transcriber(self._model)
            mic_segs = tr.transcribe_segments(self._mic_path)
            sys_segs = tr.transcribe_segments(self._sys_path)
            offset = diarize.estimate_offset(self._mic_path, self._sys_path)
            merged = diarize.merge(mic_segs, sys_segs, offset=offset)
            text = diarize.format_transcript(merged, locale=locale())
            if not text.strip():
                self.error.emit("empty")
                return
            self.finished.emit(text)
        except Exception as e:
            _logger.exception("DiarizeTranscribeWorker failed")
            self.error.emit(str(e))


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
