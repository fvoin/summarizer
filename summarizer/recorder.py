"""Audio recorder with silence detection.

Based on aidude MultiAudioRecorder but standalone (no chat_io dependency).
"""

import os
import shutil
import subprocess
import threading
import time
import datetime
from typing import Optional, List, Dict, Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

from . import config


import logging
_logger = logging.getLogger("recorder")

def _log(msg: str):
    _logger.info(msg)


class AudioRecorder:
    def __init__(self, silence_timeout: float = 30.0, input_device: Optional[int] = None):
        self._recording = False
        self._threads: list = []
        self._audio_file: Optional[str] = None
        self._stop_event: Optional[threading.Event] = None
        self._monitor_thread: Optional[threading.Thread] = None

        self._last_sound_time: Optional[float] = None
        self._silence_threshold = silence_timeout
        self._sound_time_lock = threading.Lock()
        self._rms_threshold = 0.001
        self._peak_rms = 0.0
        self._last_rms_log_time = 0.0

        self.sample_rate = 44100
        self.channels = 1
        self._input_device = input_device
        self._temp_files: list = []
        self._on_auto_stop: Optional[Callable] = None

    # ── device listing ───────────────────────────────────────────────────

    @staticmethod
    def list_devices() -> List[Dict]:
        devices = sd.query_devices()
        result = []
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                result.append({"id": i, "name": dev["name"], "channels": dev["max_input_channels"]})
        return result

    # ── silence detection ────────────────────────────────────────────────

    def _detect_silence(self, audio_data: np.ndarray) -> bool:
        if len(audio_data) == 0:
            return True
        rms = np.sqrt(np.mean(audio_data ** 2))
        if rms > self._peak_rms:
            self._peak_rms = rms
        now = time.time()
        if now - self._last_rms_log_time >= 5.0:
            self._last_rms_log_time = now
            self._peak_rms = 0.0
        return rms < self._rms_threshold

    # ── recording ────────────────────────────────────────────────────────

    def start(self, on_auto_stop: Optional[Callable] = None) -> str:
        if self._recording:
            raise RuntimeError("Recording already in progress")

        self._on_auto_stop = on_auto_stop

        all_devs = self.list_devices()
        selected = []

        if self._input_device is not None:
            selected.append(self._input_device)
        else:
            loopback = None
            for d in all_devs:
                name = d["name"].lower()
                if "blackhole" in name or "loopback" in name or "monitor" in name:
                    loopback = d["id"]
                    break
            default_in = sd.default.device[0]
            if loopback is not None:
                selected.append(loopback)
                if default_in != loopback:
                    selected.append(default_in)
            else:
                selected.append(default_in)

        selected = list(set(selected))
        _log(f"Selected device IDs: {selected}")
        for idx in selected:
            for d in all_devs:
                if d["id"] == idx:
                    _log(f"Recording from device {idx}: {d['name']} ({d['channels']}ch)")

        import tempfile
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._audio_file = os.path.join(tempfile.gettempdir(), f"summarizer_recording_{ts}.wav")
        self._recording = True
        self._stop_event = threading.Event()
        self._last_sound_time = time.time()
        self._last_rms_log_time = time.time()
        self._peak_rms = 0.0
        self._temp_files = []
        self._threads = []

        tmp_dir = tempfile.gettempdir()
        for idx in selected:
            tmp = os.path.join(tmp_dir, f"summarizer_rec_{ts}_{idx}.wav")
            self._temp_files.append(tmp)
            t = threading.Thread(target=self._record_to_file, args=(idx, tmp, self._stop_event), daemon=True)
            t.start()
            self._threads.append(t)

        self._monitor_thread = threading.Thread(target=self._monitor_silence, daemon=True)
        self._monitor_thread.start()
        return self._audio_file

    def _record_to_file(self, device_id: int, filename: str, stop_event: threading.Event):
        try:
            _log(f"Opening InputStream on device {device_id}, sr={self.sample_rate}, ch={self.channels}")
            frames_written = 0
            with sf.SoundFile(filename, mode="w", samplerate=self.sample_rate, channels=self.channels) as f:
                def callback(indata, frame_count, time_info, status):
                    nonlocal frames_written
                    if status:
                        _log(f"Stream status: {status}")
                    if not self._detect_silence(indata):
                        with self._sound_time_lock:
                            self._last_sound_time = time.time()
                    f.write(indata)
                    frames_written += frame_count

                with sd.InputStream(device=device_id, samplerate=self.sample_rate, channels=self.channels, callback=callback):
                    while not stop_event.is_set():
                        time.sleep(0.1)

            _log(f"Recording thread done (dev {device_id}): {frames_written} frames → {filename}")
        except Exception as e:
            _logger.exception("Recording thread error (dev %s)", device_id)

    def _monitor_silence(self):
        while not self._stop_event.is_set() and self._recording:
            with self._sound_time_lock:
                elapsed = time.time() - self._last_sound_time
            if elapsed > self._silence_threshold:
                _log(f"Silence detected ({elapsed:.1f}s). Auto-stopping.")
                self._stop_event.set()
                self._recording = False
                if self._on_auto_stop:
                    self._on_auto_stop()
                break
            time.sleep(1.0)

    def stop(self) -> Optional[str]:
        if self._stop_event is None:
            _log("stop() called but no recording active")
            return None
        self._recording = False
        if self._stop_event:
            self._stop_event.set()
        for t in self._threads:
            t.join(timeout=5)
        if self._monitor_thread and self._monitor_thread != threading.current_thread():
            self._monitor_thread.join(timeout=5)

        existing = [f for f in self._temp_files if os.path.exists(f)]
        _log(f"Temp files: {self._temp_files}")
        for f in self._temp_files:
            if os.path.exists(f):
                _log(f"  {f}: {os.path.getsize(f)} bytes")
            else:
                _log(f"  {f}: MISSING")
        try:
            if not existing:
                _log("No temp files found — nothing captured")
                return None
            self._mix_files(existing, self._audio_file)
            if os.path.exists(self._audio_file):
                sz = os.path.getsize(self._audio_file)
                _log(f"Final recording: {self._audio_file} ({sz} bytes)")
                if sz < 1000:
                    _log("WARNING: file very small, mic may not have captured audio")
                return self._audio_file
            _log("Final output file missing after mix")
            return None
        except Exception as e:
            _logger.exception("Mixing failed")
            return None
        finally:
            for f in self._temp_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def is_recording(self) -> bool:
        return self._recording and not (self._stop_event is not None and self._stop_event.is_set())

    def _find_ffmpeg(self) -> str:
        """Find a working ffmpeg binary. Prefer system install over bundled."""
        candidates = [
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/usr/bin/ffmpeg",
            "ffmpeg",
        ]
        for path in candidates:
            try:
                result = subprocess.run(
                    [path, "-version"], capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    _log(f"Using ffmpeg: {path}")
                    return path
            except Exception:
                continue
        _log("No working ffmpeg found")
        return "ffmpeg"

    def _mix_files(self, inputs: List[str], output: str):
        if len(inputs) == 1:
            shutil.copy(inputs[0], output)
            return

        ffmpeg = self._find_ffmpeg()
        cmd = [ffmpeg, "-y"]
        for inp in inputs:
            cmd.extend(["-i", inp])
        cmd.extend(["-filter_complex", f"amix=inputs={len(inputs)}:duration=longest", output])
        _log(f"Mixing {len(inputs)} files with: {ffmpeg}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            _log(f"ffmpeg mix failed: {result.stderr[:300]}")
            _log("Falling back to largest single file")
            best = max(inputs, key=lambda f: os.path.getsize(f))
            shutil.copy(best, output)
