import json
import logging
import os
from pathlib import Path
from typing import Optional, List

APP_VERSION = "1.10"

_CONFIG_DIR = Path.home() / ".summarizer"
_CONFIG_FILE = _CONFIG_DIR / "config.json"
_LOG_FILE = _CONFIG_DIR / "summarizer.log"


def get_log_path() -> Path:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_FILE


def setup_logging():
    from logging.handlers import RotatingFileHandler
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        str(_LOG_FILE), maxBytes=2 * 1024 * 1024, backupCount=1, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

DEFAULT_INSTRUCTIONS = (
    "You are a professional meeting analyst. Produce a structured, actionable summary of the transcript below.\n"
    "\n"
    "Output exactly these sections in order, using the emoji + bold header format shown:\n"
    "\n"
    "\U0001f5d2\ufe0f *Overview*\n"
    "\u2022 One sentence: meeting purpose and main outcome.\n"
    "\n"
    "\U0001f3af *Key Decisions*\n"
    "\u2022 Each confirmed decision, stated as a fact.\n"
    "\u2022 If none \u2014 omit this section entirely.\n"
    "\n"
    "\u2705 *Action Items*\n"
    "\u2022 Format: *Owner* \u2014 task \u2014 _deadline if mentioned_\n"
    "\u2022 If owner is unclear, write _unassigned_.\n"
    "\u2022 If none \u2014 omit this section entirely.\n"
    "\n"
    "\U0001f4ac *Key Discussion Points*\n"
    "\u2022 Important topics discussed, options considered, problems raised.\n"
    "\u2022 Focus on substance \u2014 skip small talk and repetition.\n"
    "\n"
    "\u26a0\ufe0f *Risks & Open Questions*\n"
    "\u2022 Unresolved issues, blockers, things that need follow-up.\n"
    "\u2022 If none \u2014 omit this section entirely.\n"
    "\n"
    "\U0001f4ca *Meeting Score*\n"
    "\u2022 *Efficiency*: X/10 \u2014 one-line reason\n"
    "\u2022 *Agenda*: how well goals/agenda were met (skip if no agenda was mentioned)\n"
    "\u2022 *Next steps clarity*: brief comment on who/what/when coverage\n"
    "\u2022 *Cost estimate*: [duration]h \u00d7 [N] participants \u00d7 50 EUR = ~X EUR\n"
    "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    "FORMATTING RULES \u2014 follow exactly, no exceptions:\n"
    "\u2022 Bullet points use \u2022 only \u2014 never -, *, or numbers\n"
    "\u2022 Bold uses *asterisks* \u2014 for names, decisions, owners, key terms\n"
    "\u2022 Italic uses _underscores_ \u2014 for dates, deadlines, qualifiers\n"
    "\u2022 NO markdown: no # headers, no ** double asterisks, no __ double underscores\n"
    "\u2022 NO filler openers (\u201cThe meeting covered...\u201d, \u201cIn summary...\u201d) \u2014 start each bullet with the content\n"
    "\u2022 One idea per bullet\n"
    "\u2022 Section header format: emoji + space + *Bold Title* \u2014 nothing else on that line"
)

DEFAULT_PROFILE_NAME = "Default"

_DEFAULTS = {
    "model": "gemini-3-flash-preview",
    "api_key": "",
    "base_url": "",
    "instructions": DEFAULT_INSTRUCTIONS,
    "active_profile": DEFAULT_PROFILE_NAME,
    "instruction_profiles": {DEFAULT_PROFILE_NAME: DEFAULT_INSTRUCTIONS},
    "whisper_model": "base",
    "save_audio": False,
    "context_limit": 5000,
    "silence_timeout": 30,
    "input_device": None,
    "recordings_dir": "",
}

