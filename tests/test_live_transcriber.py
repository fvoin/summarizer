import numpy as np
import pytest

pytest.importorskip("PyQt6.QtCore")
from PyQt6.QtWidgets import QApplication
from summarizer.workers import LiveTranscriber

_app = QApplication.instance() or QApplication([])


class _FakeWorker:
    def __init__(self):
        self.pushed = []

    def push_audio(self, audio, sr):
        self.pushed.append((len(audio), sr))


class _FakeRecorder:
    sample_rate = 100

    def __init__(self, audio):
        self._audio = audio

    def get_all_rt_audio(self):
        return self._audio

    def is_recording(self):
        return True


def test_on_chunk_advances_committed_and_emits_text():
    lt = LiveTranscriber()
    seen = []
    lt.text_appended.connect(seen.append)
    lt._on_chunk("hello", 50)
    lt._on_chunk("", 25)          # empty text: advance counter, emit nothing
    assert lt._committed_len == 75
    assert seen == ["hello"]


def test_tick_pushes_only_when_delta_exceeds_min():
    lt = LiveTranscriber()
    lt._worker = _FakeWorker()
    lt._sample_rate = 100          # min delta = 3 s = 300 samples
    lt._committed_len = 0
    # 250 samples of new audio -> below threshold, no push
    lt._recorder = _FakeRecorder(np.zeros(250, dtype=np.float32))
    lt._on_tick()
    assert lt._worker.pushed == []
    # 400 samples -> above threshold, one push of the full delta
    lt._recorder = _FakeRecorder(np.zeros(400, dtype=np.float32))
    lt._on_tick()
    assert lt._worker.pushed == [(400, 100)]
