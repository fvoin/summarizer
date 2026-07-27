"""Tests for silence detection: per-stream detectors + auto-stop wiring.

The false-stop guarantees (recording must NOT auto-stop mid-meeting) are the
priority: threshold may never run away above speech level, and sustained
speech must always register as activity.
"""

import threading
import time

import numpy as np
import pytest

from summarizer.recorder import AudioRecorder, StreamSilenceDetector

SR = 44100
FRAME = 1024  # ~23 ms — typical mic callback block
FRAME_DUR = FRAME / SR


def _frame(level: float, n: int = FRAME) -> np.ndarray:
    """Constant-amplitude frame whose RMS == level."""
    return np.full(n, level, dtype=np.float32)


def feed(det: StreamSilenceDetector, level: float, seconds: float, t0: float,
         n: int = FRAME):
    """Feed `seconds` of frames at RMS `level` starting at t0.

    Returns (activity_times, t_end): synthetic timestamps at which the
    detector reported activity, and the clock after the last frame.
    """
    dur = n / SR
    now = t0
    activity_times = []
    steps = int(round(seconds / dur))
    for _ in range(steps):
        now += dur
        if det.process(_frame(level, n), now):
            activity_times.append(now)
    return activity_times, now


def calibrated(level: float = 0.005, t0: float = 1000.0):
    """Detector that has finished calibration on `level` ambient."""
    det = StreamSilenceDetector("test", SR)
    _, t = feed(det, level, StreamSilenceDetector.CALIBRATION_SECS + 0.1, t0)
    assert det.calibrated
    return det, t


# ── calibration ──────────────────────────────────────────────────────────


def test_digital_zero_stream_clamps_to_min_threshold():
    # System-audio tap emits digital zeros when nothing plays; its threshold
    # must clamp at the minimum, not poison anything else (per-stream state).
    det, _ = calibrated(level=0.0)
    assert det.threshold == pytest.approx(StreamSilenceDetector.MIN_THRESHOLD)


def test_calibration_window_starts_at_first_frame_not_construction():
    det = StreamSilenceDetector("test", SR)
    # First frame arrives 100 s after construction (slow pipeline startup):
    # calibration must still collect a full window from that point.
    _, t = feed(det, 0.005, 1.0, t0=100.0)
    assert not det.calibrated
    feed(det, 0.005, StreamSilenceDetector.CALIBRATION_SECS, t)
    assert det.calibrated


def test_calibration_counts_as_activity():
    # No auto-stop may fire while a stream is still calibrating.
    det = StreamSilenceDetector("test", SR)
    activity, _ = feed(det, 0.0, 1.0, t0=0.0)
    assert activity  # every calibration frame reports activity


# ── debounce: transients must not keep the recording alive ───────────────


def test_single_transient_click_is_not_activity():
    det, t = calibrated(level=0.005)
    # One loud ~23 ms frame (keyboard click) far above threshold.
    assert det.process(_frame(0.3), t + FRAME_DUR) is False


def test_ambient_noise_after_meeting_is_silent():
    det, t = calibrated(level=0.005)
    activity, _ = feed(det, 0.006, 40.0, t)
    assert activity == []


# ── activity: real speech must reset the timer (false-stop guard) ────────


def test_sustained_speech_is_activity():
    det, t = calibrated(level=0.005)
    activity, _ = feed(det, 0.05, 0.5, t)
    assert activity  # became activity within half a second of speech


def test_system_stream_speech_chunk_is_activity_quickly():
    # System audio arrives in larger chunks; a single 0.25 s speech chunk
    # already exceeds the debounce duration and must register immediately.
    det, t = calibrated(level=0.0)
    n = int(0.25 * SR)
    assert det.process(_frame(0.05, n), t + 0.25) is True


def test_threshold_never_exceeds_cap():
    # Runaway adaptation was observed in production (threshold 0.275 —
    # above speech RMS → silent-classified speech → false stop risk).
    det, t = calibrated(level=0.005)
    for _ in range(120):  # 120 cycles of speech/pause ≈ 2 minutes
        _, t = feed(det, 0.08, 0.5, t)
        _, t = feed(det, 0.004, 0.5, t)
        assert det.threshold <= StreamSilenceDetector.MAX_THRESHOLD


def test_no_long_activity_gap_during_ongoing_meeting():
    # THE false-stop guard: while people talk (even with pauses), activity
    # gaps must stay far below any plausible silence_timeout.
    det, t = calibrated(level=0.005)
    last_activity = t
    max_gap = 0.0
    for _ in range(120):
        for level, secs in ((0.08, 0.5), (0.004, 0.5)):
            acts, t = feed(det, level, secs, t)
            for a in acts:
                max_gap = max(max_gap, a - last_activity)
                last_activity = a
    max_gap = max(max_gap, t - last_activity)
    assert max_gap < 2.0


def test_loud_calibration_still_lets_speech_through():
    # Recording started mid-music (RMS 0.2): the threshold cap must keep
    # normal speech (RMS 0.06) registering as activity afterwards.
    det, t = calibrated(level=0.2)
    assert det.threshold <= StreamSilenceDetector.MAX_THRESHOLD
    activity, _ = feed(det, 0.06, 0.5, t)
    assert activity


def test_noise_floor_recovers_after_loud_calibration():
    det, t = calibrated(level=0.2)
    # Music stops; quiet room. Floor must decay quickly (fast-down alpha)
    # so genuine post-meeting silence is eventually recognized as silent.
    _, t = feed(det, 0.004, 10.0, t)
    activity, _ = feed(det, 0.006, 5.0, t)
    assert activity == []


# ── recorder wiring ──────────────────────────────────────────────────────


