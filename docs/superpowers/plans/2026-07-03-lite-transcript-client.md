# Lite Transcript Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Depends on:** `2026-07-03-speaker-separation.md` (the `diarize` module, `Transcriber.transcribe_segments`, recorder source files, and `DiarizeTranscribeWorker` must exist first).

**Goal:** Ship a second app bundle ("Summarizer Transcriber") that records, transcribes locally with Me/Remote tagging, uploads the transcript for agent-scheduled meetings, and shows it with a Copy button for manual recordings — with no summarization, history, grouping, context, or LLM settings.

**Architecture:** One codebase, two bundles (Option A). The transcription `QThread` workers move from `app.py` into a neutral `summarizer/workers.py` that never imports `summarizer.summarizer` or `summarizer.db`. A new `app_lite.py` (`LiteWindow` + `LiteSetupWizard`) and `run_lite.py` entry point reuse `recorder`, `workers`, `diarize`, `agent`, `config`, `i18n`, `theme`, and a shared `widgets.py`. `build.sh` gains a lite target.

**Tech Stack:** PyQt6 (existing), plus the existing `recorder`/`transcriber`/`diarize`/`agent`/`config`/`i18n`/`theme` modules.

## Global Constraints

- `app_lite.py`, `run_lite.py`, `workers.py`, and `widgets.py` MUST NOT import `summarizer.summarizer` or `summarizer.db` (keeps the LLM SDKs and history layer out of the lite bundle). (Spec: architecture, exclusions.)
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
- Produces `summarizer/workers.py` exporting `TranscribeWorker`, `RealtimeTranscribeWorker`, `_DeltaTranscribeWorker`, `DiarizeTranscribeWorker` — moved verbatim from `app.py` (signatures unchanged; see the speaker-separation plan for `DiarizeTranscribeWorker(whisper_model, mic_path, sys_path)`).
- `app.py` re-imports them so existing references keep working.

- [ ] **Step 1: Write the isolation test**

Create `tests/test_workers_isolation.py`:

```python
import sys


def test_importing_workers_does_not_load_summarizer_or_db():
    # Drop any pre-import so the check is meaningful.
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

Run: `python -m pytest tests/test_workers_isolation.py -v`
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
python -m pytest tests/test_workers_isolation.py -v
python -c "import summarizer.app"
```
Expected: tests PASS; `import summarizer.app` exits 0 with no error.

- [ ] **Step 6: Manually smoke-test the full app**

```bash
source .venv/bin/activate && python run.py
```
Record a few seconds, stop, confirm transcription still works (the workers now live in `workers.py`). Close.

- [ ] **Step 7: Commit**

```bash
git add summarizer/workers.py summarizer/app.py tests/test_workers_isolation.py
git commit -m "refactor: extract transcription workers into workers.py"
```

---

### Task 2: Shared `MicPicker` widget

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

Run: `python -m pytest tests/test_widgets.py -v`
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

Run: `python -m pytest tests/test_widgets.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add summarizer/widgets.py tests/test_widgets.py summarizer/i18n.py
git commit -m "feat: add shared MicPicker widget"
```

---

### Task 3: `LiteWindow` — record, transcribe, copy

**Files:**
- Create: `summarizer/app_lite.py`
- Test: manual (GUI + audio)

**Interfaces:**
- Consumes: `AudioRecorder`, `workers.RealtimeTranscribeWorker`, `workers.DiarizeTranscribeWorker`, `widgets.MicPicker`, `config`, `i18n.t`, `theme`.
- Produces: `LiteWindow(QMainWindow)` with a Record/Stop button, elapsed timer, a read-only transcript view, a Copy button, and a status line. On stop: if both source streams exist → `DiarizeTranscribeWorker`; else → plain `Transcriber.transcribe(mixed)`. Manual recordings display + copy only.

- [ ] **Step 1: Implement the window**

Create `summarizer/app_lite.py`:

```python
"""Lite transcript client: record -> local transcribe (Me/Remote) -> copy/upload.

Never imports summarizer.summarizer or summarizer.db.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel,
)

from . import config, theme
from .i18n import t
from .recorder import AudioRecorder
from .transcriber import Transcriber
from .workers import DiarizeTranscribeWorker

_logger = logging.getLogger("app_lite")


class LiteWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("lite_title"))
        self._recorder = None
        self._diar_recorder = None
        self._start_ts = None
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

    def _tick(self):
        if self._start_ts is None:
            return
        secs = int(time.monotonic() - self._start_ts)
        self.record_btn.setText(t("stop_recording", time=f"{secs // 60}:{secs % 60:02d}"))

    def _stop(self):
        self._timer.stop()
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
        from .workers import TranscribeWorker
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
        self._handle_result(text)  # overridden in Task 4 for agent upload

    def _handle_result(self, text: str):
        """Manual recording: nothing more to do (copy only). Overridden in Task 4."""
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
        worker.finished.connect(lambda *_: self._workers.remove(worker) if worker in self._workers else None)


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
    "lite_placeholder": {"en": "Transcript will appear here after recording.",
                          "ru": "Транскрипт появится здесь после записи."},
    "lite_copy": {"en": "Copy transcript", "ru": "Копировать транскрипт"},
    "lite_copied": {"en": "Copied to clipboard", "ru": "Скопировано в буфер обмена"},
    "lite_done": {"en": "Transcript ready", "ru": "Транскрипт готов"},
    "lite_error": {"en": "Transcription failed: {err}", "ru": "Ошибка транскрипции: {err}"},
```

- [ ] **Step 3: Verify `theme.apply` exists**

