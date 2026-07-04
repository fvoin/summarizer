"""Speaker attribution: tag transcript segments as Me (mic) vs Remote (system).

Pure logic module — no audio I/O beyond offset estimation. The system-audio
stream is the authoritative Remote track; mic segments are classified against
it using time-window overlap plus fuzzy text similarity.
"""

from __future__ import annotations

import difflib
import re
import statistics
from dataclasses import dataclass

import numpy as np


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str = ""  # "" | "me" | "remote"
    energy: float = 0.0  # RMS amplitude of the segment (mic segments only)


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


def _overlap_and_max_sim(mic_seg, sys_segments: list, offset: float):
    """(does the mic segment overlap any active system segment, best per-segment
    text similarity to those overlapping segments). Comparing against each system
    segment individually — rather than their concatenation — avoids diluting an
    echo that matches one system utterance when several overlap the window."""
    overlaps = False
    best = 0.0
    for s in sys_segments:
        if _overlaps(mic_seg.start, mic_seg.end, s.start + offset, s.end + offset):
            overlaps = True
            best = max(best, _similarity(mic_seg.text, s.text))
    return overlaps, best


def merge(
    mic_segments: list,
    sys_segments: list,
    offset: float = 0.0,
    similarity_threshold: float = 0.6,
    energy_ratio: float = 0.4,
) -> list:
    result = []

    # System stream is the authoritative Remote track (shifted onto mic timeline).
    for s in sys_segments:
        result.append(
            Segment(s.start + offset, s.end + offset, s.text, speaker="remote")
        )

    # Energy baseline: the RMS of confident-local mic speech (windows where the
    # remote is silent). Remote voice bleeding into the mic through speakers is
    # much quieter than the local speaker, so segments far below this baseline
    # are echo even when their (garbled) transcription doesn't match the system
    # text. Disabled (baseline 0) when no energies were annotated.
    local_energies = [
        m.energy
        for m in mic_segments
        if m.energy > 0.0
        and not _overlapping_sys_text(m.start, m.end, sys_segments, offset)
    ]
    baseline = statistics.median(local_energies) if local_energies else 0.0

    # Classify each mic segment.
    for m in mic_segments:
        overlaps, max_sim = _overlap_and_max_sim(m, sys_segments, offset)
        if not overlaps:
            # Remote silent in this window -> definitely local.
            result.append(Segment(m.start, m.end, m.text, speaker="me", energy=m.energy))
            continue
        if max_sim >= similarity_threshold:
            # Echo of a remote utterance -> already covered by the Remote track.
            continue
        # System active but text differs. If this mic segment is much quieter
        # than local speech, it's remote echo that transcribed differently -> drop.
        if baseline > 0.0 and m.energy > 0.0 and m.energy < energy_ratio * baseline:
            continue
        # Otherwise treat as genuine double-talk: local spoke over remote.
        result.append(Segment(m.start, m.end, m.text, speaker="me", energy=m.energy))

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


def _offset_from_envelopes(env_mic, env_sys, hz: float, max_offset_sec: float = 1.5) -> float:
    a = np.asarray(env_mic, dtype=float)
    b = np.asarray(env_sys, dtype=float)
    if a.size == 0 or b.size == 0:
        return 0.0
    a = a - a.mean()
    b = b - b.mean()
    if not np.any(a) or not np.any(b):
        return 0.0
    corr = np.correlate(a, b, mode="full")
    # The two streams start near-simultaneously, so the true offset is small.
    # Search only within ±max_offset_sec for the peak; taking the GLOBAL argmax
    # lets a spurious far peak win on repetitive speech and pin the result to
    # the clamp boundary (observed: garbage 5.0 s that wrecks alignment).
    center = len(b) - 1  # index of lag 0
    max_shift = max(1, int(max_offset_sec * hz))
    lo = max(0, center - max_shift)
    hi = min(len(corr), center + max_shift + 1)
    lag = (lo + int(np.argmax(corr[lo:hi]))) - center  # samples to shift sys onto mic
    return lag / hz


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


def rms_window(audio, sr: int, start: float, end: float) -> float:
    """RMS amplitude of the audio between start and end seconds (mono or stereo)."""
    a = np.asarray(audio, dtype=np.float64)
    if a.ndim > 1:
        a = a.mean(axis=1)  # down-mix to mono
    i0 = max(0, int(start * sr))
    i1 = min(len(a), int(end * sr))
    if i1 <= i0:
        return 0.0
    seg = a[i0:i1]
    return float(np.sqrt(np.mean(seg ** 2)))


def annotate_energies(mic_path: str, segments: list) -> list:
    """Best-effort: set .energy (RMS) on each mic segment from the mic WAV.

    On any read error the segments keep energy 0.0, which disables energy
    gating in merge() (falls back to text-only behavior).
    """
    try:
        import soundfile as sf

        audio, sr = sf.read(mic_path)
        for s in segments:
            s.energy = rms_window(audio, sr, s.start, s.end)
    except Exception:
        pass
    return segments


def estimate_offset(mic_path: str, sys_path: str, max_offset_sec: float = 1.5) -> float:
    try:
        import soundfile as sf

        mic, sr_m = sf.read(mic_path)
        sys_, sr_s = sf.read(sys_path)
        env_m = _envelope(mic, sr_m, target_hz=100.0)
        env_s = _envelope(sys_, sr_s, target_hz=100.0)
        return _offset_from_envelopes(env_m, env_s, hz=100.0, max_offset_sec=max_offset_sec)
    except Exception:
        return 0.0
