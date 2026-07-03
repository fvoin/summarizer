# Lite Transcript Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Depends on:** `2026-07-03-speaker-separation.md` (the `diarize` module, `Transcriber.transcribe_segments`, recorder source files, and `DiarizeTranscribeWorker` must exist first).

**Goal:** Ship a second app bundle ("Summarizer Transcriber") that records, shows a live transcript while recording, transcribes locally with Me/Remote tagging on stop, uploads the transcript for agent-scheduled meetings, and shows it with a Copy button for manual recordings — with no summarization, history, grouping, context, or LLM settings.

**Architecture:** One codebase, two bundles (Option A). The transcription `QThread` workers move from `app.py` into a neutral `summarizer/workers.py` that never imports `summarizer.summarizer` or `summarizer.db`. A shared `LiveTranscriber` controller (also in `workers.py`) encapsulates the real-time-transcript orchestration so the lite window reuses it instead of duplicating `MainWindow`'s logic. A new `app_lite.py` (`LiteWindow` + `LiteSetupWizard`) and `run_lite.py` entry point reuse `recorder`, `workers`, `diarize`, `agent`, `config`, `i18n`, `theme`, and a shared `widgets.py`. `build.sh` gains a lite target.

**Tech Stack:** PyQt6 (existing), plus the existing `recorder`/`transcriber`/`diarize`/`agent`/`config`/`i18n`/`theme` modules.

## Global Constraints

- `app_lite.py`, `run_lite.py`, `workers.py`, and `widgets.py` MUST NOT import `summarizer.summarizer` or `summarizer.db` (keeps the LLM SDKs and history layer out of the lite bundle). (Spec: architecture, exclusions.)
- `MainWindow`'s existing recording flow in `app.py` MUST NOT be modified by this plan — the shared `LiveTranscriber` controller is used only by the lite window for now. (User decision: don't destabilize the shipping full app.)
- Manual recordings never upload — they display + copy only. Only agent-armed recordings upload, via the existing `agent.post_complete` / `PostCompleteWorker`. (User decision.)
- Lite reuses the same `~/.summarizer/config.json`; it reads only `agent_url`, `agent_token`, `agent_enabled`, `whisper_model`, `input_device`. No config schema change. (Spec: config.)
- Whisper model is hard-coded to the app default in lite setup (`config.DEFAULT_CONFIG["whisper_model"]`); no model picker in the lite wizard. (Spec: lite setup.)
- Speaker tagging reuses `diarize` exactly as the full app does. (Spec: shared.)

---

### Task 1: Extract transcription workers into `workers.py`

**Files:**
- Create: `summarizer/workers.py`
- Modify: `summarizer/app.py` (remove the four worker classes; import them from `workers`)
- Test: `tests/test_workers_isolation.py`

**Interfaces:**
- Produces `summarizer/workers.py` exporting `TranscribeWorker`, `RealtimeTranscribeWorker`, `_DeltaTranscribeWorker`, `DiarizeTranscribeWorker` — moved verbatim from `app.py` (signatures unchanged; `DiarizeTranscribeWorker(whisper_model, mic_path, sys_path)`).
- `app.py` re-imports them so existing references keep working.

- [ ] **Step 1: Write the isolation test**

Create `tests/test_workers_isolation.py`:

```python
import sys


def test_importing_workers_does_not_load_summarizer_or_db():
    for mod in ("summarizer.summarizer", "summarizer.db"):
        sys.modules.pop(mod, None)
    import summarizer.workers  # noqa: F401
    assert "summarizer.summarizer" not in sys.modules
    assert "summarizer.db" not in sys.modules


def test_workers_exports_expected_classes():
    import summarizer.workers as w
    for name in ("TranscribeWorker", "RealtimeTranscribeWorker",
                 "_DeltaTranscribeWorker", "DiarizeTranscribeWorker"):
        assert hasattr(w, name), name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workers_isolation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'summarizer.workers'`

- [ ] **Step 3: Create `workers.py` and move the classes**

Create `summarizer/workers.py` with these module imports, then move the four classes (`TranscribeWorker`, `RealtimeTranscribeWorker`, `_DeltaTranscribeWorker`, `DiarizeTranscribeWorker`) **cut verbatim** from `app.py`:

