"""Whisper-based audio transcription.

Based on aidude WhisperService but standalone.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Callable

from . import config


import logging
_logger = logging.getLogger("transcriber")

def _log(msg: str):
    _logger.info(msg)


def download_model(model_name: str, progress_cb: Optional[Callable[[float], None]] = None) -> Path:
    """Download a Whisper model to the local cache. Returns the model directory.

    progress_cb receives a float 0.0–1.0 indicating download progress.
    """
    from huggingface_hub import snapshot_download

    info = config.WHISPER_MODELS.get(model_name)
    if not info:
        raise ValueError(f"Unknown model: {model_name}")

    dest = config.get_models_dir() / model_name
    dest.mkdir(parents=True, exist_ok=True)

    _log(f"Downloading model {model_name} ({info['repo']}) → {dest}")

    # snapshot_download exposes no progress callback, so poll the destination
    # directory size (including hub temp files) against the expected total.
    import threading
    stop = threading.Event()
    total = info.get("size_mb", 0) * 1024 * 1024
    if progress_cb and total:
        def _poll():
            while not stop.is_set():
                size = 0
                for f in dest.rglob("*"):
                    try:
                        if f.is_file():
                            size += f.stat().st_size
                    except OSError:
                        pass  # hub renames temp files mid-scan
                # size_mb is approximate: hold just under 1.0 until finished
                progress_cb(min(size / total, 0.99))
                stop.wait(0.5)
        threading.Thread(target=_poll, daemon=True).start()

    try:
        snapshot_download(
            repo_id=info["repo"],
            local_dir=str(dest),
        )
    finally:
        stop.set()

    if progress_cb:
        progress_cb(1.0)
    _log(f"Model {model_name} downloaded to {dest}")
    return dest


# Module-level cache so the WhisperModel is only loaded once per session.
_model_cache: dict = {}


class Transcriber:
    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        # Return cached instance if available (avoids re-loading between RT and final pass)
        if self.model_name in _model_cache:
            self._model = _model_cache[self.model_name]
            _log(f"Model '{self.model_name}' served from cache")
            return
        from faster_whisper import WhisperModel

        local_path = config.get_model_path(self.model_name)
        if local_path:
            _log(f"Loading Whisper model '{self.model_name}' from: {local_path}")
            self._model = WhisperModel(str(local_path), device="cpu", compute_type="int8")
        else:
            _log(f"Model '{self.model_name}' not cached locally, downloading via faster-whisper…")
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
        _model_cache[self.model_name] = self._model

    @staticmethod
    def _find_ffmpeg() -> Optional[str]:
        for path in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg", "ffmpeg"]:
            try:
                r = subprocess.run([path, "-version"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    return path
            except Exception:
                continue
        return None

    def _convert_audio(self, audio_path: str) -> str:
        """Convert to 16kHz mono WAV for Whisper."""
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            return audio_path

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        converted = tmp.name
        tmp.close()
        try:
            subprocess.run(
                [ffmpeg, "-i", audio_path, "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le", "-y", converted],
                capture_output=True, text=True, check=True,
            )
            return converted
        except Exception as e:
            _logger.warning("ffmpeg conversion failed, using original: %s", e)
            Path(converted).unlink(missing_ok=True)
            return audio_path

    def transcribe_array(self, audio_data, sample_rate: int) -> str:
        """Transcribe audio from a numpy array. Used for real-time chunk transcription."""
        import tempfile
        import soundfile as sf_mod

        self._load_model()
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            sf_mod.write(tmp_path, audio_data, sample_rate)
            converted = self._convert_audio(tmp_path)
            cleanup_conv = converted != tmp_path
            try:
                try:
                    segments, _ = self._model.transcribe(
                        converted, beam_size=3, word_timestamps=False, vad_filter=True
                    )
                except Exception:
                    segments, _ = self._model.transcribe(
                        converted, beam_size=3, word_timestamps=False
                    )
                return " ".join(seg.text for seg in segments).strip()
            finally:
                if cleanup_conv:
                    Path(converted).unlink(missing_ok=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def transcribe_segments(self, audio_path: str, language=None, beam_size: int = 5):
        """Transcribe returning per-segment timestamps for speaker separation."""
        from .diarize import Segment

        if not Path(audio_path).exists() or Path(audio_path).stat().st_size < 1000:
            return []

        self._load_model()
        converted = self._convert_audio(audio_path)
        cleanup = converted != audio_path
        try:
            try:
                segments, _ = self._model.transcribe(
                    converted, language=language, beam_size=beam_size,
                    word_timestamps=False, vad_filter=True,
                )
            except Exception:
                segments, _ = self._model.transcribe(
                    converted, language=language, beam_size=beam_size, word_timestamps=False,
                )
            return [
                Segment(start=float(s.start), end=float(s.end), text=s.text.strip())
                for s in segments
            ]
        finally:
            if cleanup:
                Path(converted).unlink(missing_ok=True)

    def transcribe_array_segments(self, audio_data, sample_rate: int,
                                  time_offset: float = 0.0, beam_size: int = 1,
                                  language=None):
        """Transcribe a numpy audio chunk into timestamped Segments.

        Fast path for real-time speaker separation: uses beam_size=1 by default
        and shifts every segment's start/end by ``time_offset`` seconds so the
        chunk's local timeline maps onto the whole-recording timeline.
        """
        import tempfile
        import soundfile as sf_mod
        from .diarize import Segment

        self._load_model()
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            sf_mod.write(tmp_path, audio_data, sample_rate)
            converted = self._convert_audio(tmp_path)
            cleanup_conv = converted != tmp_path
            try:
                try:
                    segments, _ = self._model.transcribe(
                        converted, language=language, beam_size=beam_size,
                        word_timestamps=False, vad_filter=True,
                    )
                except Exception:
                    segments, _ = self._model.transcribe(
                        converted, language=language, beam_size=beam_size, word_timestamps=False,
                    )
                return [
                    Segment(start=float(s.start) + time_offset,
                            end=float(s.end) + time_offset,
                            text=s.text.strip())
                    for s in segments
                ]
            finally:
                if cleanup_conv:
                    Path(converted).unlink(missing_ok=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        file_size = Path(audio_path).stat().st_size
        _log(f"Audio file: {audio_path} ({file_size} bytes)")
        if file_size < 1000:
            _log(f"WARNING: Audio file very small ({file_size} bytes) — likely no audio captured")

        self._load_model()
        converted = self._convert_audio(audio_path)
        cleanup = converted != audio_path

        if cleanup:
            conv_size = Path(converted).stat().st_size
            _log(f"Converted file: {converted} ({conv_size} bytes)")

        try:
            _log(f"Transcribing {converted}")
            try:
                segments, info = self._model.transcribe(converted, language=language, beam_size=5, word_timestamps=False, vad_filter=True)
            except Exception:
                _log("VAD filter unavailable (onnxruntime missing), running without it")
                segments, info = self._model.transcribe(converted, language=language, beam_size=5, word_timestamps=False)

            _log(f"Detected language: {info.language} (prob={info.language_probability:.2f}), duration={info.duration:.1f}s")
            text = " ".join(seg.text for seg in segments).strip()
            _log(f"Transcription complete: {len(text)} chars")
            if len(text) < 10:
                _log(f"WARNING: Very short transcript: '{text}'")
            return text
        finally:
            if cleanup:
                Path(converted).unlink(missing_ok=True)
