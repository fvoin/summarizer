from summarizer.diarize import Segment


def test_segment_defaults_speaker_empty():
    seg = Segment(start=0.0, end=1.0, text="hello")
    assert seg.start == 0.0
    assert seg.end == 1.0
    assert seg.text == "hello"
    assert seg.speaker == ""


def test_segment_accepts_speaker():
    seg = Segment(start=1.0, end=2.0, text="hi", speaker="me")
    assert seg.speaker == "me"