```python
"""Transcription QThread workers, shared by the full and lite apps.

This module must not import summarizer.summarizer or summarizer.db so the lite
app can reuse it without pulling in the cloud LLM SDKs or the history layer.
"""

from __future__ import annotations

import logging
import queue
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from .transcriber import Transcriber
from .i18n import t

_logger = logging.getLogger("workers")

# <-- paste TranscribeWorker, RealtimeTranscribeWorker, _DeltaTranscribeWorker,
#     and DiarizeTranscribeWorker here, exactly as they were in app.py -->
```

Note: `DiarizeTranscribeWorker.run()` uses `_logger` and does a lazy `from . import diarize` / `from .i18n import locale` — keep those lazy imports as-is; they resolve fine from `workers.py`.

- [ ] **Step 4: Import them back in `app.py`**

In `app.py`, delete the four class definitions you just moved. Near the other `from .` imports (after line 40), add:

```python
from .workers import (
    TranscribeWorker,
    RealtimeTranscribeWorker,
    _DeltaTranscribeWorker,
    DiarizeTranscribeWorker,
)
```

- [ ] **Step 5: Run tests + smoke-check the full app still imports**

Run:
```bash
.venv/bin/python -m pytest tests/test_workers_isolation.py -v
.venv/bin/python -c "import summarizer.app"
```
Expected: tests PASS; `import summarizer.app` exits 0 with no error.

- [ ] **Step 6: Manually smoke-test the full app**

```bash
source .venv/bin/activate && python run.py
```
Record a few seconds, stop, confirm transcription still works (workers now live in `workers.py`). Close.

- [ ] **Step 7: Commit**

```bash
git add summarizer/workers.py summarizer/app.py tests/test_workers_isolation.py
git commit -m "refactor: extract transcription workers into workers.py"
```

---

### Task 2: `LiveTranscriber` controller

**Files:**
- Modify: `summarizer/workers.py` (add `LiveTranscriber`)
- Modify: `tests/test_workers_isolation.py` (extend the export assertion)
- Test: `tests/test_live_transcriber.py`

**Context:** In the full app, `MainWindow` drives the live transcript with a 10-second `QTimer` that slices the new audio delta (`get_all_rt_audio()[committed_len:]`) and pushes it to a `RealtimeTranscribeWorker`; `_on_rt_chunk(text, audio_len)` advances `committed_len` and appends the text. This task encapsulates exactly that orchestration into a reusable `LiveTranscriber` so the lite window reuses it instead of copying it. `MainWindow` is NOT changed.

**Interfaces:**
- Consumes: `RealtimeTranscribeWorker` (Task 1), a recorder exposing `get_all_rt_audio() -> np.ndarray | None`, `sample_rate: int`, `is_recording() -> bool`.
- Produces: `summarizer.workers.LiveTranscriber(QObject)` with signal `text_appended = pyqtSignal(str)`, and methods `start(recorder, whisper_model: str) -> None`, `stop() -> None`. Internally uses a `QTimer` (10 s) and tracks `_committed_len`. On each tick it pushes the audio delta once it exceeds 3 s; on each chunk it advances `_committed_len` and emits non-empty text via `text_appended`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_live_transcriber.py` (this tests the pure bookkeeping via the chunk handler and the delta-gating on tick, using fakes — no real Qt event loop, model, or audio):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_live_transcriber.py -v`
Expected: FAIL with `ImportError: cannot import name 'LiveTranscriber'`

- [ ] **Step 3: Implement `LiveTranscriber`**

Add to `summarizer/workers.py` (extend the `PyQt6.QtCore` import to include `QObject` and `QTimer`):

