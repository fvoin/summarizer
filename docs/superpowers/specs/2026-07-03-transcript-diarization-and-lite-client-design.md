# Design: Speaker Separation + Lite Transcript Client

**Date:** 2026-07-03
**Status:** Approved (design), pending implementation plan

## Overview

Two features for the Summarizer macOS app:

1. **Speaker separation** — tag the transcript as `Me` (local mic) vs `Remote`
   (the other side of the call), so summaries and transcripts distinguish who
   said what. Shared by both apps.
2. **Lite transcript client** — a stripped-down build ("Summarizer
   Transcriber") that records, transcribes locally, and either uploads the
   transcript to the backend (agent-scheduled recordings) or shows it for copy
   (manual recordings). No summarization, history, meeting grouping, context,
   or instruction profiles.

Both apps ship from **one codebase, two build outputs**. Both remain
maintained products.

---

## Feature 1 — Speaker separation (shared)

### Key insight

The app already captures two **physically separate** audio streams and only
mixes them at the end of `stop()`:

- **Mic** stream(s) → `summarizer_rec_*.wav` → the local speaker (+ anyone in
  the room, + remote voice leaking from speakers when not on headphones).
- **System audio** (Core Audio Process Tap) → `summarizer_sys_*.wav` → the
  remote side only, captured digitally *before* it reaches the speakers.

The system-audio stream is a **clean reference** of the remote voice. The
remote voice in the mic is just an echo of a signal we already hold cleanly.
This makes Me-vs-Remote separation a reference-based attribution problem, not
acoustic diarization.

We do NOT use WhisperX/pyannote:
- It would drag in full PyTorch + pyannote (hundreds of MB, heavier
  PyInstaller bundle) vs the current lightweight faster-whisper + ctranslate2.
- Its diarization model is gated and needs a per-user HuggingFace token +
  license acceptance — a dealbreaker for a distributed `.app`.
- Voice clustering would hear the remote voice in both streams as one speaker
  anyway; it cannot use the system-tap reference, which is the key signal.

### Timing

**Post-recording only.** During recording the live transcript stays untagged
(as today). On Stop, we work on the two final WAV files with full Whisper
timestamps. Real-time tagging is explicitly out of scope for v1 (would require
per-source RT buffers + two delta transcribers + live alignment;
`get_all_rt_audio()` currently mixes all devices to mono).

### Approach — text-space attribution using timestamps

We compare the two **transcripts** (not raw audio), using timestamps as the
primary signal and fuzzy text similarity as the tiebreaker. Exact text
matching is explicitly rejected: the echoed remote voice in the mic transcribes
differently from the clean system audio, so only fuzzy + time-aware matching is
reliable.

Merge algorithm (`diarize.py`):

1. **System transcript = the Remote track**, verbatim and authoritative.
2. For each **mic** segment, classify:
   - System **silent** in that time window → **Me** (remote wasn't talking —
     strongest, most reliable signal).
   - System **active** and mic text **similar** to overlapping system text
     (token similarity ≥ threshold) → **echo → drop** (already in Remote track).
   - System **active** but mic text **clearly different** → **double-talk → Me**
     (local talked over remote).
3. Merge kept-mic segments + all system segments, sort by start time → tagged
   transcript.

**Alignment:** one energy-envelope cross-correlation estimates the bulk
mic↔system time offset (the streams start near-simultaneously, so this is a
small correction) and is applied before windowed comparison. Handles the
44.1 kHz mic / 48 kHz tap difference (already resampled elsewhere).

**Similarity:** normalized token ratio (lowercase, strip punctuation) via
`difflib.SequenceMatcher` or `rapidfuzz`, threshold ~0.6 (tunable). Whisper
detects language per stream.

### Graceful degradation

Diarization activates only when **both** streams exist:
- No system audio (in-person meeting, mic only) → single untagged transcript,
  exactly as today.
- No mic (system-only) → all Remote.

### Output

Inline text labels: `Me:` / `Remote:`, localized via i18n (e.g. `Я:` /
`Собеседник:`). Names stay generic for v1; the backend/summarizer can map them
later. The upload contract is unchanged — `agent.post_complete` still sends a
`transcript` string, now speaker-tagged.

### Code changes

- **`recorder.py`**: track sources as `self._mic_files` / `self._sys_file`;
  keep producing the mixed file (backward compatible) but retain the two
  sources and expose `get_source_files() -> {"mic": [...], "system": path|None}`.
  Move temp-file cleanup to after diarization consumes them.
- **`transcriber.py`**: add `transcribe_segments(path) -> [Segment(start, end,
  text)]` (faster-whisper segments already carry `.start`/`.end`; just don't
  collapse to a string). Existing `transcribe()` stays.
- **`diarize.py`** (new): the merge algorithm above. Pure logic, unit-testable
  with synthetic segment lists.
- **`DiarizeTranscribeWorker`** (new `QThread`, extends/replaces
  `TranscribeWorker`): on Stop, transcribe mic → transcribe system →
  `diarize.merge` → tagged text. Falls back to plain transcription of the mixed
  file when only one stream exists. Used by both apps.

The full app's summarization consumes the tagged transcript directly — strictly
better LLM input, no prompt change required.

---

## Feature 2 — Lite transcript client

### Architecture: separate entry point (one codebase, two bundles)

Chosen over a feature-flag edition or full panelization because the non-UI
logic (`recorder`, `transcriber`, `agent`) is already modular; only the UI
(`MainWindow` in the 4289-line `app.py`) is monolithic. A separate lite window
reuses the clean modules and adds a small focused UI, cannot break the full
app, and ships no cloud LLM SDKs or DB layer.

- **`run_lite.py`** — new entry point mirroring `run.py`'s bundled-resource
  setup; calls `app_lite.main()`.
- **`app_lite.py`** — `LiteWindow` + `LiteSetupWizard`. Imports `recorder`,
  `transcriber`, `diarize`, `agent`, `config`, `i18n`, `theme`, shared widgets.
  **Never** imports `summarizer.py` or `db.py`.

### `LiteWindow` (minimal UI)

- Record button + elapsed timer + recording status.
- Live untagged transcript (reuses `RealtimeTranscribeWorker`).
- On Stop: `DiarizeTranscribeWorker` → show Me/Remote tagged transcript +
  **Copy** button.
- Recording behavior mirrors today's app:
  - **Agent-armed recording** → also uploads via `agent.post_complete`
    (existing code).
  - **Manual recording** → display + copy only, no upload.
- Agent status line (waiting / next meeting / last upload result).

### `LiteSetupWizard` (6 steps → ~3)

- Mic permission + mic pick (shared widget).
- **Connect to backend** — `agent_url` + `agent_token` (new step; today these
  are not in the wizard).
- Whisper model download progress.
- **Whisper model is hard-coded** to a sensible default so first launch is just
  "grant mic + paste backend URL/token" (easiest fleet rollout). Picker can be
  exposed later.
- Dropped: LLM type, cloud API key, local model, use-case/instruction profile.

### Shared-widgets module

Extract only the genuinely-common controls from `app.py` into `widgets.py`: mic
picker, record control/timer, Whisper model-download step. Both windows and both
wizards import them. Summarization and history are untouched — this is the one
targeted "hybrid" extraction that avoids copy-paste without a big refactor.

### Build

`build.sh` gains a lite target (param or separate invocation): PyInstaller
against `run_lite.py` → `Summarizer Transcriber.app` → its own DMG, distinct
bundle id/name. Both bundles built from the same repo, sharing all logic.

### Config

Lite reads the same `~/.summarizer/config.json`, using a subset (`agent_url`,
`agent_token`, `agent_enabled`, `whisper_model`, `input_device`) and ignoring
LLM/context keys. No schema change.

### Explicitly excluded from lite

Summarization, history/DB, meeting grouping, context files, instruction
profiles, LLM settings.

---

## Testing

- `diarize.py` merge logic: unit tests with synthetic segment lists covering
  each branch — system-silent (Me), echo (drop), double-talk (Me), no-system
  (untagged), no-mic (all Remote), and misaligned-offset cases.
- Alignment cross-correlation: test with a known injected offset.
- Recorder `get_source_files()`: verify sources survive `stop()` and are cleaned
  up after consumption.
- (No test suite exists today; these are the first. Manual QA for the UIs.)

## Out of scope (v1)

- Real-time (live) speaker tagging.
- Distinguishing individual remote participants or multiple in-room speakers
  (only Me-vs-Remote). A later phase could run diarization on just the remote
  stream, or move it server-side.
- Acoustic echo cancellation to produce clean per-speaker audio (we only need
  attribution, not clean audio).
- Speaker naming beyond generic Me/Remote labels.
