import csv
from pathlib import Path

import pytest

from dog_audio.cli import cleanup_staging, main, parse_ffmpeg_version
from dog_audio.inference import owns_frame, resolve_bark_index
from dog_audio.models import Frame


def test_bark_is_resolved_by_label(tmp_path):
    labels = tmp_path / "classes.csv"
    with labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "mid", "display_name"])
        writer.writerow([0, "/m/a", "Speech"])
        writer.writerow([7, "/m/b", "Bark"])
    assert resolve_bark_index(labels) == 7
    labels.write_text("index,mid,display_name\n0,/m/a,Speech\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Bark"):
        resolve_bark_index(labels)


def test_frame_center_has_exactly_one_core_owner():
    assert owns_frame(59.999, 0, 60, final=False)
    assert not owns_frame(60.0, 0, 60, final=False)
    assert owns_frame(60.0, 60, 120, final=True)
    assert owns_frame(120.0, 60, 120, final=True)
    assert not owns_frame(120.001, 60, 120, final=True)


def test_nightly_ffmpeg_build_is_new_enough():
    assert parse_ffmpeg_version("ffmpeg version N-121462-gd91b1559e0 Copyright")
    assert parse_ffmpeg_version("ffmpeg version 6.1.2 Copyright")
    assert not parse_ffmpeg_version("ffmpeg version 5.0 Copyright")


def test_doctor_reports_missing_offline_cache(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("TFHUB_CACHE_DIR", str(tmp_path))
    code = main(["doctor", "--offline"])
    output = capsys.readouterr()
    assert code == 4
    assert "YAMNet" in output.err


def test_cleanup_only_removes_stale_inactive_staging(tmp_path):
    active = tmp_path / ".a.staging-live"
    stale = tmp_path / ".b.staging-old"
    active.mkdir(); stale.mkdir()
    (active / ".active").write_text(f"{__import__('os').getpid()}\n", encoding="utf-8")
    (stale / ".active").write_text("99999999\n", encoding="utf-8")
    cleanup_staging(tmp_path, older_than_seconds=0)
    assert active.exists()
    assert not stale.exists()


def test_analyze_publishes_new_complete_run(monkeypatch, tmp_path):
    source = tmp_path / "dog.wav"
    source.write_bytes(b"unchanged")
    class FakeModel:
        bark_index = 7
        digest = "d" * 64
        @staticmethod
        def versions(): return {"fake": "1"}
    monkeypatch.setattr("dog_audio.cli.Yamnet", FakeModel)
    monkeypatch.setattr("dog_audio.cli.probe_input", lambda path: __import__("dog_audio.models", fromlist=["SourceIdentity"]).SourceIdentity(
        filename="dog.wav", sha256=__import__("hashlib").sha256(b"unchanged").hexdigest(), size_bytes=9,
        duration_seconds=10, codec="pcm_s16le", format_name="wav"))
    monkeypatch.setattr("dog_audio.cli.ensure_space", lambda *args: None)
    monkeypatch.setattr("dog_audio.cli.iter_inference", lambda *args: iter([([Frame(start_seconds=1, end_seconds=1.96, score=.8)], (0, 10))]))
    monkeypatch.setattr("dog_audio.cli.export_clip", lambda source, clip, destination, kbps: (destination.parent.mkdir(parents=True, exist_ok=True), destination.write_bytes(b"mp3")))
    output = tmp_path / "out"
    assert main(["analyze", str(source), "--output", str(output)]) == 0
    run = next(output.iterdir())
    assert (run / "report.zip").is_file()
    assert (run / "clips" / "C001_part-01-of-01.mp3").is_file()
    assert not (run / ".active").exists()


def test_partial_run_preserves_events_without_zip(monkeypatch, tmp_path):
    source = tmp_path / "dog.wav"; source.write_bytes(b"unchanged")
    digest = __import__("hashlib").sha256(b"unchanged").hexdigest()
    source_model = __import__("dog_audio.models", fromlist=["SourceIdentity"]).SourceIdentity
    class FakeModel:
        bark_index = 7; digest = "d" * 64
        @staticmethod
        def versions(): return {"fake": "1"}
    def interrupted(*args):
        yield [Frame(start_seconds=1, end_seconds=1.96, score=.8)], (0, 5)
        raise RuntimeError("decoder stopped")
    monkeypatch.setattr("dog_audio.cli.Yamnet", FakeModel)
    monkeypatch.setattr("dog_audio.cli.probe_input", lambda path: source_model(filename="dog.wav", sha256=digest,
        size_bytes=9, duration_seconds=10, codec="pcm_s16le", format_name="wav"))
    monkeypatch.setattr("dog_audio.cli.ensure_space", lambda *args: None)
    monkeypatch.setattr("dog_audio.cli.iter_inference", interrupted)
    output = tmp_path / "out"
    assert main(["analyze", str(source), "--output", str(output)]) == 5
    run = next(output.iterdir())
    result = __import__("json").loads((run / "results.json").read_text(encoding="utf-8"))
    assert result["status"] == "partial"
    assert len(result["events"]) == 1
    assert result["metrics"]["coverage_percent"] is None
    assert not (run / "report.zip").exists()


def test_unavailable_model_uses_dependency_exit_code(monkeypatch, tmp_path):
    source = tmp_path / "dog.wav"; source.write_bytes(b"unchanged")
    digest = __import__("hashlib").sha256(b"unchanged").hexdigest()
    source_model = __import__("dog_audio.models", fromlist=["SourceIdentity"]).SourceIdentity
    monkeypatch.setattr("dog_audio.cli.probe_input", lambda path: source_model(filename="dog.wav", sha256=digest,
        size_bytes=9, duration_seconds=10, codec="pcm_s16le", format_name="wav"))
    monkeypatch.setattr("dog_audio.cli.ensure_space", lambda *args: None)
    monkeypatch.setattr("dog_audio.cli.Yamnet", lambda: (_ for _ in ()).throw(RuntimeError("model unavailable")))
    assert main(["analyze", str(source), "--output", str(tmp_path / "out")]) == 4


def test_export_failure_removes_missing_links_and_coverage(monkeypatch, tmp_path):
    source = tmp_path / "dog.wav"; source.write_bytes(b"unchanged")
    digest = __import__("hashlib").sha256(b"unchanged").hexdigest()
    source_model = __import__("dog_audio.models", fromlist=["SourceIdentity"]).SourceIdentity
    class FakeModel:
        bark_index = 7; digest = "d" * 64
        @staticmethod
        def versions(): return {"fake": "1"}
    monkeypatch.setattr("dog_audio.cli.Yamnet", FakeModel)
    monkeypatch.setattr("dog_audio.cli.probe_input", lambda path: source_model(filename="dog.wav", sha256=digest,
        size_bytes=9, duration_seconds=10, codec="pcm_s16le", format_name="wav"))
    monkeypatch.setattr("dog_audio.cli.ensure_space", lambda *args: None)
    monkeypatch.setattr("dog_audio.cli.iter_inference", lambda *args: iter([([Frame(start_seconds=1, end_seconds=1.96, score=.8)], (0, 10))]))
    monkeypatch.setattr("dog_audio.cli.export_clip", lambda *args: (_ for _ in ()).throw(RuntimeError("encode failed")))
    output = tmp_path / "out"
    assert main(["analyze", str(source), "--output", str(output)]) == 5
    result = __import__("json").loads((next(output.iterdir()) / "results.json").read_text(encoding="utf-8"))
    assert result["metrics"]["coverage_percent"] is None
    assert result["clips"] == []
    assert result["events"][0]["clip_ids"] == []
