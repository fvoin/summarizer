"""System audio capture via Core Audio Process Taps (macOS 14.2+).

Uses the "System Audio Recording" permission instead of Screen Recording.
Creates a process tap and an aggregate device that exposes the tap as
an input stream, then reads audio via an IOProc.
"""

import ctypes
import logging
import os
import platform
import threading
import uuid as uuidlib
from typing import Callable, Optional

import numpy as np
import soundfile as sf

_logger = logging.getLogger("audio_tap")

# ── CoreAudio framework via ctypes ──────────────────────────────────

_ca = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreAudio.framework/CoreAudio"
)

AudioObjectID = ctypes.c_uint32
OSStatus = ctypes.c_int32

_ca.AudioHardwareCreateProcessTap.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(AudioObjectID),
]
_ca.AudioHardwareCreateProcessTap.restype = OSStatus

_ca.AudioHardwareDestroyProcessTap.argtypes = [AudioObjectID]
_ca.AudioHardwareDestroyProcessTap.restype = OSStatus

_ca.AudioHardwareCreateAggregateDevice.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(AudioObjectID),
]
_ca.AudioHardwareCreateAggregateDevice.restype = OSStatus

_ca.AudioHardwareDestroyAggregateDevice.argtypes = [AudioObjectID]
_ca.AudioHardwareDestroyAggregateDevice.restype = OSStatus

_ca.AudioDeviceCreateIOProcID.argtypes = [
    AudioObjectID, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
]
_ca.AudioDeviceCreateIOProcID.restype = OSStatus

_ca.AudioDeviceDestroyIOProcID.argtypes = [AudioObjectID, ctypes.c_void_p]
_ca.AudioDeviceDestroyIOProcID.restype = OSStatus

_ca.AudioDeviceStart.argtypes = [AudioObjectID, ctypes.c_void_p]
_ca.AudioDeviceStart.restype = OSStatus

_ca.AudioDeviceStop.argtypes = [AudioObjectID, ctypes.c_void_p]
_ca.AudioDeviceStop.restype = OSStatus


# ── AudioBufferList layout ──────────────────────────────────────────


class AudioBuffer(ctypes.Structure):
    _fields_ = [
        ("mNumberChannels", ctypes.c_uint32),
        ("mDataByteSize", ctypes.c_uint32),
        ("mData", ctypes.c_void_p),
    ]


class AudioBufferList(ctypes.Structure):
    _fields_ = [
        ("mNumberBuffers", ctypes.c_uint32),
        ("mBuffers", AudioBuffer * 1),  # variable-length flex array
    ]


AudioDeviceIOProc = ctypes.CFUNCTYPE(
    OSStatus,
    AudioObjectID,
    ctypes.c_void_p,
    ctypes.POINTER(AudioBufferList),
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
)


# ── Recorder registry for callback lookup ────────────────────────────

_recorders_lock = threading.Lock()
_recorders: dict = {}  # agg_device_id -> AudioTapRecorder


# ── Availability ─────────────────────────────────────────────────────


def is_available() -> bool:
    """True if Core Audio Process Taps can be used (macOS 14.2+)."""
    try:
        parts = platform.mac_ver()[0].split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        if major < 14 or (major == 14 and minor < 2):
            return False
        from CoreAudio import CATapDescription  # noqa: F401
        return True
    except Exception as e:
        _logger.info("Core Audio Process Taps unavailable: %s", e)
        return False


# ── Module-level IO callback ────────────────────────────────────────


def _io_proc(device, _now, input_p, _input_t, _output_p, _output_t, _client):
    try:
        if not input_p:
            return 0
        with _recorders_lock:
            rec = _recorders.get(int(device))
        if rec is None:
            return 0
        bl = input_p.contents
        n = bl.mNumberBuffers
        if n == 0:
            return 0
        # mBuffers starts after mNumberBuffers (uint32)
        buf_array = ctypes.cast(
            ctypes.addressof(bl) + ctypes.sizeof(ctypes.c_uint32),
            ctypes.POINTER(AudioBuffer),
        )
        chunks = []
        for i in range(n):
            buf = buf_array[i]
            if buf.mData and buf.mDataByteSize > 0:
                nch = buf.mNumberChannels or 1
                raw = ctypes.string_at(buf.mData, buf.mDataByteSize)
                samples = np.frombuffer(raw, dtype=np.float32)
                if nch > 1:
                    # Interleaved L,R,L,R… → mono mean
                    n_frames = len(samples) // nch
                    samples = samples[: n_frames * nch].reshape(-1, nch).mean(axis=1)
                chunks.append(samples.astype(np.float32).copy())
        if not chunks:
            return 0
        mono = np.concatenate(chunks)
        with rec._file_lock:
            if rec._sound_file is not None:
                rec._sound_file.write(mono)
        if rec._on_audio_chunk is not None:
            rec._on_audio_chunk(mono)
    except Exception:
        _logger.exception("Error in audio tap IOProc")
    return 0


_IO_PROC_REF = AudioDeviceIOProc(_io_proc)


# ── Recorder ────────────────────────────────────────────────────────


