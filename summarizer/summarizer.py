"""LLM summarization + context management.

LLM routing mirrors aidude Agent.run() — routes by model name to
Gemini / Anthropic / OpenAI SDK. Text-only, no image/video support needed.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config


import logging
_logger = logging.getLogger("summarizer")

def _log(msg: str):
    _logger.info(msg)


TRANSCRIPT_EXTENSIONS = {".txt", ".md", ".text", ".srt", ".vtt"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma", ".webm", ".mp4"}


# ── context I/O ──────────────────────────────────────────────────────────

_GENERAL_MARKER = "=== GENERAL ==="
_HISTORY_MARKER = "=== HISTORY ==="


def _parse_context_file(path: Path) -> tuple[str, str]:
    """Return (general_text, history_text) from a structured context file."""
    if not path.exists():
        return "", ""
    raw = path.read_text(encoding="utf-8")
    if _GENERAL_MARKER not in raw:
        return "", raw.strip()
    gen_start = raw.index(_GENERAL_MARKER) + len(_GENERAL_MARKER)
    if _HISTORY_MARKER in raw:
        hist_start = raw.index(_HISTORY_MARKER) + len(_HISTORY_MARKER)
        general = raw[gen_start:raw.index(_HISTORY_MARKER)].strip()
        history = raw[hist_start:].strip()
    else:
        general = raw[gen_start:].strip()
        history = ""
    return general, history


def _write_context_file(path: Path, general: str, history: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [_GENERAL_MARKER, general.strip(), "", _HISTORY_MARKER, history.strip()]
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def load_general_context(name: str) -> str:
    """Load only the GENERAL section of a context file."""
    path = config.get_recordings_dir() / f"{name}_context.txt"
    general, _ = _parse_context_file(path)
    return general


def save_general_context(name: str, general: str):
    """Save updated GENERAL section, preserving HISTORY."""
    rdir = config.get_recordings_dir()
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / f"{name}_context.txt"
    _, history = _parse_context_file(path)
    _write_context_file(path, general, history)


def create_context(name: str):
    """Create an empty context file if it doesn't exist."""
    rdir = config.get_recordings_dir()
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / f"{name}_context.txt"
    if not path.exists():
        _write_context_file(path, "", "")


def load_context_for_prompt(name: str, general_text: str, meeting_text: str) -> Optional[str]:
    """Build the context string for the LLM prompt.

    Always includes general_text + meeting_text in full.
    Fills remaining budget with history entries (newest first).
    """
    limit = config.load().get("context_limit", 5000)
    path = config.get_recordings_dir() / f"{name}_context.txt"
    _, history = _parse_context_file(path)

    parts = []
    budget = limit

    if general_text:
        parts.append(f"General context:\n{general_text}")
        budget -= len(parts[-1])
    if meeting_text:
        parts.append(f"This meeting context:\n{meeting_text}")
        budget -= len(parts[-1])

    if history and budget > 0:
        trimmed = history
        if len(trimmed) > budget:
            trimmed = trimmed[:budget]
            cut = trimmed.rfind("\n[")
            if cut > 0:
                trimmed = trimmed[:cut]
        if trimmed.strip():
            parts.append(f"Previous meetings:\n{trimmed.strip()}")

    return "\n\n".join(parts) if parts else None


def save_to_context(name: str, summary: str, general_text: str = "",
                    meeting_text: str = ""):
    rdir = config.get_recordings_dir()
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / f"{name}_context.txt"
    _, old_history = _parse_context_file(path)

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry_parts = [f"[{date_str}]"]
    if meeting_text:
        entry_parts.append(f"Meeting context: {meeting_text}")
    entry_parts.append(f"Summary: {summary}")
    new_entry = "\n".join(entry_parts)

    history = f"{new_entry}\n\n{old_history}".strip() if old_history else new_entry
    _write_context_file(path, general_text, history)


def update_latest_context_entry(name: str, new_summary: str):
    """Replace the Summary field in the most recent history entry."""
    rdir = config.get_recordings_dir()
    path = rdir / f"{name}_context.txt"
    general, history = _parse_context_file(path)
    if not history:
        return
    # Find the first "Summary:" line in history and replace until next entry
    import re
    updated = re.sub(
        r"(Summary:)(.+?)(\n\n\[|\Z)",
        lambda m: m.group(1) + " " + new_summary.strip() + "\n" + m.group(3),
        history,
        count=1,
        flags=re.DOTALL,
    )
    _write_context_file(path, general, updated)


