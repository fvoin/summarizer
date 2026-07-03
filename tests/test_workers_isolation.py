import sys


def test_importing_workers_does_not_load_summarizer_or_db():
    for mod in ("summarizer.summarizer", "summarizer.db"):
        sys.modules.pop(mod, None)
    import summarizer.workers  # noqa: F401
    assert "summarizer.summarizer" not in sys.modules
    assert "summarizer.db" not in sys.modules


def test_workers_exports_expected_classes():
    import summarizer.workers as w
    for name in ("TranscribeWorker", "RealtimeTranscribeWorker",
                 "_DeltaTranscribeWorker", "DiarizeTranscribeWorker", "LiveTranscriber"):
        assert hasattr(w, name), name
