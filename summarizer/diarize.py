"""Speaker attribution: tag transcript segments as Me (mic) vs Remote (system).

Pure logic module — no audio I/O beyond offset estimation. The system-audio
stream is the authoritative Remote track; mic segments are classified against
it using time-window overlap plus fuzzy text similarity.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


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
