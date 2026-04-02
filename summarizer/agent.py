"""Auto-record agent: polls a web backend for upcoming meetings and records them."""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import certifi
from PyQt6.QtCore import QThread, QTimer, pyqtSignal

from . import config

_logger = logging.getLogger("agent")
_ssl_ctx = ssl.create_default_context(cafile=certifi.where())

# How often to poll (seconds)
POLL_INTERVAL = 5 * 60
# No-show timeout: if no voice for this many seconds after start, abort
NO_SHOW_TIMEOUT = 5 * 60
# How early before start to arm (seconds) — must be > POLL_INTERVAL
ARM_LEAD_TIME = 10 * 60


class AgentPoller(QThread):
    """Background thread that polls for upcoming meetings.

    Signals
    -------
    meeting_armed(dict)
        Emitted when a meeting is about to start and recording should be armed.
    error(str)
        Emitted on HTTP or parse errors.
    """

    meeting_armed = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._etag: str = ""
        self._armed_ids: set = set()

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                self._poll()
            except Exception as e:
                _logger.error("Agent poll error: %s", e)
                self.error.emit(str(e))
            # Sleep in small increments so stop() is responsive
            for _ in range(POLL_INTERVAL):
                if not self._running:
                    return
                time.sleep(1)

    def _poll(self):
        cfg = config.load()
        url = cfg.get("agent_url", "").rstrip("/")
        token = cfg.get("agent_token", "")
        if not url or not token:
            return

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "Summarizer",
            "Accept": "application/json",
        }
        if self._etag:
            headers["If-None-Match"] = self._etag

        req = urllib.request.Request(f"{url}/api/auto-record/upcoming", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
                self._etag = resp.headers.get("ETag", "")
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 304:
                _logger.debug("No changes (304)")
                return
            raise

        # Support both list and {meetings: [...]} / {data: [...]} responses
        if isinstance(data, dict):
            for key in ("meetings", "data", "items", "results"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            _logger.warning("Unexpected response format: %s", type(data))
            return

        now = datetime.now(timezone.utc)
        _logger.info("Poll returned %d meeting(s), now=%s", len(data), now.isoformat())
        for meeting in data:
            mid = meeting.get("id") or meeting.get("calendarEventId") or meeting.get("title", "")
            _logger.info("  Meeting '%s' (id=%s) start=%s", meeting.get("title", "?"), mid, meeting.get("start", "?"))
            if mid in self._armed_ids:
                _logger.debug("  Already armed, skipping")
                continue
            start_str = meeting.get("start") or meeting.get("startTime") or meeting.get("start_time", "")
            if not start_str:
                _logger.warning("  No start time found, skipping")
                continue
            try:
                start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                _logger.warning("  Cannot parse start time: %s", start_str)
                continue
            seconds_until = (start - now).total_seconds()
            # Arm if meeting is about to start or already started (within last 10 min)
            if seconds_until <= ARM_LEAD_TIME and seconds_until > -600:
                self._armed_ids.add(mid)
                _logger.info("  -> Arming! seconds_until=%.0f", seconds_until)
                self.meeting_armed.emit(meeting)
            else:
                _logger.info("  -> Not arming, seconds_until=%.0f", seconds_until)


def post_complete(transcript: str, meeting: dict) -> dict:
    """POST transcript + metadata to /api/auto-record/complete.

    Returns the response JSON (with meetingId, etc.).
    """
    cfg = config.load()
    url = cfg.get("agent_url", "").rstrip("/")
    token = cfg.get("agent_token", "")

    payload = json.dumps({
        "transcript": transcript,
        "meetingId": meeting.get("id") or meeting.get("calendarEventId", ""),
        "title": meeting.get("title", ""),
        "participants": meeting.get("participants", []),
        "agenda": meeting.get("agenda", ""),
        "duration": meeting.get("_duration", 0),
    }).encode()

    req = urllib.request.Request(
        f"{url}/api/auto-record/complete",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Summarizer",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as resp:
        return json.loads(resp.read().decode())


class PostCompleteWorker(QThread):
    """Upload transcript in background."""
    finished = pyqtSignal(dict)  # response data
    error = pyqtSignal(str)

    def __init__(self, transcript: str, meeting: dict, parent=None):
        super().__init__(parent)
        self._transcript = transcript
        self._meeting = meeting

    def run(self):
        try:
            result = post_complete(self._transcript, self._meeting)
            self.finished.emit(result)
        except Exception as e:
            _logger.error("Post complete failed: %s", e)
            self.error.emit(str(e))
