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


def download_dmg(dmg_url: str, progress_cb=None) -> Path:
    """Download the DMG to ~/Downloads and return its path.

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


def download_and_open(dmg_url: str, progress_cb=None) -> Path:
    """Download the DMG and open it in Finder (manual drag-install)."""
    dest = download_dmg(dmg_url, progress_cb)
    subprocess.run(["open", str(dest)], check=False)
    return dest


# ── one-click self-update ────────────────────────────────────────────────
#
# The app is ad-hoc signed, so a DMG the user downloads in a browser is
# quarantined and Gatekeeper demands the right-click-open dance. When the
# app updates ITSELF it can strip the quarantine attribute from the copy it
# stages and swap it into /Applications, so one click is enough.


def _bundle_path(exe: Optional[str] = None) -> Optional[Path]:
    """Root ``*.app`` bundle the given executable lives in, or None."""
    import sys
    p = Path(exe if exe is not None else sys.executable)
    for parent in p.parents:
        if parent.suffix == ".app":
            return parent
    return None


def _write_swap_script(pid: int, staged: Path, old_bundle: Path, dest: Path) -> Path:
    """Write the detached helper that swaps bundles once the app exits.

    Keeps the old bundle as ``*.app.old`` until the new one is in place;
    rolls back and relaunches the old app if the swap fails.
    """
    import shlex
    old_q = shlex.quote(str(old_bundle))
    new_q = shlex.quote(str(staged))
    dest_q = shlex.quote(str(dest))
    bak_q = shlex.quote(str(old_bundle) + ".old")
    script = f"""#!/bin/sh
# Auto-generated by Summarizer self-update. Safe to delete.
i=0
while /bin/kill -0 {pid} 2>/dev/null; do
  /bin/sleep 0.2
  i=$((i+1))
  [ $i -gt 300 ] && exit 1
done
/bin/rm -rf {bak_q}
[ -d {old_q} ] && /bin/mv {old_q} {bak_q}
if /bin/mv {new_q} {dest_q}; then
  /usr/bin/open {dest_q}
  /bin/sleep 10
  /bin/rm -rf {bak_q}
else
  [ -d {bak_q} ] && /bin/mv {bak_q} {old_q}
  /usr/bin/open {old_q}
fi
"""
    config._CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = config._CONFIG_DIR / "update_swap.sh"
    path.write_text(script)
    path.chmod(0o755)
    return path


def self_update(dmg_url: str, progress_cb=None) -> Path:
    """Download and install an update in place; returns the staged bundle.

    Spawns a detached helper that waits for this process to exit, swaps the
    staged bundle into /Applications and relaunches — the caller must quit
    the app promptly after this returns. Raises RuntimeError when not
    running from an installed .app bundle (dev runs fall back to
    ``download_and_open``).
    """
    import os
    import tempfile

    bundle = _bundle_path()
    if bundle is None:
        raise RuntimeError("not running from an installed .app bundle")

    dmg = download_dmg(dmg_url, progress_cb)
    mount = Path(tempfile.mkdtemp(prefix="summarizer_upd_mnt_"))
    subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly",
         "-mountpoint", str(mount), str(dmg)],
        check=True, capture_output=True,
    )
    try:
        apps = sorted(mount.glob("*.app"))
        if not apps:
            raise RuntimeError("No .app found inside the update DMG")
        src = apps[0]
        staged = Path(tempfile.mkdtemp(prefix="summarizer_upd_stage_")) / src.name
        subprocess.run(["ditto", str(src), str(staged)],
                       check=True, capture_output=True)
        # The unquarantined copy is what makes this one-click: Gatekeeper
        # never re-assesses it, so no right-click-open after the swap.
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(staged)],
                       capture_output=True)
    finally:
        subprocess.run(["hdiutil", "detach", str(mount)], capture_output=True)

    dest = bundle.parent / staged.name  # follows an app rename in the DMG
    script = _write_swap_script(os.getpid(), staged, bundle, dest)
    _logger.info("Self-update staged at %s; swap helper %s", staged, script)
    _spawn_detached(["/bin/sh", str(script)])
    return staged


def _spawn_detached(cmd: list) -> None:
    subprocess.Popen(cmd, start_new_session=True)
