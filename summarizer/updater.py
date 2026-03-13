"""Check for app updates via GitHub Releases API."""

import json
import logging
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional, Dict

from . import config

_logger = logging.getLogger("updater")

GITHUB_REPO = "fvoin/summarizer"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse_version(tag: str) -> tuple:
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def check_for_update() -> Optional[Dict]:
    """Query GitHub for the latest release.

    Returns a dict with keys ``tag``, ``dmg_url``, ``notes`` when a newer
    version exists, or ``None`` if the app is already up to date.
    """
    _logger.info("Checking for updates (current=%s)…", config.APP_VERSION)
    req = urllib.request.Request(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Summarizer"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        _logger.error("Update check failed: %s", e)
        raise RuntimeError(f"Could not reach GitHub: {e}") from e

    tag = data.get("tag_name", "")
    _logger.info("Latest release: %s", tag)

    try:
        remote = _parse_version(tag)
        local = _parse_version(config.APP_VERSION)
    except (ValueError, IndexError):
        _logger.warning("Cannot parse version tags: remote=%s local=%s", tag, config.APP_VERSION)
        return None

    if remote <= local:
        _logger.info("Already up to date")
        return None

    dmg_url = None
    for asset in data.get("assets", []):
        if asset.get("name", "").lower().endswith(".dmg"):
            dmg_url = asset["browser_download_url"]
            break

    if not dmg_url:
        _logger.warning("New version %s found but no DMG asset", tag)
        return None

    return {
        "tag": tag,
        "dmg_url": dmg_url,
        "notes": data.get("body", ""),
    }


def download_and_open(dmg_url: str, progress_cb=None) -> Path:
    """Download the DMG to ~/Downloads and open it in Finder.

    ``progress_cb`` is called with (bytes_downloaded, total_bytes) during
    the download.  ``total_bytes`` may be 0 if the server does not send
    Content-Length.
    """
    dest = Path.home() / "Downloads" / "Summarizer.dmg"
    _logger.info("Downloading %s → %s", dmg_url, dest)

    req = urllib.request.Request(dmg_url, headers={"User-Agent": "Summarizer"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 256 * 1024
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)

    _logger.info("Download complete (%d bytes)", dest.stat().st_size)
    return dest
