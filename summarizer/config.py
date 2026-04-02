import json
import logging
import os
from pathlib import Path
from typing import Optional, List

_logger = logging.getLogger("config")

APP_VERSION = "1.16.4"

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

GENERAL_MEETING_INSTRUCTIONS = (
    "You are a helpful meeting assistant. Summarize the transcript below in a clear, concise format.\n"
    "\n"
    "Output these sections (skip any that don't apply):\n"
    "\n"
    "\U0001f5d2\ufe0f *Overview*\n"
    "\u2022 One or two sentences: what this conversation was about and the main outcome.\n"
    "\n"
    "\U0001f4ac *Key Points*\n"
    "\u2022 The most important topics discussed, ideas shared, or conclusions reached.\n"
    "\u2022 Focus on substance \u2014 skip greetings and filler.\n"
    "\n"
    "\u2705 *Follow-ups*\n"
    "\u2022 Anything that was agreed on or needs to be done next.\n"
    "\u2022 If none \u2014 omit this section.\n"
    "\n"
    "\U0001f4a1 *Takeaways*\n"
    "\u2022 Key insights, interesting ideas, or notable quotes.\n"
    "\u2022 If none \u2014 omit this section.\n"
    "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    "FORMATTING RULES \u2014 follow exactly, no exceptions:\n"
    "\u2022 Bullet points use \u2022 only \u2014 never -, *, or numbers\n"
    "\u2022 Bold uses *asterisks* \u2014 for names, key terms\n"
    "\u2022 Italic uses _underscores_ \u2014 for dates, qualifiers\n"
    "\u2022 NO markdown: no # headers, no ** double asterisks, no __ double underscores\n"
    "\u2022 NO filler openers \u2014 start each bullet with the content\n"
    "\u2022 One idea per bullet\n"
    "\u2022 Section header format: emoji + space + *Bold Title* \u2014 nothing else on that line"
)

