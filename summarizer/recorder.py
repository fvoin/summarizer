"""Audio recorder with silence detection.

Based on aidude MultiAudioRecorder but standalone (no chat_io dependency).
"""

import os
import shutil
import subprocess
import threading
import time
import datetime
from collections import deque
from typing import Optional, List, Dict, Callable

import numpy as np
import sounddevice as sd
import soundfile as sf

from . import config


import logging
_logger = logging.getLogger("recorder")

def _log(msg: str):
    _logger.info(msg)


class StreamSilenceDetector:
    """Per-stream adaptive silence detector.

    Every capture stream (each mic device, the system-audio tap) gets its own
    instance. The tap emits digital zeros whenever nothing is playing; with a
    single shared noise floor those zeros dragged the threshold down to the
    minimum — below mic ambient level — so room noise counted as sound and
    auto-stop never fired.

    A frame alone never resets the silence timer: activity requires
    SOUND_MIN_DURATION of above-threshold audio within the last SOUND_WINDOW
    seconds, so a keyboard click or a chair creak can't keep a dead recording
    alive, while half a second of speech always registers.
    """

    CALIBRATION_SECS = 3.0
    FACTOR = 6.0
    MIN_THRESHOLD = 0.005
    # Hard cap, kept below quiet-speech RMS (~0.05): however wrong the noise
    # floor gets (calibration during music, rising ambient), speech must stay
    # above the threshold or the recorder would auto-stop mid-meeting.
    MAX_THRESHOLD = 0.04
    # Only frames below ADAPT_BAND × floor may move the floor. Frames between
    # the floor and the threshold must not raise it: threshold = 6 × floor, so
    # absorbing them is a positive-feedback loop (observed running the
    # threshold up to 0.275 — above speech level) .
    ADAPT_BAND = 2.0
    ADAPT_ALPHA_UP = 0.002    # ambient rising: adapt slowly
    ADAPT_ALPHA_DOWN = 0.05   # ambient dropping: recover fast
    SOUND_WINDOW = 1.0
    SOUND_MIN_DURATION = 0.15

    def __init__(self, name: str, sample_rate: int):
        self.name = name
        self.sample_rate = sample_rate
        self.calibrated = False
        self.noise_floor = 0.0
        self.threshold = self.MIN_THRESHOLD
        self._calibration_end: Optional[float] = None
        self._calibration_samples: list = []
        self._loud: deque = deque()  # (timestamp, duration) of loud frames
        self._loud_total = 0.0
        self._peak = 0.0
        self._last_log = 0.0

    def _clamp(self, threshold: float) -> float:
        return min(max(threshold, self.MIN_THRESHOLD), self.MAX_THRESHOLD)

    def process(self, audio, now: float) -> bool:
        """Consume one frame; return True if it is evidence of real sound."""
        if len(audio) == 0:
            return False
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        duration = len(audio) / self.sample_rate

        if not self.calibrated:
            # The window opens at the first frame, not at construction: the
            # pipeline can take seconds to deliver audio, and a wall-clock
            # window from start() can close with a single sample in it.
            if self._calibration_end is None:
                self._calibration_end = now + self.CALIBRATION_SECS
            self._calibration_samples.append(rms)
            if now >= self._calibration_end:
                # 10th percentile: quiet gaps, not speech bursts
                raw_floor = float(np.percentile(self._calibration_samples, 10))
                self.noise_floor = raw_floor
                self.threshold = self._clamp(raw_floor * self.FACTOR)
                self.calibrated = True
                _log(f"Silence calibration done [{self.name}]: "
                     f"noise_floor={raw_floor:.5f}, threshold={self.threshold:.5f} "
                     f"({len(self._calibration_samples)} samples)")
                self._calibration_samples = []
            return True  # calibrating counts as activity: no auto-stop yet

        band = max(self.noise_floor * self.ADAPT_BAND, self.MIN_THRESHOLD)
        if rms < band:
            alpha = self.ADAPT_ALPHA_DOWN if rms < self.noise_floor else self.ADAPT_ALPHA_UP
            self.noise_floor = (1 - alpha) * self.noise_floor + alpha * rms
            self.threshold = self._clamp(self.noise_floor * self.FACTOR)

        if rms > self._peak:
            self._peak = rms
        if now - self._last_log >= 10.0:
            _log(f"RMS[{self.name}]: current={rms:.5f}, peak={self._peak:.5f}, "
                 f"threshold={self.threshold:.5f}, noise_floor={self.noise_floor:.5f}")
            self._last_log = now
            self._peak = 0.0

        if rms >= self.threshold:
            self._loud.append((now, duration))
            self._loud_total += duration
        while self._loud and self._loud[0][0] < now - self.SOUND_WINDOW:
            self._loud_total -= self._loud.popleft()[1]
        return self._loud_total >= self.SOUND_MIN_DURATION


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
        # One detector per capture stream; the dict itself is guarded (streams
        # register lazily from their own callback threads), while each
        # detector's state is only ever touched by its own stream's thread.
        self._detectors: Dict[int, StreamSilenceDetector] = {}
        self._detectors_lock = threading.Lock()
        self._calibrating = True

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

        self._mic_files = []
        self._sys_file = None

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

    def _note_audio(self, stream_key: int, audio: np.ndarray,
                    now: Optional[float] = None) -> bool:
        """Feed one frame from a capture stream into its silence detector.

        Refreshes ``_last_sound_time`` when the stream shows real (sustained)
        sound. Auto-stop fires only when EVERY stream has been silent for the
        whole timeout.
        """
        if now is None:
            now = time.time()
        with self._detectors_lock:
            det = self._detectors.get(stream_key)
            if det is None:
                name = ("system" if stream_key == self._SYS_AUDIO_DEV
                        else f"mic-{stream_key}")
                det = StreamSilenceDetector(name, self.sample_rate)
                self._detectors[stream_key] = det
        activity = det.process(audio, now)
        if self._calibrating and det.calibrated:
            self._calibrating = False
        if activity:
            with self._sound_time_lock:
                if self._last_sound_time is None or now > self._last_sound_time:
                    self._last_sound_time = now
        return activity

    # ── recording ────────────────────────────────────────────────────────

    def start(self, on_auto_stop: Optional[Callable] = None) -> str:
        if self._recording:
            raise RuntimeError("Recording already in progress")

        self._on_auto_stop = on_auto_stop

        all_devs = self.list_devices()

        # Mic input: resolve the user's choice (name, legacy index, or None)
        # to a live, validated input-device id. Indices drift as devices come
        # and go, so a saved index — or even a saved name that's unplugged —
        # may not be capturable right now; fall back to a real mic.
        mic_id = self._resolve_input(self._input_device, all_devs)
        mic_devices = [mic_id] if mic_id is not None else []
        if not mic_devices:
            _log("No usable input device found — recording system audio only")

        import tempfile
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._audio_file = os.path.join(tempfile.gettempdir(), f"summarizer_recording_{ts}.wav")
        self._recording = True
        self._stop_event = threading.Event()
        now = time.time()
        self._last_sound_time = now
        self._calibrating = True
        with self._detectors_lock:
            self._detectors = {}
        self._temp_files = []
        self._mic_files = []
        self._sys_file = None
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
                    self._sys_file = sys_tmp
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
                        self._sys_file = sys_tmp
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
            self._mic_files.append(tmp)
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
                arr = np.concatenate(frames, axis=0)
                # Normalise every device buffer to 1-D mono. The mic InputStream
                # delivers 2-D frames (N, channels) while the system-audio tap
                # delivers 1-D mono (N,); mixing the two shapes with np.mean
                # raises ValueError (inhomogeneous shape). Down-mix to mono so
                # all device arrays share one shape.
                if arr.ndim > 1:
                    arr = arr.mean(axis=1)
                device_arrays.append(arr.astype(np.float32))
        if not device_arrays:
            return None
        if len(device_arrays) == 1:
            return device_arrays[0]
        min_len = min(len(a) for a in device_arrays)
        mixed = np.mean([a[:min_len].astype(np.float64) for a in device_arrays], axis=0)
        return mixed.astype(np.float32)

    def get_stream_rt_audio(self) -> dict:
        """Return accumulated RT audio for the mic and system streams SEPARATELY.

        {"mic": np.ndarray | None, "system": np.ndarray | None} — mono float32,
        full recording so far (buffer not cleared). Used for real-time speaker
        separation so the two streams can be transcribed independently while
        recording. Mic = every input device except the system-audio tap
        (mixed if several); system = the Core Audio / ScreenCaptureKit tap.
        """
        with self._rt_lock:
            snapshot = {k: list(v) for k, v in self._rt_frames_per_device.items()}

        def _concat(keys) -> Optional[np.ndarray]:
            arrays = []
            for k in keys:
                frames = snapshot.get(k)
                if not frames:
                    continue
                arr = np.concatenate(frames, axis=0)
                if arr.ndim > 1:
                    arr = arr.mean(axis=1)
                arrays.append(arr.astype(np.float32))
            if not arrays:
                return None
            if len(arrays) == 1:
                return arrays[0]
            n = min(len(a) for a in arrays)
            return np.mean([a[:n].astype(np.float64) for a in arrays], axis=0).astype(np.float32)

        mic_keys = [k for k in snapshot if k != self._SYS_AUDIO_DEV]
        return {"mic": _concat(mic_keys), "system": _concat([self._SYS_AUDIO_DEV])}

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
        self._note_audio(self._SYS_AUDIO_DEV, audio)
        with self._rt_lock:
            if self._SYS_AUDIO_DEV not in self._rt_frames_per_device:
                self._rt_frames_per_device[self._SYS_AUDIO_DEV] = []
            self._rt_frames_per_device[self._SYS_AUDIO_DEV].append(audio.copy())

    def _resolve_input(self, requested, all_devs: List[Dict]) -> Optional[int]:
        """Resolve a saved mic choice to a live input-device id, or None.

        ``requested`` may be:
          * None         — no explicit choice; use the system default.
          * str          — a device NAME (the stable identifier we persist).
          * int          — a legacy saved PortAudio index (older configs).

        Device names are matched against the current input list; a saved index
        is honoured only if it still points at a valid input device. Anything
        that no longer resolves falls back to ``_resolve_default_input`` so the
        mic is never silently dropped just because indices shifted.
        """
        if requested is None:
            return self._resolve_default_input(all_devs)

        if isinstance(requested, str):
            # Exact name match first, then a prefix match (macOS sometimes
            # appends suffixes like " #2" or localised qualifiers).
            for d in all_devs:
                if d["name"] == requested:
                    return d["id"]
            for d in all_devs:
                if d["name"].startswith(requested) or requested.startswith(d["name"]):
                    _log(f"Mic '{requested}' matched by prefix to '{d['name']}'")
                    return d["id"]
            _log(f"Saved mic '{requested}' not currently available; "
                 f"falling back to default input")
            return self._resolve_default_input(all_devs)

        # Legacy integer index.
        valid = {d["id"] for d in all_devs}
        if requested in valid:
            return requested
        _log(f"Saved mic index {requested} is no longer a valid input device; "
             f"falling back to default input")
        return self._resolve_default_input(all_devs)

    def _resolve_default_input(self, all_devs: List[Dict]) -> Optional[int]:
        """Return a usable default-input device id, or None.

        ``sd.default.device[0]`` is a PortAudio index that drifts as devices
        appear/disappear (Continuity iPhone mic, BlackHole, Zoom, aggregate
        devices). It can point at a device with no input channels, in which
        case opening it raises PortAudioError -9998 and the mic thread dies —
        the user's voice is silently dropped. Validate the index against the
        live input list and fall back to a real input device, preferring a
        physical mic over virtual/loopback devices.
        """
        valid = {d["id"] for d in all_devs}
        try:
            default_idx = sd.default.device[0]
        except Exception:
            default_idx = None
        if default_idx is not None and default_idx in valid:
            return default_idx
        _log(f"Default input index {default_idx} is not a usable input device; "
             f"falling back. Available inputs: {[(d['id'], d['name']) for d in all_devs]}")
        if not all_devs:
            return None

        def virtual_rank(d: Dict) -> int:
            n = d["name"].lower()
            if any(k in n for k in ("blackhole", "loopback", "aggregate",
                                    "zoom", "монитор", "monitor", "агрегат")):
                return 1  # de-prioritise virtual / loopback devices
            return 0

        return sorted(all_devs, key=virtual_rank)[0]["id"]

    def _record_to_file(self, device_id: int, filename: str, stop_event: threading.Event):
        try:
            try:
                info = sd.query_devices(device_id)
                max_in = int(info.get("max_input_channels", 0))
                dev_name = info.get("name", "?")
            except Exception:
                max_in, dev_name = 0, "?"
            if max_in < 1:
                _log(f"Device {device_id} ({dev_name}) reports no input channels — "
                     f"skipping mic capture")
                return

            # The output file is always mono. Open the stream in mono when the
            # device allows it, otherwise open at the device's native channel
            # count and down-mix. Opening with an unsupported channel count
            # raises PortAudioError -9998 ("Invalid number of channels"), which
            # used to kill this thread and drop the user's voice entirely.
            candidates = [1, max_in] if max_in > 1 else [1]
            last_err: Optional[Exception] = None
            for stream_channels in candidates:
                try:
                    self._stream_mic_to_file(
                        device_id, filename, stop_event, stream_channels, dev_name,
                    )
                    return
                except sd.PortAudioError as e:
                    last_err = e
                    _log(f"Mic dev {device_id} ({dev_name}) open failed at "
                         f"{stream_channels}ch: {e}")
            _logger.error("Could not open mic device %s (%s) with any channel "
                          "count: %s", device_id, dev_name, last_err)
        except Exception:
            _logger.exception("Recording thread error (dev %s)", device_id)

    def _stream_mic_to_file(self, device_id: int, filename: str,
                            stop_event: threading.Event, stream_channels: int,
                            dev_name: str):
        _log(f"Opening InputStream on device {device_id} ({dev_name}), "
             f"sr={self.sample_rate}, ch={stream_channels}")
        frames_written = 0
        with sf.SoundFile(filename, mode="w", samplerate=self.sample_rate, channels=1) as f:
            def callback(indata, frame_count, time_info, status):
                nonlocal frames_written
                if status:
                    _log(f"Stream status: {status}")
                # Down-mix to mono (frames, 1) regardless of stream channel count.
                if indata.ndim > 1 and indata.shape[1] > 1:
                    mono = indata.mean(axis=1, keepdims=True).astype(np.float32)
                else:
                    mono = indata.reshape(-1, 1).astype(np.float32)
                self._note_audio(device_id, mono)
                f.write(mono)
                frames_written += frame_count
                with self._rt_lock:
                    if device_id not in self._rt_frames_per_device:
                        self._rt_frames_per_device[device_id] = []
                    self._rt_frames_per_device[device_id].append(mono.copy())

            with sd.InputStream(device=device_id, samplerate=self.sample_rate,
                                channels=stream_channels, callback=callback):
                while not stop_event.is_set():
                    time.sleep(0.1)

        _log(f"Recording thread done (dev {device_id}): {frames_written} frames → {filename}")

    _MONITOR_POLL_SECS = 1.0

    def _monitor_silence(self):
        while not self._stop_event.is_set() and self._recording:
            if self._calibrating:
                time.sleep(self._MONITOR_POLL_SECS)
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
            time.sleep(self._MONITOR_POLL_SECS)

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
            sources = set(self._mic_files)
            if self._sys_file:
                sources.add(self._sys_file)
            for f in self._temp_files:
                if f in sources:
                    continue  # retained for diarization; freed by cleanup_sources()
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def get_source_files(self) -> dict:
        """Return the un-mixed per-stream source files that still exist.

        {"mic": [paths...], "system": path | None}. Used for post-recording
        speaker separation. Call cleanup_sources() when done with them.
        """
        mic = [f for f in self._mic_files if f and os.path.exists(f)]
        system = self._sys_file if (self._sys_file and os.path.exists(self._sys_file)) else None
        return {"mic": mic, "system": system}

    def cleanup_sources(self) -> None:
        """Delete the retained per-stream source files."""
        for f in list(self._mic_files):
            try:
                os.unlink(f)
            except OSError:
                pass
        if self._sys_file:
            try:
                os.unlink(self._sys_file)
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