```python
class LiveTranscriber(QObject):
    """Drives real-time (untagged) transcription for display during recording.

    Encapsulates the RealtimeTranscribeWorker + a poll timer + committed-sample
    bookkeeping, so a window can show live text without duplicating the
    orchestration. Emits text_appended(str) as new chunks arrive.
    """
    text_appended = pyqtSignal(str)

    _POLL_MS = 10000
    _MIN_DELTA_SEC = 3.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._recorder = None
        self._worker = None
        self._committed_len = 0
        self._sample_rate = 44100
        self._timer = QTimer(self)
        self._timer.setInterval(self._POLL_MS)
        self._timer.timeout.connect(self._on_tick)

    def start(self, recorder, whisper_model: str):
        self._recorder = recorder
        self._committed_len = 0
        self._sample_rate = getattr(recorder, "sample_rate", 44100)
        self._worker = RealtimeTranscribeWorker(whisper_model)
        self._worker.model_ready.connect(self._on_model_ready)
        self._worker.chunk_ready.connect(self._on_chunk)
        self._worker.error.connect(lambda e: _logger.warning("LiveTranscriber: %s", e))
        self._worker.start()

    def _on_model_ready(self):
        if self._recorder is not None and self._recorder.is_recording():
            self._timer.start()

    def _on_tick(self):
        try:
            if self._recorder is None or self._worker is None:
                return
            all_audio = self._recorder.get_all_rt_audio()
            if all_audio is None or len(all_audio) == 0:
                return
            delta = all_audio[self._committed_len:]
            if len(delta) < self._sample_rate * self._MIN_DELTA_SEC:
                return
            self._worker.push_audio(delta, self._sample_rate)
        except Exception:
            _logger.exception("LiveTranscriber tick failed (recording continues)")

    def _on_chunk(self, text: str, audio_len: int):
        self._committed_len += audio_len
        if text:
            self.text_appended.emit(text)

    def stop(self):
        self._timer.stop()
        if self._worker is not None:
            try:
                self._worker.chunk_ready.disconnect(self._on_chunk)
            except (TypeError, RuntimeError):
                pass
            if self._worker.isRunning():
                self._worker.request_stop()
        self._worker = None
        self._recorder = None
```

- [ ] **Step 4: Extend the isolation export test**

In `tests/test_workers_isolation.py`, add `"LiveTranscriber"` to the tuple of names checked in `test_workers_exports_expected_classes`.

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_live_transcriber.py tests/test_workers_isolation.py -v
```
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add summarizer/workers.py tests/test_live_transcriber.py tests/test_workers_isolation.py
git commit -m "feat: add reusable LiveTranscriber controller"
```

---

### Task 3: Shared `MicPicker` widget

**Files:**
- Create: `summarizer/widgets.py`
- Test: `tests/test_widgets.py`

**Interfaces:**
- Produces: `summarizer.widgets.MicPicker(QComboBox)` with `__init__(self, selected=None, parent=None)` that populates from `AudioRecorder.list_devices()` (each `{"id", "name", "channels"}`), stores each device id as item data, preselects `selected` when present, and exposes `selected_device() -> int | None` returning the current item's device id (or `None` for a "System default" first entry whose data is `None`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_widgets.py`:

```python
import pytest

pytest.importorskip("PyQt6.QtWidgets")
from PyQt6.QtWidgets import QApplication
from summarizer import widgets

_app = QApplication.instance() or QApplication([])


def test_micpicker_has_default_first_and_lists_devices(monkeypatch):
    monkeypatch.setattr(
        widgets.AudioRecorder, "list_devices",
        staticmethod(lambda: [{"id": 3, "name": "Built-in Mic", "channels": 1}]),
    )
    p = widgets.MicPicker()
    assert p.count() == 2  # default + one device
    assert p.itemData(0) is None  # system default
    assert p.itemData(1) == 3


def test_micpicker_preselects_saved(monkeypatch):
    monkeypatch.setattr(
        widgets.AudioRecorder, "list_devices",
        staticmethod(lambda: [{"id": 3, "name": "Built-in Mic", "channels": 1}]),
    )
    p = widgets.MicPicker(selected=3)
    assert p.selected_device() == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_widgets.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'summarizer.widgets'`

- [ ] **Step 3: Write minimal implementation**

Create `summarizer/widgets.py`:

```python
"""Small UI widgets shared by the full and lite apps.

Must not import summarizer.summarizer or summarizer.db.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox

from .recorder import AudioRecorder
from .i18n import t


class MicPicker(QComboBox):
    """Dropdown of input devices; first entry is the system default (id None)."""

    def __init__(self, selected=None, parent=None):
        super().__init__(parent)
        self.addItem(t("input_device_default"), None)
        for dev in AudioRecorder.list_devices():
            self.addItem(dev["name"], dev["id"])
        if selected is not None:
            idx = self.findData(selected)
            if idx >= 0:
                self.setCurrentIndex(idx)

    def selected_device(self):
        return self.currentData()
```

- [ ] **Step 4: Add the i18n string**

In `summarizer/i18n.py`, add to the `_STRINGS` dict:

```python
    "input_device_default": {"en": "System default", "ru": "Системный по умолчанию"},
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_widgets.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add summarizer/widgets.py tests/test_widgets.py summarizer/i18n.py
git commit -m "feat: add shared MicPicker widget"
```

---

