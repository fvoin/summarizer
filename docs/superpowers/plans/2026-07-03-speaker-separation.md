# Speaker Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tag the meeting transcript as `Me` (local mic) vs `Remote` (the other side of the call) by attributing Whisper segments across the two audio streams the app already captures separately.

**Architecture:** The recorder already writes the mic and system-audio streams to separate WAV files before mixing. We stop deleting those sources, transcribe each with timestamps, and merge them in a new pure-logic module `diarize.py`: the system stream is the authoritative Remote track; each mic segment is classified Me / echo / double-talk using time-window overlap plus fuzzy text similarity against the system transcript. Post-recording only; degrades to a plain untagged transcript when only one stream exists.

**Tech Stack:** Python 3, faster-whisper (existing), numpy (existing), soundfile (existing), `difflib` (stdlib), pytest (new dev dependency).

## Global Constraints

- Do NOT add PyTorch, pyannote, or whisperx. Diarization uses only the existing faster-whisper + numpy + stdlib. (Spec: WhisperX rejected.)
- Diarization is **post-recording only**. No real-time tagging. (Spec: Timing.)
- Diarization activates only when BOTH mic and system streams exist; otherwise fall back to the existing single-transcript behavior. (Spec: Graceful degradation.)
- The mixed WAV output of `recorder.stop()` must keep working exactly as today (backward compatible). (Spec: Recorder changes.)
- Speaker labels are localized `Me`/`Remote` (en) and `Я`/`Собеседник` (ru), matching the existing `i18n.locale()` values `"en"`/`"ru"`. (Spec: Output.)
- The upload contract is unchanged — `agent.post_complete` still sends a `transcript` string. (Spec: Output.)

---

### Task 1: Test infrastructure + `Segment` model

**Files:**
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_diarize.py`
- Create: `summarizer/diarize.py`
- Modify: `requirements.txt` (add `pytest`)

**Interfaces:**
- Produces: `summarizer.diarize.Segment` — a dataclass `Segment(start: float, end: float, text: str, speaker: str = "")`. `speaker` is one of `""`, `"me"`, `"remote"`.

- [ ] **Step 1: Add pytest to requirements**

Add a line to `requirements.txt`:

```
pytest
```

- [ ] **Step 2: Write the failing test**

Create `tests/__init__.py` as an empty file, then create `tests/test_diarize.py`:

```python
from summarizer.diarize import Segment


def test_segment_defaults_speaker_empty():
    seg = Segment(start=0.0, end=1.0, text="hello")
    assert seg.start == 0.0
    assert seg.end == 1.0
    assert seg.text == "hello"
    assert seg.speaker == ""


def test_segment_accepts_speaker():
    seg = Segment(start=1.0, end=2.0, text="hi", speaker="me")
    assert seg.speaker == "me"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'summarizer.diarize'`

- [ ] **Step 4: Write minimal implementation**

Create `summarizer/diarize.py`:

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt tests/__init__.py tests/test_diarize.py summarizer/diarize.py
git commit -m "feat: add diarize.Segment model and pytest infra"
```

---

### Task 2: Text normalization + similarity

**Files:**
- Modify: `summarizer/diarize.py`
- Test: `tests/test_diarize.py`

**Interfaces:**
- Produces: `_normalize(text: str) -> str` (lowercase, punctuation stripped, whitespace collapsed) and `_similarity(a: str, b: str) -> float` (0.0–1.0 token ratio; returns 0.0 if either normalizes to empty).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_diarize.py`:

```python
from summarizer.diarize import _normalize, _similarity


def test_normalize_lowercases_and_strips_punctuation():
    assert _normalize("Hello, World!") == "hello world"


def test_normalize_collapses_whitespace():
    assert _normalize("  a   b  ") == "a b"


def test_similarity_identical_is_one():
    assert _similarity("move the deadline", "move the deadline") == 1.0


def test_similarity_empty_is_zero():
    assert _similarity("", "anything") == 0.0
    assert _similarity("anything", "   ") == 0.0


def test_similarity_close_transcription_is_high():
    # echoed remote voice transcribes imperfectly but similar
    score = _similarity("let's move the deadline", "less move the dead line")
    assert score >= 0.6


def test_similarity_different_text_is_low():
    score = _similarity("can you send me the report", "the weather is nice today")
    assert score < 0.6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: FAIL with `ImportError: cannot import name '_normalize'`

- [ ] **Step 3: Write minimal implementation**

