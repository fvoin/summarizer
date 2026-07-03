"""Speaker attribution: tag transcript segments as Me (mic) vs Remote (system).

Pure logic module — no audio I/O beyond offset estimation. The system-audio
stream is the authoritative Remote track; mic segments are classified against
it using time-window overlap plus fuzzy text similarity.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

import numpy as np


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str = ""  # "" | "me" | "remote"


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize(text: str) -> str:
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def _overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def _overlapping_sys_text(
    win_start: float, win_end: float, sys_segments: list, offset: float
) -> str:
    parts = []
    for s in sys_segments:
        if _overlaps(win_start, win_end, s.start + offset, s.end + offset):
            parts.append(s.text)
    return " ".join(parts)


def merge(
    mic_segments: list,
    sys_segments: list,
    offset: float = 0.0,
    similarity_threshold: float = 0.6,
) -> list:
    result = []

    # System stream is the authoritative Remote track (shifted onto mic timeline).
    for s in sys_segments:
        result.append(
            Segment(s.start + offset, s.end + offset, s.text, speaker="remote")
        )

    # Classify each mic segment.
    for m in mic_segments:
        sys_text = _overlapping_sys_text(m.start, m.end, sys_segments, offset)
        if not sys_text:
            # Remote silent in this window -> definitely local.
            result.append(Segment(m.start, m.end, m.text, speaker="me"))
            continue
        if _similarity(m.text, sys_text) >= similarity_threshold:
            # Echo of the remote voice -> already covered by the Remote track.
            continue
        # System active but text differs -> double-talk, local spoke over remote.
        result.append(Segment(m.start, m.end, m.text, speaker="me"))

    result.sort(key=lambda seg: seg.start)
    return result


_LABELS = {
    "me": {"en": "Me", "ru": "Я"},
    "remote": {"en": "Remote", "ru": "Собеседник"},
}


def format_transcript(segments: list, locale: str = "en") -> str:
    lines = []
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        label = _LABELS.get(seg.speaker, {}).get(locale)
        if label is None:
            label = seg.speaker or "?"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


def _offset_from_envelopes(env_mic, env_sys, hz: float, max_offset_sec: float = 5.0) -> float:
    a = np.asarray(env_mic, dtype=float)
    b = np.asarray(env_sys, dtype=float)
    if a.size == 0 or b.size == 0:
        return 0.0
    a = a - a.mean()
    b = b - b.mean()
    if not np.any(a) or not np.any(b):
        return 0.0
    corr = np.correlate(a, b, mode="full")
    lag = (len(b) - 1) - int(np.argmax(corr))  # samples to shift sys forward
    offset = lag / hz
    return max(-max_offset_sec, min(max_offset_sec, offset))


def _envelope(samples, sr: int, target_hz: float = 100.0):
    x = np.asarray(samples, dtype=float)
    if x.ndim > 1:
        x = x.mean(axis=1)  # down-mix to mono
    win = max(1, int(sr / target_hz))
    n = (len(x) // win) * win
    if n == 0:
        return np.zeros(0)
    frames = x[:n].reshape(-1, win)
    return np.sqrt(np.mean(frames ** 2, axis=1))


def estimate_offset(mic_path: str, sys_path: str, max_offset_sec: float = 5.0) -> float:
    try:
        import soundfile as sf

        mic, sr_m = sf.read(mic_path)
        sys_, sr_s = sf.read(sys_path)
        env_m = _envelope(mic, sr_m, target_hz=100.0)
        env_s = _envelope(sys_, sr_s, target_hz=100.0)
        return _offset_from_envelopes(env_m, env_s, hz=100.0, max_offset_sec=max_offset_sec)
    except Exception:
        return 0.0
