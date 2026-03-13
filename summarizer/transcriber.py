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

    snapshot_download(
        repo_id=info["repo"],
        local_dir=str(dest),
    )

    _log(f"Model {model_name} downloaded to {dest}")
    return dest


class Transcriber:
    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        local_path = config.get_model_path(self.model_name)
        if local_path:
            _log(f"Loading Whisper model '{self.model_name}' from: {local_path}")
            self._model = WhisperModel(str(local_path), device="cpu", compute_type="int8")
        else:
            _log(f"Model '{self.model_name}' not cached locally, downloading via faster-whisper…")
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")

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