Add to `summarizer/diarize.py` (imports at top, functions below the dataclass):

```python
import difflib
import re

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add summarizer/diarize.py tests/test_diarize.py
git commit -m "feat: add text normalization and fuzzy similarity to diarize"
```

---

### Task 3: Merge / classification logic

**Files:**
- Modify: `summarizer/diarize.py`
- Test: `tests/test_diarize.py`

**Interfaces:**
- Produces: `merge(mic_segments: list[Segment], sys_segments: list[Segment], offset: float = 0.0, similarity_threshold: float = 0.6) -> list[Segment]`. Returns segments sorted by start time; every returned segment has `speaker` set to `"me"` or `"remote"`. `offset` is added to each system segment's timestamps to align them onto the mic timeline.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_diarize.py`:

```python
from summarizer.diarize import merge


def test_merge_system_only_all_remote():
    sys_segs = [Segment(0.0, 1.0, "hello from remote")]
    out = merge([], sys_segs)
    assert [s.speaker for s in out] == ["remote"]
    assert out[0].text == "hello from remote"


def test_merge_mic_segment_with_system_silent_is_me():
    mic = [Segment(5.0, 6.0, "my local comment")]
    sys = [Segment(0.0, 1.0, "earlier remote")]  # no time overlap with mic
    out = merge(mic, sys)
    me = [s for s in out if s.speaker == "me"]
    assert len(me) == 1
    assert me[0].text == "my local comment"


def test_merge_echo_is_dropped():
    # remote voice leaks into mic during the same window with similar text
    mic = [Segment(0.0, 1.0, "less move the dead line")]
    sys = [Segment(0.0, 1.0, "let's move the deadline")]
    out = merge(mic, sys)
    # only the authoritative remote segment survives; the echo mic seg is dropped
    assert [s.speaker for s in out] == ["remote"]


def test_merge_double_talk_kept_as_me():
    # both talk in the same window but say different things
    mic = [Segment(0.0, 1.0, "wait I disagree with that")]
    sys = [Segment(0.0, 1.0, "the report is due friday")]
    out = merge(mic, sys)
    speakers = sorted(s.speaker for s in out)
    assert speakers == ["me", "remote"]


def test_merge_sorted_by_start_time():
    mic = [Segment(10.0, 11.0, "later local")]
    sys = [Segment(0.0, 1.0, "early remote")]
    out = merge(mic, sys)
    assert out[0].text == "early remote"
    assert out[1].text == "later local"


def test_merge_applies_offset_to_system():
    # system clock lags mic by 2s; with offset the segments overlap -> echo dropped
    mic = [Segment(2.0, 3.0, "hello there friend")]
    sys = [Segment(0.0, 1.0, "hello there friend")]
    out = merge(mic, sys, offset=2.0)
    assert [s.speaker for s in out] == ["remote"]
    assert out[0].start == 2.0  # remote seg shifted onto mic timeline
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: FAIL with `ImportError: cannot import name 'merge'`

- [ ] **Step 3: Write minimal implementation**

Add to `summarizer/diarize.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add summarizer/diarize.py tests/test_diarize.py
git commit -m "feat: add Me/Remote merge classification to diarize"
```

---

### Task 4: Transcript formatting

**Files:**
- Modify: `summarizer/diarize.py`
- Test: `tests/test_diarize.py`

**Interfaces:**
- Produces: `format_transcript(segments: list[Segment], locale: str = "en") -> str`. Emits one line per segment: `"<Label>: <text>"`, where the label is localized (`me`→`Me`/`Я`, `remote`→`Remote`/`Собеседник`). Blank/whitespace-only segment text is skipped.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_diarize.py`:

