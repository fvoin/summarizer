"""One-click self-update: download -> mount -> stage -> dequarantine -> swap.

The app is ad-hoc signed (no Apple Developer account), so Gatekeeper blocks a
plainly downloaded DMG behind the right-click-to-open dance. Because the app
controls both the download and the install, it can strip the quarantine
attribute from the staged copy and swap it into /Applications itself.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from summarizer import updater


# ── bundle detection ─────────────────────────────────────────────────────


def test_bundle_path_parses_app_root():
    exe = "/Applications/Transcriber.app/Contents/MacOS/Transcriber"
    assert updater._bundle_path(exe) == Path("/Applications/Transcriber.app")


def test_bundle_path_none_for_dev_python():
    assert updater._bundle_path(sys.executable) is None


# ── refusal outside a bundle ─────────────────────────────────────────────


def test_self_update_refuses_outside_bundle(monkeypatch):
    monkeypatch.setattr(updater, "_bundle_path", lambda: None)
    called = []
    monkeypatch.setattr(updater, "download_dmg", lambda *a, **k: called.append(1))
    with pytest.raises(RuntimeError):
        updater.self_update("https://example.com/x.dmg")
    assert not called  # refused before downloading anything


# ── swap script ──────────────────────────────────────────────────────────


def test_swap_script_waits_swaps_and_rolls_back(tmp_path):
    script = updater._write_swap_script(
        pid=12345,
        staged=tmp_path / "stage/My App.app",
        old_bundle=Path("/Applications/My App.app"),
        dest=Path("/Applications/My App.app"),
    )
    text = Path(script).read_text()
    assert "12345" in text
    assert "'/Applications/My App.app'" in text  # spaces safely quoted
    assert "open" in text
    assert "mv" in text and "rm -rf" in text  # swap + backup cleanup/rollback


# ── end to end with a real DMG (hdiutil) ─────────────────────────────────


@pytest.mark.skipif(shutil.which("hdiutil") is None, reason="needs macOS hdiutil")
def test_self_update_stages_dequarantined_app(tmp_path, monkeypatch):
    # Build a fake .app and pack it into a real DMG.
    src_app = tmp_path / "dmgroot" / "FakeApp.app"
    (src_app / "Contents/MacOS").mkdir(parents=True)
    (src_app / "Contents/MacOS/FakeApp").write_text("#!/bin/sh\necho hi\n")
    dmg = tmp_path / "FakeApp.dmg"
    subprocess.run(
        ["hdiutil", "create", "-srcfolder", str(tmp_path / "dmgroot"),
         "-volname", "FakeApp", "-quiet", str(dmg)],
        check=True,
    )

    monkeypatch.setattr(updater, "_bundle_path",
                        lambda: Path("/Applications/FakeApp.app"))
    monkeypatch.setattr(updater, "download_dmg", lambda url, progress_cb=None: dmg)

    spawned = []
    monkeypatch.setattr(updater, "_spawn_detached", lambda cmd: spawned.append(cmd))

    staged = updater.self_update("https://example.com/FakeApp.dmg")

    assert staged.name == "FakeApp.app"
    assert (staged / "Contents/MacOS/FakeApp").exists()
    xattrs = subprocess.run(["xattr", str(staged)], capture_output=True, text=True)
    assert "com.apple.quarantine" not in xattrs.stdout
    assert spawned and any(str(s).endswith(".sh") for s in spawned[0])
    # DMG must be unmounted again
    assert not os.path.ismount("/Volumes/FakeApp")
