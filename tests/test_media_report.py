import json
from pathlib import Path

import pytest

from dog_audio.media import InputError, parse_probe, required_free_bytes
from dog_audio.models import Clip, Event, Metrics, Processing, RunResult, SourceIdentity
from dog_audio.report import write_reports


def test_probe_accepts_audio_and_rejects_video_only_or_unknown():
    source = parse_probe({"format": {"duration": "12.5", "format_name": "mov,mp4,m4a"},
                          "streams": [{"codec_type": "audio", "codec_name": "aac"}]}, Path("x.m4a"), "a"*64, 20)
    assert source.duration_seconds == 12.5
    with pytest.raises(InputError):
        parse_probe({"format": {"duration": "1", "format_name": "mp4"},
                     "streams": [{"codec_type": "video", "codec_name": "h264"}]}, Path("x.mp4"), "a"*64, 20)
    with pytest.raises(InputError):
        parse_probe({"format": {"duration": "1", "format_name": "ogg"},
                     "streams": [{"codec_type": "audio", "codec_name": "opus"}]}, Path("x.ogg"), "a"*64, 20)


def test_space_estimate_has_floor():
    assert required_free_bytes(1, 128) == 512 * 1024 * 1024
    assert required_free_bytes(100_000, 128) > 512 * 1024 * 1024


def test_reports_match_and_incomplete_omits_percentages_and_zip(tmp_path):
    event = Event(id="E001", start_seconds=1, end_seconds=2, start_elapsed="0:00:01.000",
                  end_elapsed="0:00:02.000", span_seconds=1, peak_score=.7, mean_score=.5,
                  clip_ids=["C001"])
    clip = Clip(id="C001", event_ids=["E001"], start_seconds=0, end_seconds=4,
                filename="clips/C001.mp3", part_index=1, part_count=1)
    result = RunResult(status="partial", source=SourceIdentity(filename="=dog.wav", sha256="a"*64,
        size_bytes=20, duration_seconds=10, codec="pcm_s16le", format_name="wav"), settings={}, events=[event],
        clips=[clip], metrics=Metrics(analyzed_seconds=5, active_seconds=1, episode_span_seconds=1,
        review_seconds=4, first_detection_seconds=1, longest_episode_seconds=1, episode_count=1),
        processing=Processing(started_utc="2026-01-01T00:00:00Z"), analyzed_intervals=[(0, 5)])
    write_reports(tmp_path, result, make_zip=False)
    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["status"] == "partial"
    assert "coverage" not in (tmp_path / "summary.txt").read_text(encoding="utf-8").lower()
    assert "'=dog.wav" in (tmp_path / "events.csv").read_text(encoding="utf-8") or "=dog.wav" not in (tmp_path / "events.csv").read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.zip"))