```python
from summarizer.diarize import format_transcript


def test_format_transcript_en():
    segs = [
        Segment(0.0, 1.0, "hello", speaker="remote"),
        Segment(1.0, 2.0, "hi back", speaker="me"),
    ]
    out = format_transcript(segs, locale="en")
    assert out == "Remote: hello\nMe: hi back"


def test_format_transcript_ru():
    segs = [Segment(0.0, 1.0, "привет", speaker="remote")]
    out = format_transcript(segs, locale="ru")
    assert out == "Собеседник: привет"


def test_format_transcript_skips_blank_text():
    segs = [
        Segment(0.0, 1.0, "   ", speaker="me"),
        Segment(1.0, 2.0, "real", speaker="remote"),
    ]
    out = format_transcript(segs, locale="en")
    assert out == "Remote: real"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: FAIL with `ImportError: cannot import name 'format_transcript'`

- [ ] **Step 3: Write minimal implementation**

Add to `summarizer/diarize.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add summarizer/diarize.py tests/test_diarize.py
git commit -m "feat: add localized transcript formatting to diarize"
```

---

### Task 5: Stream offset estimation

**Files:**
- Modify: `summarizer/diarize.py`
- Test: `tests/test_diarize.py`

**Interfaces:**
- Produces:
  - `_offset_from_envelopes(env_mic, env_sys, hz: float, max_offset_sec: float = 5.0) -> float` — pure numpy cross-correlation; returns seconds to add to system timestamps to align onto the mic timeline, clamped to ±`max_offset_sec`.
  - `estimate_offset(mic_path: str, sys_path: str, max_offset_sec: float = 5.0) -> float` — reads both WAVs via soundfile, builds 100 Hz energy envelopes, calls `_offset_from_envelopes`. Returns `0.0` on any read error.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_diarize.py`:

```python
import numpy as np
from summarizer.diarize import _offset_from_envelopes


def test_offset_zero_when_aligned():
    rng = np.arange(100, dtype=float)
    env = np.sin(rng / 3.0) ** 2
    off = _offset_from_envelopes(env, env, hz=100.0)
    assert abs(off) < 0.02


def test_offset_detects_positive_lag():
    # sys envelope is the mic envelope delayed by 50 samples (=0.5s at 100Hz).
    rng = np.arange(300, dtype=float)
    base = (np.sin(rng / 5.0) ** 2)
    mic_env = base.copy()
    sys_env = np.concatenate([np.zeros(50), base])[:300]
    off = _offset_from_envelopes(mic_env, sys_env, hz=100.0)
    # to align sys onto mic we must ADD +0.5s to sys timestamps
    assert abs(off - 0.5) < 0.05


def test_offset_clamped():
    rng = np.arange(100, dtype=float)
    mic_env = np.sin(rng / 3.0) ** 2
    sys_env = np.zeros(100)  # no correlation
    off = _offset_from_envelopes(mic_env, sys_env, hz=100.0, max_offset_sec=1.0)
    assert -1.0 <= off <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: FAIL with `ImportError: cannot import name '_offset_from_envelopes'`

- [ ] **Step 3: Write minimal implementation**

Add to `summarizer/diarize.py` (add `import numpy as np` at top with the other imports):

```python
def _offset_from_envelopes(env_mic, env_sys, hz: float, max_offset_sec: float = 5.0) -> float:
    import numpy as np

    a = np.asarray(env_mic, dtype=float)
    b = np.asarray(env_sys, dtype=float)
    if a.size == 0 or b.size == 0:
        return 0.0
    a = a - a.mean()
    b = b - b.mean()
    if not np.any(a) or not np.any(b):
        return 0.0
    corr = np.correlate(a, b, mode="full")
    lag = int(np.argmax(corr)) - (len(b) - 1)  # samples to shift sys forward
    offset = lag / hz
    return max(-max_offset_sec, min(max_offset_sec, offset))


def _envelope(samples, sr: int, target_hz: float = 100.0):
    import numpy as np

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_diarize.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add summarizer/diarize.py tests/test_diarize.py
git commit -m "feat: add stream offset estimation to diarize"
```

---

### Task 6: Recorder exposes and retains source files

**Files:**
- Modify: `summarizer/recorder.py` (`__init__` ~line 29-65; `start` source-file bookkeeping; `stop` finally-cleanup ~lines 488-493)
- Test: `tests/test_recorder_sources.py`

**Interfaces:**
- Consumes: nothing new.
- Produces on `AudioRecorder`:
  - `self._mic_files: list[str]` and `self._sys_file: str | None`, populated during `start()`.
  - `get_source_files() -> dict` returning `{"mic": list[str], "system": str | None}` (only paths that currently exist on disk).
  - `cleanup_sources() -> None` deletes the retained source files.
  - `stop()` no longer deletes the mic/system source files in its `finally` block; it deletes only intermediate files that are neither a tracked mic file nor the system file. Callers MUST call `cleanup_sources()` after consuming the sources.

- [ ] **Step 1: Write the failing test**

Create `tests/test_recorder_sources.py`:

```python
import os
from summarizer.recorder import AudioRecorder