WHISPER_MODELS = {
    "tiny":     {"repo": "Systran/faster-whisper-tiny",     "size_mb": 75,   "quality": "Basic"},
    "base":     {"repo": "Systran/faster-whisper-base",     "size_mb": 145,  "quality": "Good"},
    "small":    {"repo": "Systran/faster-whisper-small",    "size_mb": 465,  "quality": "Better"},
    "medium":   {"repo": "Systran/faster-whisper-medium",   "size_mb": 1500, "quality": "Great"},
    "large-v3": {"repo": "Systran/faster-whisper-large-v3", "size_mb": 3100, "quality": "Best"},
}


def _ensure_dir():
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    _ensure_dir()
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = {**_DEFAULTS, **data}
            return merged
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(cfg: dict):
    _ensure_dir()
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_recordings_dir() -> Path:
    cfg = load()
    custom = cfg.get("recordings_dir", "").strip()
    if custom and Path(custom).is_dir():
        return Path(custom)
    default = _CONFIG_DIR / "recordings"
    default.mkdir(parents=True, exist_ok=True)
    return default


def get_models_dir() -> Path:
    d = _CONFIG_DIR / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_model_path(model_name: str) -> Optional[Path]:
    """Return local path if the model is downloaded, else None.

    Checks in order:
    1. Bundled model dir (WHISPER_MODEL_DIR env, only for the bundled model)
    2. Local cache ~/.summarizer/models/<name>/
    """
    bundled = os.environ.get("WHISPER_MODEL_DIR", "")
    if bundled and os.path.isdir(bundled):
        bundled_marker = Path(bundled) / "model.bin"
        if bundled_marker.exists():
            bundled_name = _detect_bundled_model_name(bundled)
            if bundled_name == model_name:
                return Path(bundled)

    local = get_models_dir() / model_name
    marker = local / "model.bin"
    if marker.exists():
        return local
    return None


def _detect_bundled_model_name(bundled_path: str) -> Optional[str]:
    """Try to detect which model is in the bundled dir by checking config.json."""
    cfg_file = Path(bundled_path) / "config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r") as f:
                data = json.load(f)
            for name, info in WHISPER_MODELS.items():
                if info["repo"] in data.get("_name_or_path", ""):
                    return name
        except Exception:
            pass
    # Fallback: check directory size heuristics
    total_mb = sum(f.stat().st_size for f in Path(bundled_path).rglob("*") if f.is_file()) / (1024 * 1024)
    if total_mb < 100:
        return "tiny"
    if total_mb < 300:
        return "base"
    if total_mb < 1000:
        return "small"
    if total_mb < 2500:
        return "medium"
    return "large-v3"


def is_model_downloaded(model_name: str) -> bool:
    return get_model_path(model_name) is not None


def list_downloaded_models() -> List[str]:
    result = []
    for name in WHISPER_MODELS:
        if is_model_downloaded(name):
            result.append(name)
    return result


def is_model_bundled(model_name: str) -> bool:
    """Return True if the model is in the app bundle (cannot be deleted)."""
    bundled = os.environ.get("WHISPER_MODEL_DIR", "")
    if not bundled:
        return False
    p = get_model_path(model_name)
    return p is not None and str(p).startswith(bundled)


def delete_whisper_model(model_name: str):
    if is_model_bundled(model_name):
        raise RuntimeError("This is the bundled model — it cannot be deleted.")
    local = get_models_dir() / model_name
    if local.exists():
        import shutil
        shutil.rmtree(local)
    else:
        raise RuntimeError(f"Model '{model_name}' not found in local cache.")


# ── Cloud LLM presets ─────────────────────────────────────────────────────

CLOUD_LLM_PRESETS = [
    ("gemini-3-flash-preview",   "Gemini 3 Flash Preview"),
    ("gemini-2.5-pro",           "Gemini 2.5 Pro"),
    ("gpt-5-mini",               "GPT-5 mini"),
    ("gpt-5.4",                  "GPT-5.4"),
]


# ── Local LLM models (Ollama) ─────────────────────────────────────────────

