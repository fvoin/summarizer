"""Transcription QThread workers, shared by the full and lite apps.

This module must not import summarizer.summarizer or summarizer.db so the lite
app can reuse it without pulling in the cloud LLM SDKs or the history layer.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

import numpy as np

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

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
            diarize.annotate_energies(self._mic_path, mic_segs)
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


class LiveTranscriber(QObject):
    """Drives real-time (untagged) transcription for display during recording.

    Encapsulates the RealtimeTranscribeWorker + a poll timer + committed-sample
    bookkeeping, so a window can show live text without duplicating the
    orchestration. Emits text_appended(str) as new chunks arrive.
    """
    text_appended = pyqtSignal(str)

    _POLL_MS = 10000
    _MIN_DELTA_SEC = 3.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recorder = None
        self._worker = None
        self._retired = []  # running workers kept alive until they finish
        self._committed_len = 0
        self._sample_rate = 44100
        self._timer = QTimer(self)
        self._timer.setInterval(self._POLL_MS)
        self._timer.timeout.connect(self._on_tick)

    def start(self, recorder, whisper_model: str):
        self._recorder = recorder
        self._committed_len = 0
        self._sample_rate = getattr(recorder, "sample_rate", 44100)
        self._worker = RealtimeTranscribeWorker(whisper_model)
        self._worker.model_ready.connect(self._on_model_ready)
        self._worker.chunk_ready.connect(self._on_chunk)
        self._worker.error.connect(lambda e: _logger.warning("LiveTranscriber: %s", e))
        self._worker.start()

    def _on_model_ready(self):
        if self._recorder is not None and self._recorder.is_recording():
            self._timer.start()

    def _on_tick(self):
        try:
            if self._recorder is None or self._worker is None:
                return
            all_audio = self._recorder.get_all_rt_audio()
            if all_audio is None or len(all_audio) == 0:
                return
            delta = all_audio[self._committed_len:]
            if len(delta) < self._sample_rate * self._MIN_DELTA_SEC:
                return
            self._worker.push_audio(delta, self._sample_rate)
        except Exception:
            _logger.exception("LiveTranscriber tick failed (recording continues)")

    def _on_chunk(self, text: str, audio_len: int):
        self._committed_len += audio_len
        if text:
            self.text_appended.emit(text)

    def stop(self):
        self._timer.stop()
        w = self._worker
        self._worker = None
        self._recorder = None
        if w is None:
            return
        try:
            w.chunk_ready.disconnect(self._on_chunk)
        except (TypeError, RuntimeError):
            pass
        if w.isRunning():
            # Destroying a running QThread aborts the process. request_stop()
            # ends the worker's loop after its in-flight chunk finishes; keep a
            # reference until finished() fires so it is never GC'd mid-run.
            self._retired.append(w)
            w.finished.connect(lambda: self._drop_retired(w))
            w.request_stop()

    def _drop_retired(self, worker):
        if worker in self._retired:
            self._retired.remove(worker)


class RealtimeDiarizer(QThread):
    """Real-time speaker separation.

    Transcribes the mic and system streams SEPARATELY and incrementally while
    recording (reading the recorder's per-stream RT buffers), so at Stop only a
    quick final delta + merge remain — instead of re-transcribing both full
    streams after the meeting. Uses beam_size=1 and a single worker (one model,
    streams processed one after another) to keep CPU load real-time-capable.
    """
    partial = pyqtSignal(str)     # live tagged transcript during recording
    finished = pyqtSignal(str)    # final tagged transcript
    error = pyqtSignal(str)

    _INTERVAL = 20.0     # seconds between incremental passes
    _MIN_DELTA = 8.0     # min new audio (s) worth transcribing mid-recording
    _MIN_GAP = 0.5       # min system-silent gap (s) to treat as a local turn
    _MIC_RMS = 0.004     # min mic energy in a silent gap to be real speech
    _SYS_PAD = 0.3       # pad system-active regions (s) to avoid edge echo

    def __init__(self, whisper_model: str, recorder, locale: str = "en", parent=None):
        super().__init__(parent)
        self._model_name = whisper_model
        self._recorder = recorder
        self._locale = locale
        self._sr = int(getattr(recorder, "sample_rate", 44100))
        self._stop = threading.Event()
        self._aborted = False
        self._mic_segs = []
        self._sys_segs = []
        self._mic_done = 0   # samples of mic already transcribed
        self._sys_done = 0   # samples of system already transcribed

    def request_finalize(self):
        """Ask the diarizer to transcribe the tail and emit the final transcript."""
        self._stop.set()

    def request_abort(self):
        """Stop ASAP without finalizing (used when the app is quitting)."""
        self._aborted = True
        self._stop.set()

    def run(self):
        from . import diarize
        try:
            tr = Transcriber(self._model_name)
            tr._load_model()
        except Exception as e:
            _logger.exception("RealtimeDiarizer: model load failed")
            self.error.emit(str(e))
            return

        # Incremental passes while recording.
        while not self._stop.is_set():
            self._stop.wait(self._INTERVAL)
            if self._stop.is_set():
                break
            try:
                self._pass(tr, final=False)
                self.partial.emit(self._merge_text(diarize))
            except Exception:
                _logger.exception("RealtimeDiarizer: pass failed (continuing)")

        if self._aborted:
            return  # app quitting — skip finalize, exit the thread cleanly

        # Final pass, then just combine (attribution already decided by which
        # stream each segment came from — no echo guessing needed).
        try:
            self._pass(tr, final=True)
            # Single-speaker recordings -> plain, untagged transcript.
            if not self._sys_segs:
                self.finished.emit(" ".join(s.text for s in self._mic_segs).strip())
                return
            if not self._mic_segs:
                self.finished.emit(" ".join(s.text for s in self._sys_segs).strip())
                return
            self.finished.emit(diarize.format_transcript(self._combined(), locale=self._locale))
        except Exception as e:
            _logger.exception("RealtimeDiarizer: finalize failed")
            self.error.emit(str(e))

    def _pass(self, tr, final: bool):
        """Transcribe new system audio (Remote), and the mic ONLY where the
        remote is silent (your turns). Echo during remote speech is never
        transcribed — the system stream already covers it."""
        streams = self._recorder.get_stream_rt_audio()
        min_new = int(self._sr * (0.5 if final else self._MIN_DELTA))

        # 1. System stream -> Remote (also defines when the remote is talking).
        sys_a = streams.get("system")
        if sys_a is not None and (len(sys_a) - self._sys_done) >= min_new:
            delta = sys_a[self._sys_done:]
            for s in tr.transcribe_array_segments(
                    delta, self._sr, time_offset=self._sys_done / self._sr, beam_size=1):
                s.speaker = "remote"
                self._sys_segs.append(s)
            self._sys_done = len(sys_a)

        # 2. Mic -> Me, only within system-silent gaps that contain real speech.
        mic_a = streams.get("mic")
        if mic_a is not None and (len(mic_a) - self._mic_done) >= min_new:
            t0 = self._mic_done / self._sr
            t1 = len(mic_a) / self._sr
            for g0, g1 in self._silent_gaps(t0, t1):
                if (g1 - g0) < self._MIN_GAP:
                    continue
                chunk = mic_a[int(g0 * self._sr):int(g1 * self._sr)]
                if len(chunk) == 0:
                    continue
                rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
                if rms < self._MIC_RMS:
                    continue  # silence / no real local speech in this gap
                for s in tr.transcribe_array_segments(chunk, self._sr, time_offset=g0, beam_size=1):
                    s.speaker = "me"
                    self._mic_segs.append(s)
            self._mic_done = len(mic_a)

    def _silent_gaps(self, t0: float, t1: float):
        """Sub-intervals of [t0, t1] where the remote (system) is silent."""
        active = sorted((s.start - self._SYS_PAD, s.end + self._SYS_PAD)
                        for s in self._sys_segs if s.end > t0 and s.start < t1)
        gaps = []
        cur = t0
        for a0, a1 in active:
            if a0 > cur:
                gaps.append((cur, min(a0, t1)))
            cur = max(cur, a1)
            if cur >= t1:
                break
        if cur < t1:
            gaps.append((cur, t1))
        return gaps

    def _combined(self):
        segs = list(self._sys_segs) + list(self._mic_segs)
        segs.sort(key=lambda s: s.start)
        return segs

    def _merge_text(self, diarize) -> str:
        return diarize.format_transcript(self._combined(), locale=self._locale)