def test_get_source_files_reports_existing(tmp_path):
    rec = AudioRecorder()
    mic = tmp_path / "summarizer_rec_x_1.wav"
    sysf = tmp_path / "summarizer_sys_x.wav"
    mic.write_bytes(b"RIFF0000")
    sysf.write_bytes(b"RIFF0000")
    rec._mic_files = [str(mic)]
    rec._sys_file = str(sysf)
    out = rec.get_source_files()
    assert out["mic"] == [str(mic)]
    assert out["system"] == str(sysf)


def test_get_source_files_omits_missing(tmp_path):
    rec = AudioRecorder()
    rec._mic_files = [str(tmp_path / "missing.wav")]
    rec._sys_file = None
    out = rec.get_source_files()
    assert out["mic"] == []
    assert out["system"] is None


def test_cleanup_sources_deletes_files(tmp_path):
    rec = AudioRecorder()
    mic = tmp_path / "summarizer_rec_x_1.wav"
    mic.write_bytes(b"data")
    rec._mic_files = [str(mic)]
    rec._sys_file = None
    rec.cleanup_sources()
    assert not os.path.exists(str(mic))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recorder_sources.py -v`
Expected: FAIL with `AttributeError: 'AudioRecorder' object has no attribute 'get_source_files'` (or `_mic_files` unset in `__init__`)

- [ ] **Step 3: Initialize the new attributes in `__init__`**

In `summarizer/recorder.py`, inside `AudioRecorder.__init__` (near the other instance attributes around line 52), add:

```python
        self._mic_files = []
        self._sys_file = None
```

- [ ] **Step 4: Populate the attributes in `start()`**

In `start()`, the system-audio temp path is appended to `self._temp_files` when the tap/ScreenCaptureKit starts (search for `self._temp_files.append(sys_tmp)`). Immediately after each such append, also record it as the system source:

```python
                    self._sys_file = sys_tmp
```

Still in `start()`, the mic recording loop creates one temp file per device (search for `tmp = os.path.join(tmp_dir, f"summarizer_rec_{ts}_{idx}.wav")`). After `self._temp_files.append(tmp)` in that loop, add:

```python
            self._mic_files.append(tmp)
```

Also reset both at the top of `start()` next to `self._temp_files = []`:

```python
        self._mic_files = []
        self._sys_file = None
```

- [ ] **Step 5: Add the accessor and cleanup methods**

Add these methods to `AudioRecorder` (e.g. right after `stop()`):

```python
    def get_source_files(self) -> dict:
        """Return the un-mixed per-stream source files that still exist.

        {"mic": [paths...], "system": path | None}. Used for post-recording
        speaker separation. Call cleanup_sources() when done with them.
        """
        mic = [f for f in self._mic_files if f and os.path.exists(f)]
        system = self._sys_file if (self._sys_file and os.path.exists(self._sys_file)) else None
        return {"mic": mic, "system": system}

    def cleanup_sources(self) -> None:
        """Delete the retained per-stream source files."""
        for f in list(self._mic_files):
            try:
                os.unlink(f)
            except OSError:
                pass
        if self._sys_file:
            try:
                os.unlink(self._sys_file)
            except OSError:
                pass
```

- [ ] **Step 6: Stop `stop()` from deleting the sources**

In `stop()`, replace the `finally` cleanup block (currently deletes every entry in `self._temp_files`):

```python
        finally:
            for f in self._temp_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass
```

with a version that preserves the tracked mic/system sources:

```python
        finally:
            sources = set(self._mic_files)
            if self._sys_file:
                sources.add(self._sys_file)
            for f in self._temp_files:
                if f in sources:
                    continue  # retained for diarization; freed by cleanup_sources()
                try:
                    os.unlink(f)
                except OSError:
                    pass
```

- [ ] **Step 7: Run test to verify it passes**

Run: `python -m pytest tests/test_recorder_sources.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Commit**

```bash
git add summarizer/recorder.py tests/test_recorder_sources.py
git commit -m "feat: retain and expose per-stream source files in recorder"
```

---

### Task 7: Transcriber returns timestamped segments

**Files:**
- Modify: `summarizer/transcriber.py` (add method to `Transcriber`, ~after line 132)
- Test: manual (requires the Whisper model; not unit-tested)

**Interfaces:**
- Consumes: `summarizer.diarize.Segment`.
- Produces: `Transcriber.transcribe_segments(audio_path: str, language: str | None = None) -> list[Segment]` — one `Segment(start, end, text)` per Whisper segment, `speaker` left `""`. Returns `[]` if the file is missing or empty.