DEFAULT_INSTRUCTIONS_RU = (
    "\u0422\u044b \u2014 \u043f\u0440\u043e\u0444\u0435\u0441\u0441\u0438\u043e\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0430\u043d\u0430\u043b\u0438\u0442\u0438\u043a \u0432\u0441\u0442\u0440\u0435\u0447. \u0421\u043e\u0441\u0442\u0430\u0432\u044c \u0441\u0442\u0440\u0443\u043a\u0442\u0443\u0440\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435, \u043f\u0440\u0430\u043a\u0442\u0438\u0447\u043d\u043e\u0435 \u0440\u0435\u0437\u044e\u043c\u0435 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442\u0430 \u043d\u0438\u0436\u0435.\n"
    "\n"
    "\u0412\u044b\u0432\u0435\u0434\u0438 \u0440\u043e\u0432\u043d\u043e \u044d\u0442\u0438 \u0440\u0430\u0437\u0434\u0435\u043b\u044b \u043f\u043e \u043f\u043e\u0440\u044f\u0434\u043a\u0443, \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u044f \u0444\u043e\u0440\u043c\u0430\u0442 \u044d\u043c\u043e\u0434\u0437\u0438 + \u0436\u0438\u0440\u043d\u044b\u0439 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a:\n"
    "\n"
    "\U0001f5d2\ufe0f *\u041e\u0431\u0437\u043e\u0440*\n"
    "\u2022 \u041e\u0434\u043d\u043e \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u0435: \u0446\u0435\u043b\u044c \u0432\u0441\u0442\u0440\u0435\u0447\u0438 \u0438 \u043e\u0441\u043d\u043e\u0432\u043d\u043e\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442.\n"
    "\n"
    "\U0001f3af *\u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u044f*\n"
    "\u2022 \u041a\u0430\u0436\u0434\u043e\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0451\u043d\u043d\u043e\u0435 \u0440\u0435\u0448\u0435\u043d\u0438\u0435, \u0441\u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435 \u043a\u0430\u043a \u0444\u0430\u043a\u0442.\n"
    "\u2022 \u0415\u0441\u043b\u0438 \u043d\u0435\u0442 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 \u044d\u0442\u043e\u0442 \u0440\u0430\u0437\u0434\u0435\u043b.\n"
    "\n"
    "\u2705 *\u0417\u0430\u0434\u0430\u0447\u0438*\n"
    "\u2022 \u0424\u043e\u0440\u043c\u0430\u0442: *\u041e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0439* \u2014 \u0437\u0430\u0434\u0430\u0447\u0430 \u2014 _\u0434\u0435\u0434\u043b\u0430\u0439\u043d, \u0435\u0441\u043b\u0438 \u0443\u043a\u0430\u0437\u0430\u043d_\n"
    "\u2022 \u0415\u0441\u043b\u0438 \u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0439 \u043d\u0435 \u044f\u0441\u0435\u043d, \u043f\u0438\u0448\u0438 _\u043d\u0435 \u043d\u0430\u0437\u043d\u0430\u0447\u0435\u043d_.\n"
    "\u2022 \u0415\u0441\u043b\u0438 \u043d\u0435\u0442 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 \u044d\u0442\u043e\u0442 \u0440\u0430\u0437\u0434\u0435\u043b.\n"
    "\n"
    "\U0001f4ac *\u041e\u0441\u043d\u043e\u0432\u043d\u044b\u0435 \u0442\u0435\u043c\u044b \u043e\u0431\u0441\u0443\u0436\u0434\u0435\u043d\u0438\u044f*\n"
    "\u2022 \u0412\u0430\u0436\u043d\u044b\u0435 \u0442\u0435\u043c\u044b, \u0440\u0430\u0441\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u043d\u044b\u0435 \u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b, \u043f\u043e\u0434\u043d\u044f\u0442\u044b\u0435 \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u044b.\n"
    "\u2022 \u0424\u043e\u043a\u0443\u0441 \u043d\u0430 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0438 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 small talk \u0438 \u043f\u043e\u0432\u0442\u043e\u0440\u044b.\n"
    "\n"
    "\u26a0\ufe0f *\u0420\u0438\u0441\u043a\u0438 \u0438 \u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b*\n"
    "\u2022 \u041d\u0435\u0440\u0435\u0448\u0451\u043d\u043d\u044b\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b, \u0431\u043b\u043e\u043a\u0435\u0440\u044b, \u0447\u0442\u043e \u0442\u0440\u0435\u0431\u0443\u0435\u0442 \u0434\u0430\u043b\u044c\u043d\u0435\u0439\u0448\u0438\u0445 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0439.\n"
    "\u2022 \u0415\u0441\u043b\u0438 \u043d\u0435\u0442 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 \u044d\u0442\u043e\u0442 \u0440\u0430\u0437\u0434\u0435\u043b.\n"
    "\n"
    "\U0001f4ca *\u041e\u0446\u0435\u043d\u043a\u0430 \u0432\u0441\u0442\u0440\u0435\u0447\u0438*\n"
    "\u2022 *\u042d\u0444\u0444\u0435\u043a\u0442\u0438\u0432\u043d\u043e\u0441\u0442\u044c*: X/10 \u2014 \u043a\u0440\u0430\u0442\u043a\u043e\u0435 \u043e\u0431\u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0435\n"
    "\u2022 *\u041f\u043e\u0432\u0435\u0441\u0442\u043a\u0430*: \u043d\u0430\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0434\u043e\u0441\u0442\u0438\u0433\u043d\u0443\u0442\u044b \u0446\u0435\u043b\u0438 (\u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438, \u0435\u0441\u043b\u0438 \u043f\u043e\u0432\u0435\u0441\u0442\u043a\u0438 \u043d\u0435 \u0431\u044b\u043b\u043e)\n"
    "\u2022 *\u0414\u0430\u043b\u044c\u043d\u0435\u0439\u0448\u0438\u0435 \u0448\u0430\u0433\u0438*: \u043a\u043e\u043c\u043c\u0435\u043d\u0442\u0430\u0440\u0438\u0439 \u043f\u043e \u043f\u043e\u043a\u0440\u044b\u0442\u0438\u044e \u043a\u0442\u043e/\u0447\u0442\u043e/\u043a\u043e\u0433\u0434\u0430\n"
    "\u2022 *\u041e\u0446\u0435\u043d\u043a\u0430 \u0441\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u0438*: [\u0434\u043b\u0438\u0442\u0435\u043b\u044c\u043d\u043e\u0441\u0442\u044c]\u0447 \u00d7 [N] \u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a\u043e\u0432 \u00d7 50 EUR = ~X EUR\n"
    "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    "\u041f\u0420\u0410\u0412\u0418\u041b\u0410 \u0424\u041e\u0420\u041c\u0410\u0422\u0418\u0420\u041e\u0412\u0410\u041d\u0418\u042f \u2014 \u0441\u043e\u0431\u043b\u044e\u0434\u0430\u0439 \u0431\u0435\u0437 \u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0439:\n"
    "\u2022 \u041c\u0430\u0440\u043a\u0435\u0440\u044b \u0441\u043f\u0438\u0441\u043a\u0430 \u2014 \u0442\u043e\u043b\u044c\u043a\u043e \u2022 \u2014 \u043d\u0438\u043a\u0430\u043a\u0438\u0445 -, *, \u0446\u0438\u0444\u0440\n"
    "\u2022 \u0416\u0438\u0440\u043d\u044b\u0439 \u2014 *\u0437\u0432\u0451\u0437\u0434\u043e\u0447\u043a\u0438* \u2014 \u0434\u043b\u044f \u0438\u043c\u0451\u043d, \u0440\u0435\u0448\u0435\u043d\u0438\u0439, \u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0435\u043d\u043d\u044b\u0445, \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0445 \u0442\u0435\u0440\u043c\u0438\u043d\u043e\u0432\n"
    "\u2022 \u041a\u0443\u0440\u0441\u0438\u0432 \u2014 _\u043f\u043e\u0434\u0447\u0451\u0440\u043a\u0438\u0432\u0430\u043d\u0438\u044f_ \u2014 \u0434\u043b\u044f \u0434\u0430\u0442, \u0434\u0435\u0434\u043b\u0430\u0439\u043d\u043e\u0432, \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u0438\u0439\n"
    "\u2022 \u0411\u0415\u0417 markdown: \u0431\u0435\u0437 # \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u043e\u0432, \u0431\u0435\u0437 ** \u0434\u0432\u043e\u0439\u043d\u044b\u0445 \u0437\u0432\u0451\u0437\u0434\u043e\u0447\u0435\u043a, \u0431\u0435\u0437 __ \u0434\u0432\u043e\u0439\u043d\u044b\u0445 \u043f\u043e\u0434\u0447\u0451\u0440\u043a\u0438\u0432\u0430\u043d\u0438\u0439\n"
    "\u2022 \u0411\u0415\u0417 \u0432\u0432\u043e\u0434\u043d\u044b\u0445 \u0444\u0440\u0430\u0437 \u2014 \u043d\u0430\u0447\u0438\u043d\u0430\u0439 \u043a\u0430\u0436\u0434\u044b\u0439 \u043f\u0443\u043d\u043a\u0442 \u0441 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u044f\n"
    "\u2022 \u041e\u0434\u043d\u0430 \u043c\u044b\u0441\u043b\u044c \u043d\u0430 \u043f\u0443\u043d\u043a\u0442\n"
    "\u2022 \u0424\u043e\u0440\u043c\u0430\u0442 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u0430 \u0440\u0430\u0437\u0434\u0435\u043b\u0430: \u044d\u043c\u043e\u0434\u0437\u0438 + \u043f\u0440\u043e\u0431\u0435\u043b + *\u0416\u0438\u0440\u043d\u044b\u0439 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a* \u2014 \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0430 \u044d\u0442\u043e\u0439 \u0441\u0442\u0440\u043e\u043a\u0435"
)

