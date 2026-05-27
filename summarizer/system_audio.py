"""System audio capture via macOS ScreenCaptureKit (macOS 13+).

Taps desktop audio at the OS level — works with headphones, no BlackHole needed.
Falls back gracefully on older macOS or when the framework is unavailable.
"""

import ctypes
import logging
import os
import platform
import threading
from typing import Callable, Optional

import numpy as np
import soundfile as sf

_logger = logging.getLogger("system_audio")


# ── CoreMedia buffer extraction via ctypes ──────────────────────────

_cm_lib = None


def _load_cm():
    global _cm_lib
    if _cm_lib is not None:
        return _cm_lib
    lib = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreMedia.framework/CoreMedia"
    )
    lib.CMSampleBufferGetDataBuffer.restype = ctypes.c_void_p
    lib.CMSampleBufferGetDataBuffer.argtypes = [ctypes.c_void_p]
    lib.CMBlockBufferGetDataLength.restype = ctypes.c_size_t
    lib.CMBlockBufferGetDataLength.argtypes = [ctypes.c_void_p]
    lib.CMBlockBufferCopyDataBytes.restype = ctypes.c_int32
    lib.CMBlockBufferCopyDataBytes.argtypes = [
        ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p,
    ]
    _cm_lib = lib
    return lib


def _extract_audio(sample_buffer) -> Optional[np.ndarray]:
    """Pull float32 samples out of a CMSampleBuffer."""
    import objc
    cm = _load_cm()
    ptr = objc.pyobjc_id(sample_buffer)
    block = cm.CMSampleBufferGetDataBuffer(ptr)
    if not block:
        return None
    length = cm.CMBlockBufferGetDataLength(block)
    if length == 0:
        return None
    buf = (ctypes.c_char * length)()
    if cm.CMBlockBufferCopyDataBytes(block, 0, length, buf) != 0:
        return None
    return np.frombuffer(bytes(buf), dtype=np.float32)


# ── Availability ────────────────────────────────────────────────────


def is_available() -> bool:
    """True when ScreenCaptureKit audio capture can be used (macOS 13+)."""
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
        if major < 13:
            return False
        import ScreenCaptureKit  # noqa: F401
        return True
    except Exception:
        return False


# ── NSObject handler (defined once to avoid ObjC class name clash) ──

_OutputClass = None


def _get_output_class():
    global _OutputClass
    if _OutputClass is not None:
        return _OutputClass

    from Foundation import NSObject

    class SCKAudioOutput(NSObject):
        def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buf, type_):
            if int(type_) != 1:  # SCStreamOutputTypeAudio
                return
            recorder = getattr(self, "_recorder", None)
            if recorder is None:
                return
            try:
                audio = _extract_audio(sample_buf)
                if audio is None or len(audio) == 0:
                    return
                with recorder._file_lock:
                    if recorder._sound_file is not None:
                        recorder._sound_file.write(audio)
                cb = recorder._on_audio_chunk
                if cb is not None:
                    cb(audio)
            except Exception:
                _logger.exception("Error in system audio callback")

    _OutputClass = SCKAudioOutput
    return SCKAudioOutput


# ── Recorder ────────────────────────────────────────────────────────


class SystemAudioRecorder:
    """Captures desktop/system audio via ScreenCaptureKit."""

    def __init__(
        self,
        sample_rate: int = 44100,
        output_path: str = "",
        on_audio_chunk: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self._sample_rate = sample_rate
        self._output_path = output_path
        self._on_audio_chunk = on_audio_chunk
        self._stream = None
        self._handler = None
        self._sound_file: Optional[sf.SoundFile] = None
        self._file_lock = threading.Lock()
        self.error: Optional[str] = None

    def start(self) -> bool:
        """Start capturing system audio. Returns True on success."""
        try:
            return self._start_inner()
        except Exception as exc:
            self.error = str(exc)
            _logger.exception("System audio start failed")
            self._close_file()
            return False

    def stop(self) -> Optional[str]:
        """Stop capture and close the output file. Returns file path or None."""
        if not self._stream:
            return self._close_file()
        done = threading.Event()

        def _on_stop(err):
            if err:
                _logger.warning("Error stopping system audio: %s", err)
            done.set()

        self._stream.stopCaptureWithCompletionHandler_(_on_stop)
        done.wait(timeout=5)
        self._stream = None
        self._handler = None
        return self._close_file()

    # ── internals ───────────────────────────────────────────────────

    def _start_inner(self) -> bool:
        import ScreenCaptureKit as SCK

        # 1. Discover displays
        ready = threading.Event()
        result = [None, None]

        def _on_content(content, err):
            result[0], result[1] = content, err
            ready.set()

        SCK.SCShareableContent.getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
            False, False, _on_content,
        )
        if not ready.wait(timeout=10):
            self.error = "Timeout getting shareable content"
            _logger.error(self.error)
            return False
        content, err = result
        if err or not content:
            self.error = f"Shareable content error: {err}"
            _logger.error(self.error)
            return False

        displays = content.displays()
        if not displays:
            self.error = "No displays found"
            _logger.error(self.error)
            return False

        # 2. Content filter — entire main display (we only want audio)
        sc_filter = SCK.SCContentFilter.alloc().initWithDisplay_excludingWindows_(
            displays[0], [],
        )

        # 3. Stream configuration
        cfg = SCK.SCStreamConfiguration.alloc().init()
        cfg.setCapturesAudio_(True)
        cfg.setExcludesCurrentProcessAudio_(True)
        cfg.setSampleRate_(float(self._sample_rate))
        cfg.setChannelCount_(1)
        # Minimise video overhead (SCStream requires a video surface)
        cfg.setWidth_(2)
        cfg.setHeight_(2)
        cfg.setShowsCursor_(False)

        # 4. Open output WAV
        self._sound_file = sf.SoundFile(
            self._output_path, mode="w",
            samplerate=self._sample_rate, channels=1,
        )

        # 5. Handler + stream
        OutputCls = _get_output_class()
        self._handler = OutputCls.alloc().init()
        self._handler._recorder = self

        stream = SCK.SCStream.alloc().initWithFilter_configuration_delegate_(
            sc_filter, cfg, None,
        )

        try:
            stream.addStreamOutput_type_sampleHandlerQueue_error_(
                self._handler, 1, None, None,
            )
        except Exception as exc:
            self.error = f"addStreamOutput failed: {exc}"
            _logger.error(self.error)
            self._close_file()
            return False

        # 6. Start capture
        start_ev = threading.Event()
        start_err = [None]

        def _on_start(err):
            start_err[0] = err
            start_ev.set()

        stream.startCaptureWithCompletionHandler_(_on_start)
        if not start_ev.wait(timeout=10):
            self.error = "Timeout starting capture"
            _logger.error(self.error)
            self._close_file()
            return False
        if start_err[0]:
            self.error = f"startCapture error: {start_err[0]}"
            _logger.error(self.error)
            self._close_file()
            return False

        self._stream = stream
        _logger.info("System audio capture started (sr=%d, path=%s)",
                      self._sample_rate, self._output_path)
        return True

    def _close_file(self) -> Optional[str]:
        with self._file_lock:
            if self._sound_file is not None:
                self._sound_file.close()
                self._sound_file = None
        if self._output_path and os.path.exists(self._output_path):
            sz = os.path.getsize(self._output_path)
            _logger.info("System audio file: %s (%d bytes)", self._output_path, sz)
            if sz > 1000:
                return self._output_path
            _logger.warning("System audio file very small (%d bytes)", sz)
        return None