### Task 4: `LiteWindow` — record, live transcript, tag, copy

**Files:**
- Create: `summarizer/app_lite.py`
- Test: manual (GUI + audio)

**Interfaces:**
- Consumes: `AudioRecorder`, `workers.LiveTranscriber`, `workers.DiarizeTranscribeWorker`, `workers.TranscribeWorker`, `widgets.MicPicker`, `config`, `i18n.t`, `theme`.
- Produces: `LiteWindow(QMainWindow)` with a Record/Stop button, elapsed timer, a read-only transcript view, a Copy button, and a status line. While recording it shows a live untagged transcript via `LiveTranscriber`. On stop: if both source streams exist → `DiarizeTranscribeWorker` (replaces the live text with the Me/Remote tagged version); else → plain `TranscribeWorker(mixed)`. Manual recordings display + copy only. `_handle_result(text)` is a hook overridden in Task 5 for agent upload.

- [ ] **Step 1: Implement the window**

Create `summarizer/app_lite.py`:

```python
"""Lite transcript client: record -> live transcript -> Me/Remote tag -> copy/upload.

Never imports summarizer.summarizer or summarizer.db.
"""

from __future__ import annotations

import logging
import time

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel,
)

from . import config, theme
from .i18n import t
from .recorder import AudioRecorder
from .workers import LiveTranscriber, DiarizeTranscribeWorker, TranscribeWorker

_logger = logging.getLogger("app_lite")


class LiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("lite_title"))
        self._recorder = None
        self._diar_recorder = None
        self._start_ts = None
        self._last_duration = 0
        self._workers = []

        central = QWidget()
        lay = QVBoxLayout(central)

        self.status = QLabel(t("lite_ready"))
        lay.addWidget(self.status)

        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText(t("lite_placeholder"))
        lay.addWidget(self.transcript, 1)

        row = QHBoxLayout()
        self.record_btn = QPushButton(t("start_recording"))
        self.record_btn.clicked.connect(self._toggle)
        row.addWidget(self.record_btn)
        self.copy_btn = QPushButton(t("lite_copy"))
        self.copy_btn.clicked.connect(self._copy)
        self.copy_btn.setEnabled(False)
        row.addWidget(self.copy_btn)
        lay.addLayout(row)

        self.setCentralWidget(central)
        self.resize(560, 420)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

        self._live = LiveTranscriber(self)
        self._live.text_appended.connect(self._append_live)

    # ── recording ────────────────────────────────────────────────
    def _toggle(self):
        if self._recorder and self._recorder.is_recording():
            self._stop()
        else:
            self._start()

    def _start(self):
        cfg = config.load()
        self._recorder = AudioRecorder(
            silence_timeout=cfg.get("silence_timeout", 30),
            input_device=cfg.get("input_device"),
        )
        self._recorder.start()
        self._start_ts = time.monotonic()
        self.transcript.clear()
        self.copy_btn.setEnabled(False)
        self.record_btn.setText(t("stop_recording", time="0:00"))
        self.record_btn.setStyleSheet(theme.btn_recording())
        self.status.setText(t("status_recording"))
        self._timer.start()
        wm = cfg.get("whisper_model", config.DEFAULT_CONFIG["whisper_model"])
        self._live.start(self._recorder, wm)

    def _append_live(self, text: str):
        current = self.transcript.toPlainText()
        sep = " " if current else ""
        self.transcript.setPlainText(current + sep + text)
        sb = self.transcript.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _tick(self):
        if self._start_ts is None:
            return
        secs = int(time.monotonic() - self._start_ts)
        self.record_btn.setText(t("stop_recording", time=f"{secs // 60}:{secs % 60:02d}"))

    def _stop(self):
        self._timer.stop()
        self._live.stop()
        self.record_btn.setText(t("start_recording"))
        self.record_btn.setStyleSheet(theme.btn_primary())
        duration = int(time.monotonic() - self._start_ts) if self._start_ts else 0
        self._start_ts = None

        mixed = self._recorder.stop()
        sources = self._recorder.get_source_files()
        self._diar_recorder = self._recorder
        self._recorder = None
        self._last_duration = duration

        if not mixed:
            self._cleanup_sources()
            self.status.setText(t("status_recording_failed"))
            return

        self.status.setText(t("status_transcribing"))
        cfg = config.load()
        wm = cfg.get("whisper_model", config.DEFAULT_CONFIG["whisper_model"])
        mic = sources.get("mic") or []
        sysf = sources.get("system")
        if mic and sysf:
            worker = DiarizeTranscribeWorker(wm, mic[0], sysf)
            worker.finished.connect(self._on_transcript)
            worker.error.connect(self._on_plain_fallback)
            self._track(worker)
            worker.start()
        else:
            self._plain_transcribe(mixed, wm)

    def _plain_transcribe(self, mixed, wm):
        worker = TranscribeWorker(mixed, wm)
        worker.finished.connect(self._on_transcript)
        worker.error.connect(lambda e: self.status.setText(t("lite_error", err=e)))
        self._track(worker)
        worker.start()

    def _on_plain_fallback(self, _err):
        self._cleanup_sources()
        self.status.setText(t("lite_error", err="empty"))

    def _on_transcript(self, text: str):
        self._cleanup_sources()
        self.transcript.setPlainText(text)
        self.copy_btn.setEnabled(bool(text.strip()))
        self.status.setText(t("lite_done"))
        self._handle_result(text)  # overridden in Task 5 for agent upload

    def _handle_result(self, text: str):
        """Manual recording: nothing more to do (copy only). Overridden in Task 5."""
        pass

    def _cleanup_sources(self):
        if self._diar_recorder:
            self._diar_recorder.cleanup_sources()
            self._diar_recorder = None

    def _copy(self):
        QGuiApplication.clipboard().setText(self.transcript.toPlainText())
        self.status.setText(t("lite_copied"))

    def _track(self, worker):
        self._workers.append(worker)
        worker.finished.connect(
            lambda *_: self._workers.remove(worker) if worker in self._workers else None
        )


def main():
    import sys
    from PyQt6.QtWidgets import QApplication

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    theme.apply(app)
    win = LiteWindow()
    win.show()
    sys.exit(app.exec())
```