class AudioTapRecorder:
    """System audio capture via Core Audio Process Taps."""

    def __init__(
        self,
        sample_rate: int = 48000,
        output_path: str = "",
        on_audio_chunk: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self._sample_rate = sample_rate
        self._output_path = output_path
        self._on_audio_chunk = on_audio_chunk
        self._tap_desc = None
        self._tap_id: Optional[int] = None
        self._agg_id: Optional[int] = None
        self._ioproc_id: Optional[ctypes.c_void_p] = None
        self._sound_file: Optional[sf.SoundFile] = None
        self._file_lock = threading.Lock()
        self.error: Optional[str] = None

    def start(self) -> bool:
        try:
            return self._start_inner()
        except Exception as exc:
            self.error = str(exc)
            _logger.exception("Audio tap start failed")
            self._cleanup()
            return False

    def stop(self) -> Optional[str]:
        self._cleanup()
        return self._close_file()

    # ── internals ───────────────────────────────────────────────────

    def _start_inner(self) -> bool:
        import objc
        from Foundation import NSArray, NSMutableDictionary

        try:
            from CoreAudio import CATapDescription
        except ImportError as e:
            self.error = f"CATapDescription import failed: {e}"
            return False

        # 1. Tap description — stereo mixdown of ALL system audio, excluding none
        try:
            tap_desc = CATapDescription.alloc().initStereoGlobalTapButExcludeProcesses_(
                NSArray.array()
            )
        except Exception:
            # Fallback: tap all processes via stereoMixdownOfProcesses with empty list
            tap_desc = CATapDescription.alloc().initStereoMixdownOfProcesses_(
                NSArray.array()
            )
        tap_desc.setName_("Summarizer System Audio Tap")
        tap_desc.setPrivate_(True)
        try:
            tap_desc.setMuteBehavior_(0)  # CATapUnmuted
        except Exception:
            pass
        self._tap_desc = tap_desc

        # 2. Create the process tap
        tap_id_out = AudioObjectID()
        status = _ca.AudioHardwareCreateProcessTap(
            objc.pyobjc_id(tap_desc), ctypes.byref(tap_id_out)
        )
        if status != 0:
            self.error = f"AudioHardwareCreateProcessTap failed: {status}"
            return False
        self._tap_id = tap_id_out.value
        _logger.info("Process tap created (id=%d)", self._tap_id)

        # 3. Tap UUID
        tap_uuid = str(tap_desc.UUID().UUIDString())

        # 4. Aggregate device dict — tap as a sub-device
        agg_uid = f"com.fvoin.summarizer.tap.{uuidlib.uuid4()}"
        agg_dict = NSMutableDictionary.dictionaryWithDictionary_({
            "name": "Summarizer Tap Aggregate",
            "uid": agg_uid,
            "private": 1,
            "stacked": 0,
            "taps": [{"uid": tap_uuid, "drift": 0}],
        })
        agg_id_out = AudioObjectID()
        status = _ca.AudioHardwareCreateAggregateDevice(
            objc.pyobjc_id(agg_dict), ctypes.byref(agg_id_out)
        )
        if status != 0:
            self.error = f"AudioHardwareCreateAggregateDevice failed: {status}"
            return False
        self._agg_id = agg_id_out.value
        _logger.info("Aggregate device created (id=%d)", self._agg_id)

        # 5. Open output WAV
        self._sound_file = sf.SoundFile(
            self._output_path, mode="w",
            samplerate=self._sample_rate, channels=1,
        )

        # 6. Register for IOProc lookup BEFORE starting the device
        with _recorders_lock:
            _recorders[self._agg_id] = self

        # 7. Create IOProc on aggregate device
        ioproc_id_out = ctypes.c_void_p()
        status = _ca.AudioDeviceCreateIOProcID(
            self._agg_id, _IO_PROC_REF, None, ctypes.byref(ioproc_id_out),
        )
        if status != 0:
            self.error = f"AudioDeviceCreateIOProcID failed: {status}"
            return False
        self._ioproc_id = ioproc_id_out

        # 8. Start the aggregate device
        status = _ca.AudioDeviceStart(self._agg_id, self._ioproc_id)
        if status != 0:
            self.error = f"AudioDeviceStart failed: {status}"
            return False

        _logger.info("Audio tap active (tap=%d agg=%d)", self._tap_id, self._agg_id)
        return True

    def _cleanup(self):
        if self._agg_id is not None and self._ioproc_id is not None:
            try:
                _ca.AudioDeviceStop(self._agg_id, self._ioproc_id)
            except Exception:
                pass
            try:
                _ca.AudioDeviceDestroyIOProcID(self._agg_id, self._ioproc_id)
            except Exception:
                pass
        self._ioproc_id = None

        # Unregister BEFORE destroying device
        if self._agg_id is not None:
            with _recorders_lock:
                _recorders.pop(self._agg_id, None)
            try:
                _ca.AudioHardwareDestroyAggregateDevice(self._agg_id)
            except Exception:
                pass
        self._agg_id = None

        if self._tap_id is not None:
            try:
                _ca.AudioHardwareDestroyProcessTap(self._tap_id)
            except Exception:
                pass
        self._tap_id = None
        self._tap_desc = None

    def _close_file(self) -> Optional[str]:
        with self._file_lock:
            if self._sound_file is not None:
                self._sound_file.close()
                self._sound_file = None
        if self._output_path and os.path.exists(self._output_path):
            sz = os.path.getsize(self._output_path)
            _logger.info("Audio tap file: %s (%d bytes)", self._output_path, sz)
            if sz > 1000:
                return self._output_path
            _logger.warning("Audio tap file very small (%d bytes)", sz)
        return None
