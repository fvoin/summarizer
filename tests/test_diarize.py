from summarizer.diarize import Segment, _normalize, _similarity, merge, format_transcript


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


def test_merge_system_only_all_remote():
    sys_segs = [Segment(0.0, 1.0, "hello from remote")]
    out = merge([], sys_segs)
    assert [s.speaker for s in out] == ["remote"]
    assert out[0].text == "hello from remote"


def test_merge_mic_segment_with_system_silent_is_me():
    mic = [Segment(5.0, 6.0, "my local comment")]
    sys = [Segment(0.0, 1.0, "earlier remote")]  # no time overlap with mic
    out = merge(mic, sys)
    me = [s for s in out if s.speaker == "me"]
    assert len(me) == 1
    assert me[0].text == "my local comment"


def test_merge_echo_is_dropped():
    # remote voice leaks into mic during the same window with similar text
    mic = [Segment(0.0, 1.0, "less move the dead line")]
    sys = [Segment(0.0, 1.0, "let's move the deadline")]
    out = merge(mic, sys)
    # only the authoritative remote segment survives; the echo mic seg is dropped
    assert [s.speaker for s in out] == ["remote"]


def test_merge_double_talk_kept_as_me():
    # both talk in the same window but say different things
    mic = [Segment(0.0, 1.0, "wait I disagree with that")]
    sys = [Segment(0.0, 1.0, "the report is due friday")]
    out = merge(mic, sys)
    speakers = sorted(s.speaker for s in out)
    assert speakers == ["me", "remote"]


def test_merge_sorted_by_start_time():
    mic = [Segment(10.0, 11.0, "later local")]
    sys = [Segment(0.0, 1.0, "early remote")]
    out = merge(mic, sys)
    assert out[0].text == "early remote"
    assert out[1].text == "later local"


def test_merge_applies_offset_to_system():
    # system clock lags mic by 2s; with offset the segments overlap -> echo dropped
    mic = [Segment(2.0, 3.0, "hello there friend")]
    sys = [Segment(0.0, 1.0, "hello there friend")]
    out = merge(mic, sys, offset=2.0)
    assert [s.speaker for s in out] == ["remote"]
    assert out[0].start == 2.0  # remote seg shifted onto mic timeline


def test_format_transcript_en():
    segs = [
        Segment(0.0, 1.0, "hello", speaker="remote"),
        Segment(1.0, 2.0, "hi back", speaker="me"),
    ]
    out = format_transcript(segs, locale="en")
    assert out == "Remote: hello\nMe: hi back"


def test_format_transcript_ru():
    segs = [Segment(0.0, 1.0, "привет", speaker="remote")]
    out = format_transcript(segs, locale="ru")
    assert out == "Собеседник: привет"


def test_format_transcript_skips_blank_text():
    segs = [
        Segment(0.0, 1.0, "   ", speaker="me"),
        Segment(1.0, 2.0, "real", speaker="remote"),
    ]
    out = format_transcript(segs, locale="en")
    assert out == "Remote: real"
