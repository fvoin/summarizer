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
        # Guards the calibration/threshold state below, which is touched by
        # several capture threads at once (each mic stream + the system-audio
        # IO thread). Without it the read-modify-write of the noise floor races.
        self._silence_lock = threading.Lock()
        self._rms_threshold = 0.01
        self._noise_floor = 0.0
        self._calibrating = True
        self._calibration_samples: list = []
        self._calibration_end: float = 0.0
        self._peak_rms = 0.0
        self._last_rms_log_time = 0.0

        self.sample_rate = 44100
        self.channels = 1
        self._input_device = input_device
        self._temp_files: list = []
        self._on_auto_stop: Optional[Callable] = None

        # Real-time audio buffer — one list per device, concatenated sequentially on read
        self._rt_frames_per_device: dict = {}
        self._rt_lock = threading.Lock()

        self._sys_audio = None  # SystemAudioRecorder when active
        self._sys_audio_rate = 44100  # source rate of system audio callbacks

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

    _CALIBRATION_SECS = 3.0
    _CALIBRATION_FACTOR = 6.0
    _MIN_THRESHOLD = 0.005
    _NOISE_ADAPT_ALPHA = 0.005  # how fast noise floor tracks ambient changes

    def _detect_silence(self, audio_data: np.ndarray) -> bool:
        if len(audio_data) == 0:
            return True
        # Heavy math stays outside the lock; only shared-state access is guarded.
        rms = float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
        now = time.time()

        with self._silence_lock:
            if rms > self._peak_rms:
                self._peak_rms = rms

            if self._calibrating:
                self._calibration_samples.append(rms)
                if now >= self._calibration_end:
                    # Use 10th percentile to capture true quiet frames, ignoring speech bursts
                    raw_floor = float(np.percentile(self._calibration_samples, 10)) if self._calibration_samples else 0.0
                    self._noise_floor = raw_floor
                    self._rms_threshold = max(raw_floor * self._CALIBRATION_FACTOR, self._MIN_THRESHOLD)
                    self._calibrating = False
                    with self._sound_time_lock:
                        self._last_sound_time = now
                    _log(f"Silence calibration done: noise_floor={raw_floor:.5f}, "
                         f"threshold={self._rms_threshold:.5f} "
                         f"({len(self._calibration_samples)} samples)")
                return False

            # Continuously adapt noise floor on quiet frames so threshold tracks ambient changes
            if rms < self._rms_threshold:
                self._noise_floor = (1 - self._NOISE_ADAPT_ALPHA) * self._noise_floor + self._NOISE_ADAPT_ALPHA * rms
                self._rms_threshold = max(self._noise_floor * self._CALIBRATION_FACTOR, self._MIN_THRESHOLD)

            if now - self._last_rms_log_time >= 10.0:
                _log(f"RMS: current={rms:.5f}, peak={self._peak_rms:.5f}, threshold={self._rms_threshold:.5f}, noise_floor={self._noise_floor:.5f}")
                self._last_rms_log_time = now
                self._peak_rms = 0.0

            return rms < self._rms_threshold

    # ── recording ────────────────────────────────────────────────────────

    def start(self, on_auto_stop: Optional[Callable] = None) -> str:
        if self._recording:
            raise RuntimeError("Recording already in progress")

        self._on_auto_stop = on_auto_stop

        all_devs = self.list_devices()

        # Mic input: user-picked device, or system default mic
        if self._input_device is not None:
            mic_devices = [self._input_device]
        else:
            mic_devices = [sd.default.device[0]]

        import tempfile
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._audio_file = os.path.join(tempfile.gettempdir(), f"summarizer_recording_{ts}.wav")
        self._recording = True
        self._stop_event = threading.Event()
        now = time.time()
        self._last_sound_time = now
        self._last_rms_log_time = now
        self._peak_rms = 0.0
        self._calibrating = True
        self._calibration_samples = []
        self._calibration_end = now + self._CALIBRATION_SECS
        self._temp_files = []
        self._threads = []
        with self._rt_lock:
            self._rt_frames_per_device = {}

        tmp_dir = tempfile.gettempdir()

        # ── System audio: prefer Core Audio Process Tap (audio-only perm) ──
        self._sys_audio = None
        sys_started = False

        try:
            from . import audio_tap
            tap_available = audio_tap.is_available()
            _log(f"Core Audio Process Tap available: {tap_available}")
            if tap_available:
                sys_tmp = os.path.join(tmp_dir, f"summarizer_sys_{ts}.wav")
                self._sys_audio = audio_tap.AudioTapRecorder(
                    sample_rate=48000,
                    output_path=sys_tmp,
                    on_audio_chunk=self._on_system_audio_chunk,
                )
                _log("Starting Core Audio Process Tap…")
                if self._sys_audio.start():
                    sys_started = True
                    self._sys_audio_rate = 48000
                    self._temp_files.append(sys_tmp)
                    _log("System audio capture active via Core Audio Process Tap")
                else:
                    _log(f"Process Tap failed: {self._sys_audio.error}")
                    self._sys_audio = None
        except Exception:
            _logger.exception("Process Tap init error")
            self._sys_audio = None

        # Fall back to ScreenCaptureKit on older macOS (13.x – 14.1)
        if not sys_started:
            try:
                from . import system_audio
                sck_available = system_audio.is_available()
                _log(f"ScreenCaptureKit available: {sck_available}")
                if sck_available:
                    sys_tmp = os.path.join(tmp_dir, f"summarizer_sys_{ts}.wav")
                    self._sys_audio = system_audio.SystemAudioRecorder(
                        sample_rate=self.sample_rate,
                        output_path=sys_tmp,
                        on_audio_chunk=self._on_system_audio_chunk,
                    )
                    _log("Starting ScreenCaptureKit system audio capture…")
                    if self._sys_audio.start():
                        sys_started = True
                        self._sys_audio_rate = self.sample_rate
                        self._temp_files.append(sys_tmp)
                        _log("System audio capture active via ScreenCaptureKit")
                    else:
                        _log(f"ScreenCaptureKit failed: {self._sys_audio.error}")
                        self._sys_audio = None
            except Exception:
                _logger.exception("ScreenCaptureKit init error")
                self._sys_audio = None

        # ── Fallback: add BlackHole/Loopback as input device if neither worked ──
        selected = list(mic_devices)
        if not sys_started and self._input_device is None:
            for d in all_devs:
                name = d["name"].lower()
                if "blackhole" in name or "loopback" in name or "monitor" in name:
                    if d["id"] not in selected:
                        selected.append(d["id"])
                        _log(f"System audio APIs unavailable — using loopback fallback: {d['name']}")
                    break

        selected = list(set(selected))
        _log(f"Selected mic device IDs: {selected}")
        for idx in selected:
            for d in all_devs:
                if d["id"] == idx:
                    _log(f"Recording from device {idx}: {d['name']} ({d['channels']}ch)")

        for idx in selected:
            tmp = os.path.join(tmp_dir, f"summarizer_rec_{ts}_{idx}.wav")
            self._temp_files.append(tmp)
            t = threading.Thread(
                target=self._record_to_file,
                args=(idx, tmp, self._stop_event),
                daemon=True,
            )
            t.start()
            self._threads.append(t)

        self._monitor_thread = threading.Thread(target=self._monitor_silence, daemon=True)
        self._monitor_thread.start()
        return self._audio_file

    def get_all_rt_audio(self) -> Optional[np.ndarray]:
        """Return ALL accumulated RT audio from all devices mixed together.

        Does NOT clear the buffer — each call returns the full recording so far.
        If multiple devices are recording, their audio is averaged (mixed).
        """
        # Copy references under lock, do heavy work outside
        with self._rt_lock:
            snapshot = {k: list(v) for k, v in self._rt_frames_per_device.items()}
        device_arrays = []
        for dev_id in sorted(snapshot.keys()):
            frames = snapshot[dev_id]
            if frames:
                device_arrays.append(np.concatenate(frames, axis=0))
        if not device_arrays:
            return None
        if len(device_arrays) == 1:
            return device_arrays[0]
        min_len = min(len(a) for a in device_arrays)
        mixed = np.mean([a[:min_len].astype(np.float64) for a in device_arrays], axis=0)
        return mixed.astype(np.float32)

    _SYS_AUDIO_DEV = -1

    def _on_system_audio_chunk(self, audio: np.ndarray):
        """Called from SystemAudioRecorder with each audio buffer."""
        # Resample to mic rate (44.1k) for the RT buffer if sources differ
        if self._sys_audio_rate != self.sample_rate and len(audio) > 1:
            new_len = max(1, int(len(audio) * self.sample_rate / self._sys_audio_rate))
            audio = np.interp(
                np.linspace(0, len(audio) - 1, new_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)
        if not self._detect_silence(audio):
            with self._sound_time_lock:
                self._last_sound_time = time.time()
        with self._rt_lock:
            if self._SYS_AUDIO_DEV not in self._rt_frames_per_device:
                self._rt_frames_per_device[self._SYS_AUDIO_DEV] = []
            self._rt_frames_per_device[self._SYS_AUDIO_DEV].append(audio.copy())

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
                    with self._rt_lock:
                        if device_id not in self._rt_frames_per_device:
                            self._rt_frames_per_device[device_id] = []
                        self._rt_frames_per_device[device_id].append(indata.copy())

                with sd.InputStream(device=device_id, samplerate=self.sample_rate, channels=self.channels, callback=callback):
                    while not stop_event.is_set():
                        time.sleep(0.1)

            _log(f"Recording thread done (dev {device_id}): {frames_written} frames → {filename}")
        except Exception as e:
            _logger.exception("Recording thread error (dev %s)", device_id)

    def _monitor_silence(self):
        while not self._stop_event.is_set() and self._recording:
            if self._calibrating:
                time.sleep(1.0)
                continue
            with self._sound_time_lock:
                elapsed = time.time() - self._last_sound_time
            if elapsed > self._silence_threshold:
                _log(f"Silence detected ({elapsed:.1f}s > {self._silence_threshold}s). Auto-stopping.")
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

        if self._sys_audio:
            self._sys_audio.stop()
            self._sys_audio = None

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
        # Resample each input to 44100 Hz before mixing (tap runs at 48k, mic at 44.1k)
        filter_parts = [f"[{i}:a]aresample=44100[a{i}]" for i in range(len(inputs))]
        filter_parts.append(
            "".join(f"[a{i}]" for i in range(len(inputs)))
            + f"amix=inputs={len(inputs)}:duration=longest"
        )
        cmd.extend(["-filter_complex", ";".join(filter_parts), output])
        _log(f"Mixing {len(inputs)} files with: {ffmpeg}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            _log(f"ffmpeg mix failed: {result.stderr[:300]}")
            _log("Falling back to largest single file")
            best = max(inputs, key=lambda f: os.path.getsize(f))
            shutil.copy(best, output)
