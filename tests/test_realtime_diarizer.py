"""RealtimeDiarizer finalize/merge plumbing (no real Whisper model)."""
import numpy as np
import pytest

pytest.importorskip("PyQt6.QtCore")
from PyQt6.QtCore import QCoreApplication
import summarizer.workers as W
from summarizer.diarize import Segment

_app = QCoreApplication.instance() or QCoreApplication([])


class _FakeTr:
    def __init__(self, *a, **k):
        pass

    def _load_model(self):
        pass

    def transcribe_array_segments(self, audio, sr, time_offset=0.0, beam_size=1, language=None):
        marker = float(np.asarray(audio).reshape(-1)[0]) if len(audio) else 0.0
        txt = "my own comment" if marker > 0.5 else "the remote speaker words"
        return [Segment(time_offset, time_offset + 1.0, txt)]


class _FakeRec:
    sample_rate = 100

    def __init__(self, mic, system):
        self._mic, self._sys = mic, system

    def get_stream_rt_audio(self):
        return {"mic": self._mic, "system": self._sys}


def _run(diar):
    diar._stop.set()   # skip the recording loop, go straight to finalize
    diar.run()         # synchronous


def test_realtime_diarizer_merges_two_streams(monkeypatch):
    monkeypatch.setattr(W, "Transcriber", _FakeTr)
    rec = _FakeRec(mic=np.ones(500, dtype=np.float32),
                   system=np.zeros(500, dtype=np.float32))
    diar = W.RealtimeDiarizer("base", rec, locale="en")
    out = {}
    diar.finished.connect(lambda t: out.setdefault("text", t))
    _run(diar)
    assert "Remote: the remote speaker words" in out["text"]
    assert "Me: my own comment" in out["text"]


def test_realtime_diarizer_single_stream_is_plain(monkeypatch):
    # Only system audio -> plain, untagged transcript (no "Remote:"/"Me:").
    monkeypatch.setattr(W, "Transcriber", _FakeTr)
    rec = _FakeRec(mic=None, system=np.zeros(500, dtype=np.float32))
    diar = W.RealtimeDiarizer("base", rec, locale="en")
    out = {}
    diar.finished.connect(lambda t: out.setdefault("text", t))
    _run(diar)
    assert "Remote:" not in out["text"] and "Me:" not in out["text"]
    assert "remote speaker words" in out["text"]
