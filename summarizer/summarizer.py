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

def load_context(name: str) -> Optional[str]:
    path = config.get_recordings_dir() / f"{name}_context.txt"
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        limit = config.load().get("context_limit", 5000)
        if limit and len(content) > limit:
            content = content[-limit:]
            cut = content.find("\n")
            if cut > 0:
                content = content[cut + 1:]
        return content
    return None


def save_to_context(name: str, summary: str, quick_context: Optional[str] = None):
    rdir = config.get_recordings_dir()
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / f"{name}_context.txt"
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [f"\n\n--- {date_str} ---"]
    if quick_context:
        parts.append(f"Quick context: {quick_context}")
    parts.append(summary)
    entry = "\n".join(parts)
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)


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


def call_llm(prompt: str, model: Optional[str] = None) -> str:
    cfg = config.load()
    config.apply_env(cfg)
    if model is None:
        model = cfg.get("model", "gemini-2.5-pro")
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
    context_inline: Optional[str] = None,
    duration_seconds: Optional[int] = None,
) -> str:
    """Build prompt, call LLM, save context, return formatted summary.

    Both context_name and context_inline can be provided simultaneously:
    - context_name: loads prior summaries from file, saves new summary back
    - context_inline: quick context always included in the prompt
    """
    parts = []
    if context_name:
        file_ctx = load_context(context_name)
        if file_ctx:
            parts.append(file_ctx)
    if context_inline:
        parts.append(context_inline)

    prior = "\n\n".join(parts) if parts else None

    prompt = build_prompt(transcript, prior, duration_seconds=duration_seconds)
    raw = call_llm(prompt)
    summary = format_summary(raw)

    if context_name:
        try:
            save_to_context(context_name, summary, quick_context=context_inline)
        except Exception as e:
            _log(f"Failed to save context: {e}")

    return summary
