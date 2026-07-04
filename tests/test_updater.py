from summarizer.updater import _select_dmg


def _assets(*names):
    return [{"name": n, "browser_download_url": f"https://x/{n}"} for n in names]


ALL = _assets(
    "Summarizer-AppleSilicon.dmg",
    "Summarizer-Intel.dmg",
    "Summarizer-Transcriber-AppleSilicon.dmg",
    "Summarizer-Transcriber-Intel.dmg",
)


def test_full_arm_picks_full_apple_silicon():
    assert _select_dmg(ALL, "full", "AppleSilicon").endswith("Summarizer-AppleSilicon.dmg")


def test_lite_arm_picks_transcriber_apple_silicon():
    assert _select_dmg(ALL, "lite", "AppleSilicon").endswith("Summarizer-Transcriber-AppleSilicon.dmg")


def test_full_intel_picks_full_intel():
    assert _select_dmg(ALL, "full", "Intel").endswith("Summarizer-Intel.dmg")


def test_lite_intel_picks_transcriber_intel():
    assert _select_dmg(ALL, "lite", "Intel").endswith("Summarizer-Transcriber-Intel.dmg")


def test_full_never_picks_lite_dmg():
    # release with only arm DMGs of both editions; full must not grab the lite one
    assets = _assets("Summarizer-AppleSilicon.dmg", "Summarizer-Transcriber-AppleSilicon.dmg")
    assert "Transcriber" not in _select_dmg(assets, "full", "AppleSilicon")


def test_arch_fallback_returns_edition_match_when_no_arch_asset():
    # only Intel assets available but running arm -> still returns the edition match
    assets = _assets("Summarizer-Intel.dmg", "Summarizer-Transcriber-Intel.dmg")
    assert _select_dmg(assets, "lite", "AppleSilicon").endswith("Summarizer-Transcriber-Intel.dmg")


def test_no_dmg_returns_none():
    assert _select_dmg(_assets("notes.txt"), "full", "AppleSilicon") is None