GENERAL_MEETING_INSTRUCTIONS_RU = (
    "\u0422\u044b \u2014 \u043f\u043e\u043b\u0435\u0437\u043d\u044b\u0439 \u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a \u0434\u043b\u044f \u0432\u0441\u0442\u0440\u0435\u0447. \u041f\u043e\u0434\u0432\u0435\u0434\u0438 \u0438\u0442\u043e\u0433 \u0442\u0440\u0430\u043d\u0441\u043a\u0440\u0438\u043f\u0442\u0430 \u043d\u0438\u0436\u0435 \u0432 \u043f\u043e\u043d\u044f\u0442\u043d\u043e\u043c \u0438 \u043b\u0430\u043a\u043e\u043d\u0438\u0447\u043d\u043e\u043c \u0444\u043e\u0440\u043c\u0430\u0442\u0435.\n"
    "\n"
    "\u0412\u044b\u0432\u0435\u0434\u0438 \u044d\u0442\u0438 \u0440\u0430\u0437\u0434\u0435\u043b\u044b (\u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 \u043d\u0435\u043f\u043e\u0434\u0445\u043e\u0434\u044f\u0449\u0438\u0435):\n"
    "\n"
    "\U0001f5d2\ufe0f *\u041e\u0431\u0437\u043e\u0440*\n"
    "\u2022 \u041e\u0434\u043d\u043e-\u0434\u0432\u0430 \u043f\u0440\u0435\u0434\u043b\u043e\u0436\u0435\u043d\u0438\u044f: \u043e \u0447\u0451\u043c \u0431\u044b\u043b \u0440\u0430\u0437\u0433\u043e\u0432\u043e\u0440 \u0438 \u0433\u043b\u0430\u0432\u043d\u044b\u0439 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442.\n"
    "\n"
    "\U0001f4ac *\u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u043c\u043e\u043c\u0435\u043d\u0442\u044b*\n"
    "\u2022 \u0421\u0430\u043c\u044b\u0435 \u0432\u0430\u0436\u043d\u044b\u0435 \u0442\u0435\u043c\u044b, \u0438\u0434\u0435\u0438 \u0438\u043b\u0438 \u0432\u044b\u0432\u043e\u0434\u044b.\n"
    "\u2022 \u0424\u043e\u043a\u0443\u0441 \u043d\u0430 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u0438 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 \u043f\u0440\u0438\u0432\u0435\u0442\u0441\u0442\u0432\u0438\u044f \u0438 \u043b\u0438\u0448\u043d\u0435\u0435.\n"
    "\n"
    "\u2705 *\u0414\u0430\u043b\u044c\u043d\u0435\u0439\u0448\u0438\u0435 \u0448\u0430\u0433\u0438*\n"
    "\u2022 \u0427\u0442\u043e \u0431\u044b\u043b\u043e \u0441\u043e\u0433\u043b\u0430\u0441\u043e\u0432\u0430\u043d\u043e \u0438\u043b\u0438 \u0447\u0442\u043e \u043d\u0443\u0436\u043d\u043e \u0441\u0434\u0435\u043b\u0430\u0442\u044c \u0434\u0430\u043b\u044c\u0448\u0435.\n"
    "\u2022 \u0415\u0441\u043b\u0438 \u043d\u0435\u0442 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 \u044d\u0442\u043e\u0442 \u0440\u0430\u0437\u0434\u0435\u043b.\n"
    "\n"
    "\U0001f4a1 *\u0412\u044b\u0432\u043e\u0434\u044b*\n"
    "\u2022 \u041a\u043b\u044e\u0447\u0435\u0432\u044b\u0435 \u0438\u0434\u0435\u0438, \u0438\u043d\u0442\u0435\u0440\u0435\u0441\u043d\u044b\u0435 \u043c\u044b\u0441\u043b\u0438 \u0438\u043b\u0438 \u0437\u0430\u043c\u0435\u0442\u043d\u044b\u0435 \u0446\u0438\u0442\u0430\u0442\u044b.\n"
    "\u2022 \u0415\u0441\u043b\u0438 \u043d\u0435\u0442 \u2014 \u043f\u0440\u043e\u043f\u0443\u0441\u0442\u0438 \u044d\u0442\u043e\u0442 \u0440\u0430\u0437\u0434\u0435\u043b.\n"
    "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    "\u041f\u0420\u0410\u0412\u0418\u041b\u0410 \u0424\u041e\u0420\u041c\u0410\u0422\u0418\u0420\u041e\u0412\u0410\u041d\u0418\u042f \u2014 \u0441\u043e\u0431\u043b\u044e\u0434\u0430\u0439 \u0431\u0435\u0437 \u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0439:\n"
    "\u2022 \u041c\u0430\u0440\u043a\u0435\u0440\u044b \u0441\u043f\u0438\u0441\u043a\u0430 \u2014 \u0442\u043e\u043b\u044c\u043a\u043e \u2022 \u2014 \u043d\u0438\u043a\u0430\u043a\u0438\u0445 -, *, \u0446\u0438\u0444\u0440\n"
    "\u2022 \u0416\u0438\u0440\u043d\u044b\u0439 \u2014 *\u0437\u0432\u0451\u0437\u0434\u043e\u0447\u043a\u0438* \u2014 \u0434\u043b\u044f \u0438\u043c\u0451\u043d, \u043a\u043b\u044e\u0447\u0435\u0432\u044b\u0445 \u0442\u0435\u0440\u043c\u0438\u043d\u043e\u0432\n"
    "\u2022 \u041a\u0443\u0440\u0441\u0438\u0432 \u2014 _\u043f\u043e\u0434\u0447\u0451\u0440\u043a\u0438\u0432\u0430\u043d\u0438\u044f_ \u2014 \u0434\u043b\u044f \u0434\u0430\u0442, \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u0438\u0439\n"
    "\u2022 \u0411\u0415\u0417 markdown: \u0431\u0435\u0437 # \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u043e\u0432, \u0431\u0435\u0437 ** \u0434\u0432\u043e\u0439\u043d\u044b\u0445 \u0437\u0432\u0451\u0437\u0434\u043e\u0447\u0435\u043a, \u0431\u0435\u0437 __ \u0434\u0432\u043e\u0439\u043d\u044b\u0445 \u043f\u043e\u0434\u0447\u0451\u0440\u043a\u0438\u0432\u0430\u043d\u0438\u0439\n"
    "\u2022 \u0411\u0415\u0417 \u0432\u0432\u043e\u0434\u043d\u044b\u0445 \u0444\u0440\u0430\u0437 \u2014 \u043d\u0430\u0447\u0438\u043d\u0430\u0439 \u043a\u0430\u0436\u0434\u044b\u0439 \u043f\u0443\u043d\u043a\u0442 \u0441 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u043d\u0438\u044f\n"
    "\u2022 \u041e\u0434\u043d\u0430 \u043c\u044b\u0441\u043b\u044c \u043d\u0430 \u043f\u0443\u043d\u043a\u0442\n"
    "\u2022 \u0424\u043e\u0440\u043c\u0430\u0442 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043a\u0430 \u0440\u0430\u0437\u0434\u0435\u043b\u0430: \u044d\u043c\u043e\u0434\u0437\u0438 + \u043f\u0440\u043e\u0431\u0435\u043b + *\u0416\u0438\u0440\u043d\u044b\u0439 \u0437\u0430\u0433\u043e\u043b\u043e\u0432\u043e\u043a* \u2014 \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0438\u0447\u0435\u0433\u043e \u043d\u0430 \u044d\u0442\u043e\u0439 \u0441\u0442\u0440\u043e\u043a\u0435"
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
    "silence_timeout": 180,
    "sound_on_done": True,
    "transcribe_only": False,
    "context_profiles": {},
    "input_device": None,
    "recordings_dir": "",
    "theme": "light",
    "menubar_enabled": False,
    "agent_url": "",
    "agent_token": "",
    "agent_enabled": False,
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
    "qwen3:30b": {
        "display": "Qwen 3 30B",
        "size_gb": 19.0,
        "quality": "Great (24+ GB RAM)",
        "ollama_name": "qwen3:30b",
    },
    "gpt-oss:20b": {
        "display": "GPT-OSS 20B",
        "size_gb": 12.0,
        "quality": "Best (16+ GB RAM)",
        "ollama_name": "gpt-oss:20b",
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
        _logger.info("list_ollama_models: ollama binary not found")
        return []
    try:
        r = subprocess.run([ollama, "list"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            _logger.warning("ollama list failed (rc=%d): %s", r.returncode, r.stderr.strip())
            ensure_ollama_server(ollama)
            r = subprocess.run([ollama, "list"], capture_output=True, text=True, timeout=10)
        lines = r.stdout.strip().splitlines()[1:]  # skip header
        models = [line.split()[0] for line in lines if line.strip()]
        _logger.info("list_ollama_models: found %d models: %s", len(models), models)
        return models
    except Exception as e:
        _logger.warning("list_ollama_models error: %s", e)
        return []


def is_local_llm_downloaded(model_key: str, _pulled: list[str] | None = None) -> bool:
    info = LOCAL_LLM_MODELS.get(model_key)
    if not info:
        return False
    if _pulled is None:
        _pulled = list_ollama_models()
    return info["ollama_name"] in _pulled


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


def get_context_profile(context_name: str) -> str:
    """Return the saved instruction profile for a context, or the global active profile."""
    cfg = load()
    context_profiles = cfg.get("context_profiles", {})
    return context_profiles.get(context_name, cfg.get("active_profile", DEFAULT_PROFILE_NAME))


def set_context_profile(context_name: str, profile_name: str):
    """Save the instruction profile association for a context."""
    cfg = load()
    context_profiles = cfg.get("context_profiles", {})
    context_profiles[context_name] = profile_name
    cfg["context_profiles"] = context_profiles
    save(cfg)


def get_default_instructions() -> str:
    """Return DEFAULT_INSTRUCTIONS in the user's language."""
    from .i18n import locale
    if locale() == "ru":
        return DEFAULT_INSTRUCTIONS_RU
    return DEFAULT_INSTRUCTIONS


def get_general_instructions() -> str:
    """Return GENERAL_MEETING_INSTRUCTIONS in the user's language."""
    from .i18n import locale
    if locale() == "ru":
        return GENERAL_MEETING_INSTRUCTIONS_RU
    return GENERAL_MEETING_INSTRUCTIONS


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