def _bare_recorder(timeout=0.5):
    r = AudioRecorder(silence_timeout=timeout)
    r._stop_event = threading.Event()
    r._recording = True
    r._last_sound_time = time.time()
    return r


def test_note_audio_updates_last_sound_time_only_on_activity():
    r = _bare_recorder()
    r._calibrating = False
    det = StreamSilenceDetector("mic-2", SR)
    _, t = feed(det, 0.005, StreamSilenceDetector.CALIBRATION_SECS + 0.1, 0.0)
    r._detectors[2] = det

    r._last_sound_time = 0.0
    r._note_audio(2, _frame(0.3), now=t + FRAME_DUR)  # single click
    assert r._last_sound_time == 0.0

    now = t
    for _ in range(10):  # ~0.23 s of speech
        now += FRAME_DUR
        r._note_audio(2, _frame(0.08), now=now)
    assert r._last_sound_time == pytest.approx(now)


def test_streams_have_independent_detectors():
    r = _bare_recorder()
    r._note_audio(2, _frame(0.0), now=1.0)
    r._note_audio(AudioRecorder._SYS_AUDIO_DEV, _frame(0.0), now=1.0)
    assert 2 in r._detectors and AudioRecorder._SYS_AUDIO_DEV in r._detectors
    assert r._detectors[2] is not r._detectors[AudioRecorder._SYS_AUDIO_DEV]


def test_monitor_autostops_after_silence():
    r = _bare_recorder(timeout=0.3)
    r._MONITOR_POLL_SECS = 0.05
    r._calibrating = False
    r._heard_sound = True
    r._last_sound_time = time.time() - 1.0
    stopped = threading.Event()
    r._on_auto_stop = stopped.set
    r._monitor_silence()
    assert stopped.is_set()
    assert r._stop_event.is_set()


class _FakeTap:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_monitor_stops_tap_when_no_callback():
    # A silence auto-stop with no app callback must not leak the system-audio
    # tap (observed in production: taps kept writing GBs for hours).
    r = _bare_recorder(timeout=0.3)
    r._MONITOR_POLL_SECS = 0.05
    r._calibrating = False
    r._heard_sound = True
    r._last_sound_time = time.time() - 1.0
    tap = _FakeTap()
    r._sys_audio = tap
    r._monitor_silence()
    assert tap.stopped


def test_monitor_stops_tap_when_callback_raises():
    r = _bare_recorder(timeout=0.3)
    r._MONITOR_POLL_SECS = 0.05
    r._calibrating = False
    r._heard_sound = True
    r._last_sound_time = time.time() - 1.0
    tap = _FakeTap()
    r._sys_audio = tap

    def boom():
        raise RuntimeError("app handler died")

    r._on_auto_stop = boom
    r._monitor_silence()
    assert tap.stopped


def test_no_autostop_before_first_sound():
    # Waiting-room grace: an armed recording where the meeting hasn't started
    # yet (no sound ever heard) must not auto-stop on the normal timeout.
    r = _bare_recorder(timeout=0.3)
    r._MONITOR_POLL_SECS = 0.05
    r._calibrating = False
    assert not r._heard_sound
    r._last_sound_time = time.time() - 1.0
    stopped = threading.Event()
    r._on_auto_stop = stopped.set
    th = threading.Thread(target=r._monitor_silence, daemon=True)
    th.start()
    time.sleep(0.3)
    assert not stopped.is_set()
    r._stop_event.set()
    th.join(timeout=2)


def test_autostop_after_grace_even_without_sound():
    # A recording that never hears anything (dead mic, meeting never joined)
    # must still stop eventually.
    r = _bare_recorder(timeout=0.3)
    r._MONITOR_POLL_SECS = 0.05
    r._PRE_SOUND_GRACE_SECS = 0.5
    r._calibrating = False
    r._last_sound_time = time.time() - 1.0
    stopped = threading.Event()
    r._on_auto_stop = stopped.set
    r._monitor_silence()
    assert stopped.is_set()


def test_heard_sound_set_only_by_post_calibration_activity():
    r = _bare_recorder()
    now = 0.0
    # Whole calibration window reports activity, but that must not count as
    # "the meeting produced sound".
    for _ in range(int((StreamSilenceDetector.CALIBRATION_SECS + 0.2) / FRAME_DUR)):
        now += FRAME_DUR
        r._note_audio(2, _frame(0.005), now=now)
    assert not r._heard_sound
    for _ in range(int(1.0 / FRAME_DUR)):  # quiet ambient: still no sound
        now += FRAME_DUR
        r._note_audio(2, _frame(0.006), now=now)
    assert not r._heard_sound
    for _ in range(10):  # real speech
        now += FRAME_DUR
        r._note_audio(2, _frame(0.08), now=now)
    assert r._heard_sound


def test_monitor_waits_while_calibrating():
    r = _bare_recorder(timeout=0.3)
    r._MONITOR_POLL_SECS = 0.05
    r._calibrating = True
    r._last_sound_time = time.time() - 100.0
    stopped = threading.Event()
    r._on_auto_stop = stopped.set
    th = threading.Thread(target=r._monitor_silence, daemon=True)
    th.start()
    time.sleep(0.3)
    assert not stopped.is_set()
    r._stop_event.set()
    th.join(timeout=2)


def test_first_calibrated_detector_clears_calibrating_flag():
    r = _bare_recorder()
    assert r._calibrating
    now = 0.0
    for _ in range(int((StreamSilenceDetector.CALIBRATION_SECS + 0.2) / FRAME_DUR)):
        now += FRAME_DUR
        r._note_audio(2, _frame(0.005), now=now)
    assert not r._calibrating