Run: `python -c "from summarizer import theme; print(hasattr(theme, 'apply'))"`
Expected: `True`. If it prints `False`, open `summarizer/theme.py`, find the actual app-styling entry point (e.g. `apply_theme` / `set_palette`), and use that name in `main()` instead of `theme.apply`.

- [ ] **Step 4: Manual verification**

```bash
source .venv/bin/activate && python -c "from summarizer.app_lite import main; main()"
```
- Record a few seconds with system audio playing + speaking → Stop → transcript shows `Me:`/`Remote:` tags → Copy enables and copies.
- Confirm no summarization/history UI is present.

- [ ] **Step 5: Commit**

```bash
git add summarizer/app_lite.py summarizer/i18n.py
git commit -m "feat: add LiteWindow record/transcribe/copy"
```

---

### Task 4: Agent polling + upload in lite

**Files:**
- Modify: `summarizer/app_lite.py`
- Test: manual

**Interfaces:**
- Consumes: `agent.AgentPoller`, `agent.PostCompleteWorker`.
- Produces: `LiteWindow` starts an `AgentPoller` when `config.agent_enabled` is true, auto-records armed meetings, remembers the armed `meeting` dict, and on transcript-ready uploads via `PostCompleteWorker` (agent recordings only). Manual recordings still copy-only.

- [ ] **Step 1: Wire the poller and auto-record**

In `LiteWindow.__init__`, after building the UI, add:

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

Replace the `_handle_result` stub from Task 3 with:

```python
    def _handle_result(self, text: str):
        meeting = self._agent_meeting
        self._agent_meeting = None
        if not meeting:
            return  # manual recording: copy only
        meeting["_duration"] = getattr(self, "_last_duration", 0)
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

### Task 5: `LiteSetupWizard` — mic + backend

**Files:**
- Modify: `summarizer/app_lite.py`
- Test: manual

**Interfaces:**
- Consumes: `widgets.MicPicker`, `config.load`/`config.save`, `config.is_model_downloaded`, `config.DEFAULT_CONFIG`, `transcriber.download_model`.
- Produces: `LiteSetupWizard(QDialog)` with three steps — (1) mic permission + `MicPicker`, (2) backend `agent_url` + `agent_token`, (3) Whisper model download progress (model hard-coded to `config.DEFAULT_CONFIG["whisper_model"]`). Saves to config on finish. `should_run_setup() -> bool` returns True when `agent_url` is empty or the default Whisper model is not downloaded.

- [ ] **Step 1: Implement the wizard**

Add to `summarizer/app_lite.py` (imports: `QDialog`, `QLineEdit`, `QProgressBar`, `QStackedWidget`, `QFormLayout` from `PyQt6.QtWidgets`; `download_model` from `.transcriber`; `MicPicker` from `.widgets`):

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

Add `QThread, pyqtSignal` to the `PyQt6.QtCore` import at the top of `app_lite.py`.

- [ ] **Step 2: Run the wizard before the window in `main()`**

Update `main()` in `app_lite.py` so setup runs first when needed:

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

(Add `QDialog` to the `PyQt6.QtWidgets` import.)

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
python -c "from summarizer import config; print(hasattr(config,'save'), hasattr(config,'is_model_downloaded'), 'whisper_model' in config.DEFAULT_CONFIG)"
python -c "import inspect, summarizer.transcriber as t; print(inspect.signature(t.download_model))"
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

### Task 6: `run_lite.py` entry point

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
Expected: the lite window (or setup wizard) launches; recording + transcription work end to end.

- [ ] **Step 3: Commit**

```bash
git add run_lite.py
git commit -m "feat: add run_lite.py entry point"
```

---

### Task 7: `build.sh` lite target

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

Then replace the hard-coded app name, entry script, and bundle id in the PyInstaller call and DMG steps with `"$APP_NAME"`, `"$ENTRY"`, and `"$BUNDLE_ID"` (match the real variable/flag names found in Step 1; keep every other flag identical). Ensure `--hidden-import summarizer.app_lite` and `--hidden-import summarizer.workers` and `--hidden-import summarizer.diarize` are collected for the lite entry (PyInstaller follows imports, but add them explicitly if the build warns).

- [ ] **Step 3: Build the lite bundle**

Run: `./build.sh lite`
Expected: `dist/Summarizer Transcriber.app` and a corresponding DMG are produced without error.

- [ ] **Step 4: Smoke-test the built app**

```bash
open "dist/Summarizer Transcriber.app"
```
Expected: the lite app launches (setup wizard on first run), records, transcribes with Me/Remote tags, and copies. Confirm the full build still works: `./build.sh` (no arg) → `dist/Summarizer.app`.

- [ ] **Step 5: Commit**

```bash
git add build.sh
git commit -m "feat: add lite build target to build.sh"
```

---

## Self-Review Notes

- **Spec coverage:** separate entry point (Tasks 3–6), no `summarizer`/`db` imports (Task 1 isolation test guards it), shared `MicPicker` (Task 2), agent-upload reuse + manual copy-only (Task 4), 3-step wizard with hard-coded model (Task 5), two bundles from one codebase (Task 7).
- **Live untagged transcript during recording** (spec Section B) is intentionally deferred: reusing the full app's RT tick/commit loop would duplicate fragile state. Lite v1 shows an elapsed timer while recording and the tagged transcript on stop. Revisit if live feedback proves necessary. **(Flag for user — deviates from spec Section B.)**
- **Signature verification steps** (Tasks 3/5) exist because `theme.apply`, `config.save`, and the defaults-dict name were not confirmed while writing this plan; the engineer verifies and adjusts to the real names before proceeding.
- **`_track` cleanup** keeps QThread references alive until they finish, preventing premature GC of running workers.
