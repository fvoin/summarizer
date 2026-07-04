import os
from summarizer.recorder import AudioRecorder


def test_get_source_files_reports_existing(tmp_path):
    rec = AudioRecorder()
    mic = tmp_path / "summarizer_rec_x_1.wav"
    sysf = tmp_path / "summarizer_sys_x.wav"
    mic.write_bytes(b"RIFF0000")
    sysf.write_bytes(b"RIFF0000")
    rec._mic_files = [str(mic)]
    rec._sys_file = str(sysf)
    out = rec.get_source_files()
    assert out["mic"] == [str(mic)]
    assert out["system"] == str(sysf)


def test_get_source_files_omits_missing(tmp_path):
    rec = AudioRecorder()
    rec._mic_files = [str(tmp_path / "missing.wav")]
    rec._sys_file = None
    out = rec.get_source_files()
    assert out["mic"] == []
    assert out["system"] is None


def test_cleanup_sources_deletes_files(tmp_path):
    rec = AudioRecorder()
    mic = tmp_path / "summarizer_rec_x_1.wav"
    mic.write_bytes(b"data")
    rec._mic_files = [str(mic)]
    rec._sys_file = None
    rec.cleanup_sources()
    assert not os.path.exists(str(mic))