- [ ] **Step 1: Implement `transcribe_segments`**

Add to the `Transcriber` class in `summarizer/transcriber.py` (mirror the existing `transcribe()` conversion/VAD handling):

```python
    def transcribe_segments(self, audio_path: str, language=None):
        """Transcribe returning per-segment timestamps for speaker separation."""
        from .diarize import Segment

        if not Path(audio_path).exists() or Path(audio_path).stat().st_size < 1000:
            return []

        self._load_model()
        converted = self._convert_audio(audio_path)
        cleanup = converted != audio_path
        try:
            try:
                segments, _ = self._model.transcribe(
                    converted, language=language, beam_size=5,
                    word_timestamps=False, vad_filter=True,
                )
            except Exception:
                segments, _ = self._model.transcribe(
                    converted, language=language, beam_size=5, word_timestamps=False,
                )
            return [
                Segment(start=float(s.start), end=float(s.end), text=s.text.strip())
                for s in segments
            ]
        finally:
            if cleanup:
                Path(converted).unlink(missing_ok=True)
```

- [ ] **Step 2: Manual smoke test**

With the venv active, run this against any existing WAV (e.g. a temp recording under `/tmp`):

```bash
source .venv/bin/activate
python -c "from summarizer.transcriber import Transcriber; import sys; \
segs = Transcriber('base').transcribe_segments(sys.argv[1]); \
print(len(segs), 'segments'); print(segs[:3])" /path/to/some.wav
```

Expected: prints a segment count > 0 and the first few `Segment(start=..., end=..., text='...')` for a file with speech; `0 segments` for silence/missing.

- [ ] **Step 3: Commit**

```bash
git add summarizer/transcriber.py
git commit -m "feat: add transcribe_segments with timestamps to Transcriber"
```

---

### Task 8: `DiarizeTranscribeWorker` + wire into the full app

**Context — the real flow:** The full app does NOT use `TranscribeWorker` for the recording flow. On stop, `_finish_recording_with_rt()` (app.py ~3604) calls `self._recorder.stop()`, then builds the final transcript from the real-time text plus a small delta, and hands it to `_use_rt_transcript()` (~3677), which saves it, persists the meeting, uploads for agent recordings, and either summarizes or displays it. Our integration: right after `stop()`, if BOTH source streams exist, re-transcribe them separately, tag Me/Remote, and feed the tagged transcript into the existing `_use_rt_transcript()` — bypassing the RT/delta path. Otherwise the existing path runs unchanged (graceful degradation).

**Files:**
- Modify: `summarizer/app.py` — add `DiarizeTranscribeWorker` near `TranscribeWorker` (~line 289); edit `_finish_recording_with_rt` (~3615–3637); add two handler methods.
- Test: manual (GUI + audio)

**Interfaces:**
- Consumes: `AudioRecorder.get_source_files()`, `AudioRecorder.cleanup_sources()`, `Transcriber.transcribe_segments()`, `summarizer.diarize.merge/format_transcript/estimate_offset`, `summarizer.i18n.locale()`, existing `MainWindow._use_rt_transcript()` and `MainWindow._process_audio()`.
- Produces: `DiarizeTranscribeWorker(QThread)` with `__init__(self, whisper_model: str, mic_path: str, sys_path: str, parent=None)`, signal `finished = pyqtSignal(str)` (tagged transcript), signal `error = pyqtSignal(str)` (emitted when the tagged transcript is empty or an exception occurs, so the caller falls back).

- [ ] **Step 1: Implement the worker**

Add to `summarizer/app.py` near `TranscribeWorker` (the file already imports `t`/`i18n`; `Transcriber` is already imported):

```python
class DiarizeTranscribeWorker(QThread):
    """Post-recording Me/Remote speaker separation from the two source streams."""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, whisper_model: str, mic_path: str, sys_path: str, parent=None):
        super().__init__(parent)
        self._model = whisper_model
        self._mic_path = mic_path
        self._sys_path = sys_path

    def run(self):
        try:
            from . import diarize
            from .i18n import locale

            tr = Transcriber(self._model)
            mic_segs = tr.transcribe_segments(self._mic_path)
            sys_segs = tr.transcribe_segments(self._sys_path)
            offset = diarize.estimate_offset(self._mic_path, self._sys_path)
            merged = diarize.merge(mic_segs, sys_segs, offset=offset)
            text = diarize.format_transcript(merged, locale=locale())
            if not text.strip():
                self.error.emit("empty")
                return
            self.finished.emit(text)
        except Exception as e:
            _logger.exception("DiarizeTranscribeWorker failed")
            self.error.emit(str(e))
```

