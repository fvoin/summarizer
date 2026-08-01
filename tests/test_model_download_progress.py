"""download_model must actually report progress (it never called its cb)."""

import time

import pytest

import huggingface_hub

from summarizer import config, transcriber


def test_download_model_reports_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "get_models_dir", lambda: tmp_path)
    monkeypatch.setattr(config, "WHISPER_MODELS", {
        "fake": {"repo": "x/fake", "size_mb": 1, "quality": "Test"},
    })

    def fake_snapshot(repo_id, local_dir):
        # Simulate a download: half the expected bytes appear, then the rest.
        f = tmp_path / "fake" / "model.bin"
        f.write_bytes(b"\0" * (512 * 1024))
        time.sleep(0.7)  # let the poller observe the partial state
        f.write_bytes(b"\0" * (1024 * 1024))
        time.sleep(0.7)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot)

    seen = []
    transcriber.download_model("fake", progress_cb=seen.append)

    assert seen, "progress_cb was never called"
    assert seen[-1] == 1.0
    mid = [p for p in seen if 0.3 < p < 0.8]
    assert mid, f"no intermediate progress observed: {seen}"
    assert seen == sorted(seen)  # monotonically increasing