LOCAL_LLM_MODELS = {
    "glm4:9b": {
        "display": "GLM-4 9B",
        "size_gb": 5.5,
        "quality": "Good",
        "ollama_name": "glm4:9b",
    },
    "gemma3:12b-it-qat": {
        "display": "Gemma 3 12B QAT",
        "size_gb": 8.9,
        "quality": "Better",
        "ollama_name": "gemma3:12b-it-qat",
    },
    "gemma3:27b-it-qat": {
        "display": "Gemma 3 27B QAT",
        "size_gb": 18.0,
        "quality": "Best (24+ GB RAM)",
        "ollama_name": "gemma3:27b-it-qat",
    },
}


def find_ollama() -> Optional[str]:
    """Return full path to ollama binary, or None."""
    import subprocess
    candidates = [
        "/opt/homebrew/bin/ollama",
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        os.path.expanduser("~/.ollama/bin/ollama"),
        "ollama",
    ]
    for path in candidates:
        try:
            r = subprocess.run([path, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return path
        except Exception:
            continue
    return None


def is_ollama_available() -> bool:
    return find_ollama() is not None


def ensure_ollama_server(ollama_bin: str):
    """Start ollama serve in background if not already running."""
    import subprocess
    import time
    r = subprocess.run([ollama_bin, "list"], capture_output=True, timeout=5)
    if r.returncode == 0:
        return  # already running
    subprocess.Popen(
        [ollama_bin, "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(2)  # give it a moment to start


def list_ollama_models() -> list[str]:
    """Return list of locally pulled ollama model names."""
    import subprocess
    ollama = find_ollama()
    if not ollama:
        return []
    try:
        r = subprocess.run([ollama, "list"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().splitlines()[1:]  # skip header
        return [line.split()[0] for line in lines if line.strip()]
    except Exception:
        return []


def is_local_llm_downloaded(model_key: str) -> bool:
    info = LOCAL_LLM_MODELS.get(model_key)
    if not info:
        return False
    pulled = list_ollama_models()
    name = info["ollama_name"]
    return name in pulled


def delete_local_llm(model_key: str):
    import subprocess
    ollama = find_ollama()
    info = LOCAL_LLM_MODELS.get(model_key)
    if ollama and info:
        subprocess.run([ollama, "rm", info["ollama_name"]], capture_output=True)


def get_api_key_env_var(model: str) -> str:
    """Return the env var name for the given model."""
    m = model.lower()
    if "gemini" in m:
        return "GEMINI_API_KEY"
    if "claude" in m:
        return "ANTHROPIC_API_KEY"
    return "OPENAI_API_KEY"


def list_profiles() -> list[str]:
    cfg = load()
    profiles = cfg.get("instruction_profiles", {})
    if not profiles:
        return [DEFAULT_PROFILE_NAME]
    return list(profiles.keys())


def get_profile(name: str) -> str:
    cfg = load()
    profiles = cfg.get("instruction_profiles", {})
    return profiles.get(name, DEFAULT_INSTRUCTIONS)


def save_profile(name: str, text: str):
    cfg = load()
    profiles = cfg.get("instruction_profiles", {})
    profiles[name] = text
    cfg["instruction_profiles"] = profiles
    save(cfg)


def delete_profile(name: str):
    cfg = load()
    profiles = cfg.get("instruction_profiles", {})
    profiles.pop(name, None)
    if not profiles:
        profiles[DEFAULT_PROFILE_NAME] = DEFAULT_INSTRUCTIONS
    cfg["instruction_profiles"] = profiles
    if cfg.get("active_profile") == name:
        cfg["active_profile"] = next(iter(profiles))
        cfg["instructions"] = profiles[cfg["active_profile"]]
    save(cfg)


def apply_env(cfg: Optional[dict] = None):
    """Set env vars from config so SDKs pick them up."""
    if cfg is None:
        cfg = load()
    api_key = cfg.get("api_key", "").strip()
    if not api_key:
        return
    env_var = get_api_key_env_var(cfg.get("model", ""))
    os.environ[env_var] = api_key
    base_url = cfg.get("base_url", "").strip()
    if base_url:
        os.environ["OPENAI_BASE_URL"] = base_url