- [ ] **Step 2: Capture sources before the recorder is cleared**

In `_finish_recording_with_rt`, the current lines are:

```python
        audio_file = self._recorder.stop()
        self._recorder = None
        self._reset_record_btn()
```

Replace with (capture sources + keep a recorder reference for later cleanup):

```python
        audio_file = self._recorder.stop()
        sources = self._recorder.get_source_files()
        self._diar_recorder = self._recorder  # kept only to cleanup_sources() later
        self._recorder = None
        self._reset_record_btn()
```

- [ ] **Step 3: Add the diarization branch**

Still in `_finish_recording_with_rt`, the "Save audio if configured" block ends just before:

```python
        self._pending_audio_path = audio_file
        self._pending_duration = duration
```

Immediately BEFORE those two lines, insert the branch (note `whisper_model` is already computed earlier in this method, ~line 3610):

```python
        # Speaker separation: when both mic and system streams were captured,
        # re-transcribe them separately and tag Me/Remote (post-recording).
        mic_srcs = sources.get("mic") or []
        sys_src = sources.get("system")
        if mic_srcs and sys_src:
            self._pending_audio_path = audio_file
            self._pending_duration = duration
            self._set_status(f"{status_prefix}{t('status_processing')}", "busy")
            self.progress.setVisible(True)
            self.record_btn.setEnabled(False)
            worker = DiarizeTranscribeWorker(whisper_model, mic_srcs[0], sys_src)
            worker.finished.connect(self._on_diarized)
            worker.error.connect(self._on_diarize_failed)
            self._track_worker(worker)
            worker.start()
            return
```

- [ ] **Step 4: Add the handler methods**

Add these two methods to `MainWindow` (e.g. right after `_use_rt_transcript`):

```python
    def _on_diarized(self, transcript: str):
        """Speaker-tagged transcript ready — route through the normal sink."""
        rec = getattr(self, "_diar_recorder", None)
        if rec:
            rec.cleanup_sources()
            self._diar_recorder = None
        self._use_rt_transcript(transcript)

    def _on_diarize_failed(self, _err: str):
        """Diarization produced nothing usable — fall back to plain transcription."""
        rec = getattr(self, "_diar_recorder", None)
        if rec:
            rec.cleanup_sources()
            self._diar_recorder = None
        audio = getattr(self, "_pending_audio_path", None)
        duration = getattr(self, "_pending_duration", None)
        self._pending_audio_path = None
        self._pending_duration = None
        if audio:
            self._process_audio(audio, duration_seconds=duration)
        else:
            self._set_busy(False)
            self._on_error(t("error_no_speech"))
```

- [ ] **Step 5: Manual end-to-end verification**

```bash
source .venv/bin/activate && python run.py
```

Record a short clip while playing audio through the system (so the tap captures a "remote" voice) and speaking into the mic. Stop. Verify:
- The resulting transcript shows `Me:` / `Remote:` prefixes (or `Я:`/`Собеседник:` under a Russian system locale).
- A mic-only recording (no system audio playing) still produces a normal untagged transcript via the existing RT path.
- No leftover `summarizer_rec_*` / `summarizer_sys_*` files remain in the temp dir afterward (`ls "$TMPDIR"/summarizer_*`).

- [ ] **Step 6: Commit**

```bash
git add summarizer/app.py
git commit -m "feat: speaker-separated transcription in full app"
```

---

## Self-Review Notes

- **Spec coverage:** recorder source retention (Task 6), timestamped transcription (Task 7), merge/classify/format/offset (Tasks 2–5), graceful degradation (Task 8 fallback), localized labels (Task 4), unchanged upload contract (Task 8 emits a plain string), no-torch constraint (only stdlib+numpy+soundfile used). Lite client is a separate plan.
- **Bundling note (for the person running `build.sh`):** `summarizer/diarize.py` is imported lazily inside the worker; PyInstaller collects `summarizer.*` already, but confirm `diarize` is present in the built app during the lite/full build pass.
- **Threshold 0.6** is the spec's tunable starting value; revisit after Task 8 manual QA on real recordings.
