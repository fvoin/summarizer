from summarizer.diarize import Segment, _normalize, _similarity


def test_segment_defaults_speaker_empty():
    seg = Segment(start=0.0, end=1.0, text="hello")
    assert seg.start == 0.0
    assert seg.end == 1.0
    assert seg.text == "hello"
    assert seg.speaker == ""


def test_segment_accepts_speaker():
    seg = Segment(start=1.0, end=2.0, text="hi", speaker="me")
    assert seg.speaker == "me"


def test_normalize_lowercases_and_strips_punctuation():
    assert _normalize("Hello, World!") == "hello world"


def test_normalize_collapses_whitespace():
    assert _normalize("  a   b  ") == "a b"


def test_similarity_identical_is_one():
    assert _similarity("move the deadline", "move the deadline") == 1.0


def test_similarity_empty_is_zero():
    assert _similarity("", "anything") == 0.0
    assert _similarity("anything", "   ") == 0.0


def test_similarity_close_transcription_is_high():
    # echoed remote voice transcribes imperfectly but similar
    score = _similarity("let's move the deadline", "less move the dead line")
    assert score >= 0.6


def test_similarity_different_text_is_low():
    score = _similarity("can you send me the report", "the weather is nice today")
    assert score < 0.6
