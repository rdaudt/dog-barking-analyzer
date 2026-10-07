from pathlib import Path

import pytest
from pydantic import ValidationError

from dog_audio.analysis import assemble_events, build_clips, calculate_metrics, interval_union
from dog_audio.config import Settings, load_settings
from dog_audio.models import Frame
from dog_audio.util import format_elapsed, safe_stem


def test_presets_and_config_validation():
    default = load_settings(Path("config/default.toml"))
    assert (default.onset, default.offset) == (0.30, 0.20)
    with pytest.raises(ValidationError):
        Settings(onset=0.2, offset=0.2)
    with pytest.raises(ValidationError):
        Settings(chunk_seconds=2, clip_padding_seconds=2)
    with pytest.raises(ValidationError):
        Settings(chunk_seconds=float("inf"))
    bad = Path("tests/bad.toml")
    bad.write_text("onset=0.3\nunknown=1\n", encoding="utf-8")
    try:
        with pytest.raises(ValidationError):
            load_settings(bad)
    finally:
        bad.unlink()


def test_hysteresis_keeps_isolated_onset_and_merges():
    frames = [
        Frame(start_seconds=0, end_seconds=.96, score=.31),
        Frame(start_seconds=.48, end_seconds=1.44, score=.10),
        Frame(start_seconds=3, end_seconds=3.96, score=.4),
        Frame(start_seconds=3.48, end_seconds=4.44, score=.21),
        Frame(start_seconds=4, end_seconds=4.96, score=.1),
    ]
    events = assemble_events(frames, onset=.3, offset=.2, merge_gap=3)
    assert len(events) == 1
    assert events[0].start_seconds == 0
    assert events[0].end_seconds == 4.44
    assert events[0].peak_score == .4
    assert events[0].mean_score == pytest.approx((.31 + .4 + .21) / 3)


def test_clips_share_overlap_split_and_clamp():
    frames = [Frame(start_seconds=1, end_seconds=2, score=.5), Frame(start_seconds=2, end_seconds=3, score=.1),
              Frame(start_seconds=4, end_seconds=5, score=.6)]
    events = assemble_events(frames, onset=.3, offset=.2, merge_gap=0)
    clips = build_clips(events, duration=10, padding=2, max_seconds=3)
    assert len(clips) == 3
    assert clips[0].event_ids == ["E001", "E002"]
    assert clips[0].start_seconds == 0
    assert clips[-1].end_seconds == 7
    assert [c.part_index for c in clips] == [1, 2, 3]


def test_unions_and_metrics_do_not_double_count():
    assert interval_union([(0, 2), (1, 3), (5, 6)]) == 4
    frames = [Frame(start_seconds=1, end_seconds=2, score=.5), Frame(start_seconds=2, end_seconds=3, score=.1),
              Frame(start_seconds=4, end_seconds=5, score=.6)]
    events = assemble_events(frames, .3, .2, 0)
    clips = build_clips(events, 10, 2, 300)
    metrics = calculate_metrics(events, clips, duration=10, analyzed_intervals=[(0, 6), (5, 10)], complete=True)
    assert metrics.active_seconds == 2
    assert metrics.review_seconds == 7
    assert metrics.coverage_percent == 100
    assert metrics.first_detection_seconds == 1


def test_formatting_and_safe_names():
    assert format_elapsed(3661.25) == "1:01:01.250"
    assert safe_stem("  my dog: bark?.wav ") == "my_dog_bark"
    assert safe_stem("CON.wav") == "recording"