- [ ] **Step 2: Add i18n strings**

In `summarizer/i18n.py` `_STRINGS`, add:

```python
    "lite_title": {"en": "Summarizer Transcriber", "ru": "Summarizer Транскрибатор"},
    "lite_ready": {"en": "Ready", "ru": "Готово"},
    "lite_placeholder": {"en": "Transcript will appear here.",
                          "ru": "Транскрипт появится здесь."},
    "lite_copy": {"en": "Copy transcript", "ru": "Копировать транскрипт"},
    "lite_copied": {"en": "Copied to clipboard", "ru": "Скопировано в буфер обмена"},
    "lite_done": {"en": "Transcript ready", "ru": "Транскрипт готов"},
    "lite_error": {"en": "Transcription failed: {err}", "ru": "Ошибка транскрипции: {err}"},
```

- [ ] **Step 3: Verify `theme.apply` exists**

Run: `.venv/bin/python -c "from summarizer import theme; print(hasattr(theme, 'apply'))"`
Expected: `True`. If it prints `False`, open `summarizer/theme.py`, find the actual app-styling entry point (e.g. `apply_theme` / `set_palette`), and use that name in `main()` instead of `theme.apply`.

- [ ] **Step 4: Manual verification**

```bash
source .venv/bin/activate && python -c "from summarizer.app_lite import main; main()"
```
- Record a few seconds with system audio playing + speaking → a live untagged transcript streams in → Stop → transcript is replaced with `Me:`/`Remote:` tags → Copy enables and copies.
- Confirm no summarization/history UI is present.

- [ ] **Step 5: Commit**

```bash
git add summarizer/app_lite.py summarizer/i18n.py
git commit -m "feat: add LiteWindow with live transcript, tagging, copy"
```

---

### Task 5: Agent polling + upload in lite

**Files:**
- Modify: `summarizer/app_lite.py`
- Test: manual

**Interfaces:**
- Consumes: `agent.AgentPoller`, `agent.PostCompleteWorker`.
- Produces: `LiteWindow` starts an `AgentPoller` when `config.agent_enabled` is true, auto-records armed meetings, remembers the armed `meeting` dict, and on transcript-ready uploads via `PostCompleteWorker` (agent recordings only). Manual recordings still copy-only.

- [ ] **Step 1: Wire the poller and auto-record**

In `LiteWindow.__init__`, after building the UI and the `LiveTranscriber`, add:

```python
        self._agent_meeting = None
        self._poller = None
        cfg = config.load()
        if cfg.get("agent_enabled") and cfg.get("agent_url") and cfg.get("agent_token"):
            from .agent import AgentPoller
            self._poller = AgentPoller(self)
            self._poller.meeting_armed.connect(self._on_meeting_armed)
            self._poller.error.connect(lambda e: _logger.warning("agent: %s", e))
            self._poller.start()
            self.status.setText(t("lite_agent_waiting"))
```

Add the armed-meeting handler:

```python
    def _on_meeting_armed(self, meeting: dict):
        if self._recorder and self._recorder.is_recording():
            return  # already recording
        self._agent_meeting = meeting
        self.status.setText(t("lite_agent_recording", title=meeting.get("title", "")))
        self._start()
```

- [ ] **Step 2: Upload on transcript-ready for agent recordings**

Replace the `_handle_result` stub from Task 4 with:

```python
    def _handle_result(self, text: str):
        meeting = self._agent_meeting
        self._agent_meeting = None
        if not meeting:
            return  # manual recording: copy only
        meeting["_duration"] = self._last_duration
        from .agent import PostCompleteWorker
        worker = PostCompleteWorker(text, meeting)
        worker.finished.connect(lambda _r: self.status.setText(t("lite_uploaded")))
        worker.error.connect(lambda e: self.status.setText(t("lite_upload_failed", err=e)))
        self._track(worker)
        worker.start()
```

- [ ] **Step 3: Stop the poller on close**

Add to `LiteWindow`:

```python
    def closeEvent(self, event):
        if self._poller:
            self._poller.stop()
            self._poller.wait(2000)
        super().closeEvent(event)
```

- [ ] **Step 4: Add i18n strings**

In `summarizer/i18n.py` `_STRINGS`, add:

```python
    "lite_agent_waiting": {"en": "Waiting for scheduled meetings…",
                            "ru": "Ожидание запланированных встреч…"},
    "lite_agent_recording": {"en": "Auto-recording: {title}",
                              "ru": "Автозапись: {title}"},
    "lite_uploaded": {"en": "Transcript uploaded", "ru": "Транскрипт загружен"},
    "lite_upload_failed": {"en": "Upload failed: {err}", "ru": "Ошибка загрузки: {err}"},
```

- [ ] **Step 5: Manual verification**

With `agent_enabled`, `agent_url`, `agent_token` set in `~/.summarizer/config.json` pointing at a test backend: confirm the status shows "Waiting…", an armed meeting triggers auto-record, and on stop the transcript uploads (status "Transcript uploaded"). With the poller disabled, a manual recording only copies (no upload attempted).

- [ ] **Step 6: Commit**

```bash
git add summarizer/app_lite.py summarizer/i18n.py
git commit -m "feat: agent auto-record and upload in lite client"
```

---

### Task 6: `LiteSetupWizard` — mic + backend

**Files:**
- Modify: `summarizer/app_lite.py`
- Test: manual

**Interfaces:**
- Consumes: `widgets.MicPicker`, `config.load`/`config.save`, `config.is_model_downloaded`, `config.DEFAULT_CONFIG`, `transcriber.download_model`.
- Produces: `LiteSetupWizard(QDialog)` with three steps — (1) mic permission + `MicPicker`, (2) backend `agent_url` + `agent_token`, (3) Whisper model download progress (model hard-coded to `config.DEFAULT_CONFIG["whisper_model"]`). Saves to config on finish. `should_run_setup() -> bool` returns True when `agent_url` is empty or the default Whisper model is not downloaded.

- [ ] **Step 1: Implement the wizard**

Add to `summarizer/app_lite.py` (extend imports: add `QDialog, QLineEdit, QProgressBar, QStackedWidget, QFormLayout` to the `PyQt6.QtWidgets` import; add `QThread, pyqtSignal` to the `PyQt6.QtCore` import; add `from .transcriber import download_model` and `from .widgets import MicPicker`):

