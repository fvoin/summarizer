# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A macOS desktop app ("Summarizer") that records meetings, transcribes audio locally via Whisper, and summarizes transcripts using cloud LLMs (Gemini, OpenAI, Anthropic) or local Ollama models. Distributed as a `.app` bundle via DMG.

## Build & Run

```bash
# Full build (creates .app + DMG in dist/)
./build.sh

# Run from source (requires .venv)
source .venv/bin/activate
python run.py
```

`build.sh` handles everything: venv creation, dependency install, ffmpeg download, Whisper model pre-download, PyInstaller bundling, codesigning, and DMG creation. There is also `build_intel.sh` for x86_64 builds.

Bump `APP_VERSION` in `summarizer/config.py` before each release — the GitHub release tag must match.

## Architecture

**Entry point**: `run.py` — sets up bundled resource paths (ffmpeg, whisper model) for PyInstaller, then calls `summarizer.app.main()`.

**Core modules** (all in `summarizer/`):

- `app.py` — PyQt6 GUI. Contains `MainWindow` (main recording/summarization UI), `SettingsDialog`, `SetupWizard` (multi-step first-run wizard), and all `QThread` workers (`TranscribeWorker`, `SummarizeWorker`, `RealtimeTranscribeWorker`, etc.). This is the largest file (~2800+ lines).
- `i18n.py` — Localization module. Detects macOS system language via `defaults read -g AppleLanguages`. Provides `t(key, **kwargs)` for string lookup and `locale()` returning `"ru"` or `"en"`. All UI strings are in a single `_STRINGS` dict with both language variants.
- `recorder.py` — `AudioRecorder` class. Records from mic (and loopback if BlackHole/similar detected). Has silence detection with auto-calibration, multi-device mixing via ffmpeg, and a real-time audio buffer (`get_all_rt_audio()`) for live transcription.
- `transcriber.py` — `Transcriber` class wrapping faster-whisper. Downloads models from HuggingFace (`Systran/faster-whisper-*`). Supports file transcription and numpy array transcription (for real-time). Module-level model cache avoids reloading.
- `summarizer.py` — LLM routing (`call_llm` dispatches to Gemini/Anthropic/OpenAI/Ollama based on model name), prompt building, summary formatting (Slack mrkdwn style), and context management (per-meeting-series context files with general + history sections).
- `config.py` — JSON config at `~/.summarizer/config.json`. Defines all defaults, model presets (cloud + local), Ollama integration, instruction profiles (with EN/RU variants for work and general meetings), and whisper model registry.
- `updater.py` — Checks GitHub Releases API (`fvoin/summarizer`) for new versions, downloads DMG.

**Key data flow**: Record → Transcribe (Whisper, local) → Summarize (LLM, cloud/local) → Display + save to context file.

**Real-time transcription**: During recording, `RealtimeTranscribeWorker` periodically reads accumulated audio from `AudioRecorder.get_all_rt_audio()` and runs incremental delta transcription via `_DeltaTranscribeWorker`.

**Config/data location**: `~/.summarizer/` (config.json, models/, recordings/, logs).

## Key Dependencies

- **PyQt6** — GUI framework
- **sounddevice + soundfile** — audio capture
- **faster-whisper + ctranslate2** — local speech-to-text
- **google-generativeai, openai, anthropic** — cloud LLM SDKs
- **PyInstaller** — app bundling

## Notes

- Tests live in `tests/` (pytest). Run with `source .venv/bin/activate && QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q`.
- The app requires microphone permission on macOS (set via entitlements.plist and Info.plist patching in build).
- ffmpeg is bundled as a static binary (downloaded during build) and also searched at system paths at runtime.
- Intel builds need `ctranslate2==4.6.0` pinned (no newer x86_64 wheels available).
- The app supports Russian localization (auto-detected from macOS system language). All UI strings are in `summarizer/i18n.py`. To add a new UI string, add it to `_STRINGS` dict with `en` and `ru` keys, then use `t("key_name")` in app.py.
- `generate_guide.py` produces the English PDF guide; `generate_guide_ru.py` produces the Russian version. Both require `reportlab`.
