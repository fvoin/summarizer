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