```python
class LiteSetupWizard(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("lite_setup_title"))
        self._cfg = config.load()
        self._model = config.DEFAULT_CONFIG["whisper_model"]

        self._stack = QStackedWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(self._stack)

        # Step 1 — mic
        s1 = QWidget(); l1 = QVBoxLayout(s1)
        l1.addWidget(QLabel(t("lite_setup_mic")))
        self._mic = MicPicker(selected=self._cfg.get("input_device"))
        l1.addWidget(self._mic)
        b1 = QPushButton(t("wizard_next")); b1.clicked.connect(self._to_backend)
        l1.addWidget(b1)
        self._stack.addWidget(s1)

        # Step 2 — backend
        s2 = QWidget(); l2 = QFormLayout(s2)
        self._url = QLineEdit(self._cfg.get("agent_url", ""))
        self._token = QLineEdit(self._cfg.get("agent_token", ""))
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        l2.addRow(t("lite_setup_url"), self._url)
        l2.addRow(t("lite_setup_token"), self._token)
        b2 = QPushButton(t("wizard_next")); b2.clicked.connect(self._to_download)
        l2.addRow(b2)
        self._stack.addWidget(s2)

        # Step 3 — download
        s3 = QWidget(); l3 = QVBoxLayout(s3)
        l3.addWidget(QLabel(t("lite_setup_download")))
        self._bar = QProgressBar()
        l3.addWidget(self._bar)
        self._stack.addWidget(s3)

        self.resize(420, 240)

    def _to_backend(self):
        self._cfg["input_device"] = self._mic.selected_device()
        self._stack.setCurrentIndex(1)

    def _to_download(self):
        self._cfg["agent_url"] = self._url.text().strip()
        self._cfg["agent_token"] = self._token.text().strip()
        self._cfg["agent_enabled"] = bool(self._cfg["agent_url"])
        self._cfg["whisper_model"] = self._model
        config.save(self._cfg)
        self._stack.setCurrentIndex(2)
        if config.is_model_downloaded(self._model):
            self._bar.setValue(100)
            self.accept()
            return
        self._dl = _LiteModelDownloadWorker(self._model)
        self._dl.progress.connect(lambda p: self._bar.setValue(int(p * 100)))
        self._dl.done.connect(self.accept)
        self._dl.error.connect(lambda e: self.reject())
        self._dl.start()


class _LiteModelDownloadWorker(QThread):
    progress = pyqtSignal(float)
    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model_name):
        super().__init__()
        self._model = model_name

    def run(self):
        try:
            download_model(self._model, progress_cb=lambda p: self.progress.emit(p))
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


def should_run_setup() -> bool:
    cfg = config.load()
    model = config.DEFAULT_CONFIG["whisper_model"]
    return not cfg.get("agent_url") or not config.is_model_downloaded(model)
```

- [ ] **Step 2: Run the wizard before the window in `main()`**

Update `main()` in `app_lite.py` so setup runs first when needed (add `QDialog` to the `PyQt6.QtWidgets` import if not already there):

```python
def main():
    import sys
    from PyQt6.QtWidgets import QApplication

    logging.basicConfig(level=logging.INFO)
    app = QApplication(sys.argv)
    theme.apply(app)
    if should_run_setup():
        wiz = LiteSetupWizard()
        if wiz.exec() != QDialog.DialogCode.Accepted:
            return
    win = LiteWindow()
    win.show()
    sys.exit(app.exec())
```

- [ ] **Step 3: Add i18n strings**

In `summarizer/i18n.py` `_STRINGS`, add:

```python
    "lite_setup_title": {"en": "Set up Transcriber", "ru": "Настройка Транскрибатора"},
    "lite_setup_mic": {"en": "Choose your microphone. Grant mic access if prompted.",
                        "ru": "Выберите микрофон. Разрешите доступ к микрофону при запросе."},
    "lite_setup_url": {"en": "Backend URL", "ru": "URL бэкенда"},
    "lite_setup_token": {"en": "Access token", "ru": "Токен доступа"},
    "lite_setup_download": {"en": "Downloading the transcription model…",
                             "ru": "Загрузка модели транскрипции…"},
```

- [ ] **Step 4: Verify `config.save` and `download_model` signatures**

Run:
```bash
.venv/bin/python -c "from summarizer import config; print(hasattr(config,'save'), hasattr(config,'is_model_downloaded'), 'whisper_model' in config.DEFAULT_CONFIG)"
.venv/bin/python -c "import inspect, summarizer.transcriber as t; print(inspect.signature(t.download_model))"
```
Expected: `True True True`, and `download_model(model_name, progress_cb=None)`. If `config.save` is named differently (e.g. `config.write`/`config.dump`), use that name in `_to_download`. If `DEFAULT_CONFIG` is spelled differently, grep `config.py` for the defaults dict and use the correct name.

- [ ] **Step 5: Manual verification**

Temporarily clear `agent_url` in `~/.summarizer/config.json`, launch lite, walk the 3 steps, confirm config is saved and the window opens.

