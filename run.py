"""Entry point for Summarizer app.

Sets up paths for bundled resources (ffmpeg, whisper model) when running
from a PyInstaller .app bundle, then launches the Qt application.
"""

import sys
import os
import multiprocessing

multiprocessing.freeze_support()
if multiprocessing.current_process().name != "MainProcess":
    sys.exit(0)

import shutil


def _setup_bundled_paths():
    """When running inside a PyInstaller bundle, add bundled ffmpeg to PATH
    and seed the model cache from the bundled whisper model."""
    if getattr(sys, "frozen", False):
        bundle_dir = sys._MEIPASS
    else:
        bundle_dir = os.path.dirname(os.path.abspath(__file__))

    # ffmpeg
    ffmpeg_dir = os.path.join(bundle_dir, "ffmpeg")
    if os.path.isdir(ffmpeg_dir):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    elif os.path.isfile(os.path.join(bundle_dir, "ffmpeg")):
        os.environ["PATH"] = bundle_dir + os.pathsep + os.environ.get("PATH", "")

    # Seed the local model cache from the bundled whisper model (one-time copy)
    whisper_dir = os.path.join(bundle_dir, "whisper_model")
    if os.path.isdir(whisper_dir) and os.path.isfile(os.path.join(whisper_dir, "model.bin")):
        os.environ["WHISPER_MODEL_DIR"] = whisper_dir
        cache_dir = os.path.join(os.path.expanduser("~"), ".summarizer", "models", "base")
        marker = os.path.join(cache_dir, "model.bin")
        if not os.path.exists(marker):
            try:
                shutil.copytree(whisper_dir, cache_dir, dirs_exist_ok=True)
            except Exception:
                pass


_setup_bundled_paths()

from summarizer.app import main

if __name__ == "__main__":
    main()
