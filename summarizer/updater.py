"""Check for app updates via GitHub Releases API."""

import json
import logging
import platform
import ssl
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional, Dict

import certifi

from . import config

_ssl_ctx = ssl.create_default_context(cafile=certifi.where())

_logger = logging.getLogger("updater")

GITHUB_REPO = "fvoin/summarizer"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse_version(tag: str) -> tuple:
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def _arch_tag() -> str:
    """DMG arch suffix for the running process."""
    return "AppleSilicon" if platform.machine() == "arm64" else "Intel"


def _select_dmg(assets: list, edition: str, arch: str) -> Optional[str]:
    """Pick the DMG download URL matching this edition and CPU architecture.

    Lite DMGs contain "Transcriber" in the name; full ones do not. Within the
    matching edition, prefer the asset whose name contains this arch tag.
    """
    dmgs = [a for a in assets if a.get("name", "").lower().endswith(".dmg")]
    if not dmgs:
        return None
    want_lite = edition == "lite"
    same_edition = [a for a in dmgs if ("transcriber" in a["name"].lower()) == want_lite]
    pool = same_edition or dmgs  # fall back to any DMG if naming is unexpected
    for a in pool:
        if arch.lower() in a["name"].lower():
            return a["browser_download_url"]
    return pool[0]["browser_download_url"]


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
        with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
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

    dmg_url = _select_dmg(data.get("assets", []), config.EDITION, _arch_tag())
    if not dmg_url:
        _logger.warning("New version %s found but no DMG asset", tag)
        return None
    _logger.info("Selected DMG for edition=%s arch=%s: %s", config.EDITION, _arch_tag(), dmg_url)

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
    with urllib.request.urlopen(req, timeout=120, context=_ssl_ctx) as resp:
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