- [ ] **Step 6: Commit**

```bash
git add summarizer/app_lite.py summarizer/i18n.py
git commit -m "feat: add LiteSetupWizard (mic + backend + model)"
```

---

### Task 7: `run_lite.py` entry point

**Files:**
- Create: `run_lite.py`
- Test: manual

**Interfaces:**
- Produces: `run_lite.py` mirroring `run.py`'s bundled-resource setup (ffmpeg / whisper paths) but calling `summarizer.app_lite.main()`.

- [ ] **Step 1: Read `run.py` and copy its resource setup**

Open `run.py`. Create `run_lite.py` with the **same** resource-path/environment setup block, changing only the final import+call:

```python
# ... identical bundled-resource setup copied from run.py ...

if __name__ == "__main__":
    from summarizer.app_lite import main
    main()
```

- [ ] **Step 2: Manual verification**

```bash
source .venv/bin/activate && python run_lite.py
```
Expected: the lite window (or setup wizard) launches; recording + live transcript + tagging work end to end.

- [ ] **Step 3: Commit**

```bash
git add run_lite.py
git commit -m "feat: add run_lite.py entry point"
```

---

### Task 8: `build.sh` lite target

**Files:**
- Modify: `build.sh`
- Test: manual build

**Interfaces:**
- Produces: `build.sh` builds the lite bundle when invoked with a `lite` argument (`./build.sh lite`), producing `Summarizer Transcriber.app` + its DMG with a distinct bundle id/name. The default (no arg) still builds the full app unchanged.

- [ ] **Step 1: Read `build.sh` and identify the PyInstaller invocation**

Open `build.sh`. Locate: the app name variable, the PyInstaller call (`--name`, entry script `run.py`, `--osx-bundle-identifier`), and the DMG creation. Note the exact variable names.

- [ ] **Step 2: Parameterize by edition**

Near the top of `build.sh`, after the shebang/`set -e`, add:

```bash
EDITION="${1:-full}"
if [ "$EDITION" = "lite" ]; then
  APP_NAME="Summarizer Transcriber"
  ENTRY="run_lite.py"
  BUNDLE_ID="com.summarizer.transcriber"
else
  APP_NAME="Summarizer"
  ENTRY="run.py"
  BUNDLE_ID="com.summarizer.app"
fi
```

Then replace the hard-coded app name, entry script, and bundle id in the PyInstaller call and DMG steps with `"$APP_NAME"`, `"$ENTRY"`, and `"$BUNDLE_ID"` (match the real variable/flag names found in Step 1; keep every other flag identical). Ensure `--hidden-import summarizer.app_lite`, `--hidden-import summarizer.workers`, `--hidden-import summarizer.widgets`, and `--hidden-import summarizer.diarize` are collected for the lite entry (PyInstaller follows imports, but add them explicitly if the build warns).

- [ ] **Step 3: Build the lite bundle**

Run: `./build.sh lite`
Expected: `dist/Summarizer Transcriber.app` and a corresponding DMG are produced without error.

- [ ] **Step 4: Smoke-test the built app**

```bash
open "dist/Summarizer Transcriber.app"
```
Expected: the lite app launches (setup wizard on first run), records, shows a live transcript, tags Me/Remote on stop, and copies. Confirm the full build still works: `./build.sh` (no arg) → `dist/Summarizer.app`.

- [ ] **Step 5: Commit**

```bash
git add build.sh
git commit -m "feat: add lite build target to build.sh"
```

---

## Self-Review Notes

- **Spec coverage:** separate entry point (Tasks 4–7), no `summarizer`/`db` imports (Task 1 isolation test guards it), shared `LiveTranscriber` (Task 2) and `MicPicker` (Task 3), live transcript during recording (Task 4), agent-upload reuse + manual copy-only (Task 5), 3-step wizard with hard-coded model (Task 6), two bundles from one codebase (Task 8).
- **Live transcript reuse:** `MainWindow` is intentionally left untouched (global constraint); the lite window reuses the RT orchestration through the shared `LiveTranscriber` controller rather than duplicating it. Migrating the full app onto the same controller is a possible later step, out of scope here.
- **Signature verification steps** (Tasks 4/6) exist because `theme.apply`, `config.save`, and the defaults-dict name were not confirmed while writing this plan; the engineer verifies and adjusts to the real names before proceeding.
- **`_track` cleanup** keeps QThread references alive until they finish, preventing premature GC of running workers.