def list_contexts() -> list[str]:
    rdir = config.get_recordings_dir()
    if not rdir.exists():
        return []
    names = []
    for p in sorted(rdir.glob("*_context.txt")):
        name = p.stem.removesuffix("_context")
        if name:
            names.append(name)
    return names


# ── prompt building ──────────────────────────────────────────────────────

def build_prompt(
    transcript: str,
    prior_context: Optional[str] = None,
    duration_seconds: Optional[int] = None,
) -> str:
    cfg = config.load()
    instructions = cfg.get("instructions", config.DEFAULT_INSTRUCTIONS)

    duration_line = ""
    if duration_seconds and duration_seconds > 0:
        mins, secs = divmod(duration_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            duration_str = f"{hours}h {mins}m {secs}s"
        elif mins:
            duration_str = f"{mins}m {secs}s"
        else:
            duration_str = f"{secs}s"
        duration_line = f"Meeting duration: {duration_str}\n"

    context_block = ""
    if prior_context:
        context_block = f"""
PRIOR CONTEXT (summaries of previous conversations on the same topic):
{prior_context}

Use this context to understand ongoing topics, track progress on action items, and note any changes or new developments compared to previous conversations.
"""

    return f"""{instructions}

{duration_line}Transcript:
{transcript}
{context_block}
IMPORTANT: Write the summary in the SAME LANGUAGE as the transcript above. If the transcript is in Russian, write the summary in Russian. If it's in English, write in English.

If you can identify different speakers or perspectives in the conversation, please note that."""


def format_summary(text: str) -> str:
    """Convert markdown bold/headers to Slack mrkdwn and strip invisible chars."""
    text = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)
    return text.strip()


# ── LLM call ─────────────────────────────────────────────────────────────

def _call_gemini(model_name: str, system: str, user_text: str) -> str:
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Configure it in Settings.")
    genai.configure(api_key=api_key, transport="rest")
    model = genai.GenerativeModel(model_name, system_instruction=system)
    response = model.generate_content(user_text)
    return response.text


def _call_anthropic(model_name: str, system: str, user_text: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model_name,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_text}],
    )
    return response.content[0].text


def _call_openai(model_name: str, system: str, user_text: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    )
    return resp.choices[0].message.content.strip()


def _call_ollama(model_name: str, system: str, user_text: str) -> str:
    from openai import OpenAI
    ollama = config.find_ollama()
    if ollama:
        config.ensure_ollama_server(ollama)
    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
    )
    return resp.choices[0].message.content.strip()


def call_llm(prompt: str, model: Optional[str] = None, profile_name: str = "") -> str:
    cfg = config.load()
    config.apply_env(cfg)
    if model is None:
        model = cfg.get("model", "gemini-2.5-pro")
    if profile_name:
        instructions = config.get_profile(profile_name)
    else:
        instructions = cfg.get("instructions", config.DEFAULT_INSTRUCTIONS)

    _log(f"Calling LLM model={model} prompt_len={len(prompt)}")

    m = model.lower()
    if m in config.LOCAL_LLM_MODELS or "ollama:" in m:
        return _call_ollama(model, instructions, prompt)
    if "gemini" in m:
        return _call_gemini(model, instructions, prompt)
    if "claude" in m:
        return _call_anthropic(model, instructions, prompt)
    return _call_openai(model, instructions, prompt)


# ── high-level summarize ─────────────────────────────────────────────────

def summarize(
    transcript: str,
    context_name: Optional[str] = None,
    general_text: str = "",
    meeting_text: str = "",
    profile_name: str = "",
    duration_seconds: Optional[int] = None,
) -> str:
    """Build prompt, call LLM, save context, return formatted summary.

    - general_text: persistent info about this meeting series (always included)
    - meeting_text: agenda / details for this particular meeting (always included)
    - context_name: if set, loads history from file and saves new entry back
    """
    prior = None
    if context_name:
        prior = load_context_for_prompt(context_name, general_text, meeting_text)
    else:
        parts = []
        if general_text:
            parts.append(f"General context:\n{general_text}")
        if meeting_text:
            parts.append(f"This meeting context:\n{meeting_text}")
        prior = "\n\n".join(parts) if parts else None

    prompt = build_prompt(transcript, prior, duration_seconds=duration_seconds)
    raw = call_llm(prompt, profile_name=profile_name)
    summary = format_summary(raw)

    if context_name:
        try:
            save_to_context(context_name, summary, general_text=general_text,
                            meeting_text=meeting_text)
        except Exception as e:
            _log(f"Failed to save context: {e}")

    return summary
