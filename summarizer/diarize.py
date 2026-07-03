"""Speaker attribution: tag transcript segments as Me (mic) vs Remote (system).

Pure logic module — no audio I/O beyond offset estimation. The system-audio
stream is the authoritative Remote track; mic segments are classified against
it using time-window overlap plus fuzzy text similarity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str = ""  # "" | "me" | "remote"
