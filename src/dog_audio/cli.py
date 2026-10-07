import argparse
import os
import re
import shutil
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psutil

from .analysis import assemble_events, build_clips, calculate_metrics
from .config import Settings, load_settings
from .inference import MODEL_URI, Yamnet, iter_inference, model_cache_dir
from .media import DependencyError, InputError, ensure_space, export_clip, probe_input, required_free_bytes, sha256_file
from .models import Processing, RunResult
from .report import write_reports
from .util import safe_stem


EXIT_INVOCATION = 2
EXIT_INPUT = 3
EXIT_DEPENDENCY = 4
EXIT_PROCESSING = 5


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_ffmpeg_version(first: str) -> bool:
    if re.search(r"\bversion\s+N-\d+-g[0-9a-f]+", first, re.IGNORECASE):
        return True
    match = re.search(r"\bversion\s+n?(\d+)(?:\.(\d+))?", first, re.IGNORECASE)
    return bool(match and (int(match.group(1)), int(match.group(2) or 0)) >= (6, 1))


def _ffmpeg_version(program: str) -> tuple[int, str]:
    import subprocess
    try:
        result = subprocess.run([program, "-version"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 0, "not found"
    first = result.stdout.splitlines()[0] if result.stdout else result.stderr.strip()
    return int(parse_ffmpeg_version(first)), first


def doctor(offline: bool) -> int:
    healthy = True
    for program in ("ffmpeg", "ffprobe"):
        okay, detail = _ffmpeg_version(program)
        print(f"{program}: {detail}", file=sys.stderr)
        healthy &= bool(okay)
    cache = model_cache_dir()
    candidates = list(cache.glob("*/saved_model.pb")) if cache.exists() else []
    if offline and not candidates:
        print(f"YAMNet: no complete cached model found in {cache}", file=sys.stderr)
        healthy = False
    elif not offline:
        try:
            model = Yamnet()
            print(f"YAMNet: ready (Bark class {model.bark_index}, digest {model.digest[:12]})", file=sys.stderr)
        except Exception as error:
            print(f"YAMNet: unavailable: {error}", file=sys.stderr)
            healthy = False
    else:
        try:
            model = Yamnet(str(candidates[0].parent))
            print(f"YAMNet: offline reload ready (Bark class {model.bark_index}, digest {model.digest[:12]})", file=sys.stderr)
        except Exception as error:
            print(f"YAMNet: cached model is invalid: {error}", file=sys.stderr)
            healthy = False
    return 0 if healthy else EXIT_DEPENDENCY


def _publish(staging: Path, final: Path) -> Path:
    staging.rename(final)
    return final


def cleanup_staging(output_root: Path, older_than_seconds: float = 24 * 3600) -> None:
    """Remove abandoned staging directories, never one owned by a live process."""
    root = output_root.resolve()
    now = time.time()
    for candidate in output_root.glob(".*.staging-*"):
        resolved = candidate.resolve()
        if not candidate.is_dir() or resolved.parent != root:
            continue
        marker = candidate / ".active"
        try:
            pid = int(marker.read_text(encoding="utf-8").splitlines()[0])
            age = now - marker.stat().st_mtime
        except (OSError, ValueError, IndexError):
            pid, age = -1, now - candidate.stat().st_mtime
        if psutil.pid_exists(pid) or age < older_than_seconds:
            continue
        shutil.rmtree(candidate)


def analyze(input_path: Path, output_root: Path, config_path: Path | None) -> int:
    settings = load_settings(config_path) if config_path else Settings()
    output_root.mkdir(parents=True, exist_ok=True)
    cleanup_staging(output_root)
    token = uuid.uuid4().hex
    staging = output_root / f".{safe_stem(input_path.name)}.staging-{token}"
    staging.mkdir(exist_ok=False)
    (staging / ".active").write_text(f"{os.getpid()}\n{utc_now()}\n", encoding="utf-8")
    started = time.perf_counter()
    processing = Processing(started_utc=utc_now())
    result = RunResult(status="failed", settings=settings.model_dump(), processing=processing)
    exit_code = EXIT_PROCESSING
    original_digest = None
    frames = []
    try:
        print("[1/5] Inspecting input", file=sys.stderr)
        source = probe_input(input_path)
        original_digest = source.sha256
        result.source = source
        ensure_space(output_root, required_free_bytes(source.duration_seconds, settings.mp3_kbps))
        print("[2/5] Loading YAMNet", file=sys.stderr)
        try:
            model = Yamnet()
        except Exception as error:
            raise DependencyError(f"YAMNet is unavailable: {error}") from error
        processing.model_uri = MODEL_URI
        processing.model_digest = model.digest
        processing.bark_class_index = model.bark_index
        processing.dependencies = model.versions()
        print("[3/5] Analyzing audio", file=sys.stderr)
        for core_frames, interval in iter_inference(input_path, source.duration_seconds,
                settings.chunk_seconds, settings.context_seconds, model):
            frames.extend(core_frames)
            result.analyzed_intervals.append(interval)
        result.events = assemble_events(frames, settings.onset, settings.offset, settings.merge_gap_seconds)
        result.clips = build_clips(result.events, source.duration_seconds, settings.clip_padding_seconds,
                                   settings.max_clip_seconds)
        result.metrics = calculate_metrics(result.events, result.clips, source.duration_seconds,
                                            result.analyzed_intervals, complete=True)
        print("[4/5] Exporting clips", file=sys.stderr)
        for clip in result.clips:
            export_clip(input_path, clip, staging / clip.filename, settings.mp3_kbps)
        if sha256_file(input_path) != original_digest:
            raise InputError("source changed during analysis")
        result.status = "complete"
        exit_code = 0
    except KeyboardInterrupt:
        result.status = "cancelled"
        result.warnings.append("Analysis was cancelled by the user.")
        exit_code = 130
    except InputError as error:
        result.warnings.append(str(error))
        exit_code = EXIT_INPUT
    except DependencyError as error:
        result.warnings.append(str(error))
        exit_code = EXIT_DEPENDENCY
    except Exception as error:
        if result.analyzed_intervals:
            result.status = "partial"
        result.warnings.append(f"{type(error).__name__}: {error}")
        exit_code = EXIT_PROCESSING
    finally:
        elapsed = time.perf_counter() - started
        processing.finished_utc = utc_now()
        processing.runtime_seconds = elapsed
        if result.source and result.source.duration_seconds:
            processing.real_time_factor = elapsed / result.source.duration_seconds
        processing.peak_working_set_bytes = psutil.Process().memory_info().peak_wset if os.name == "nt" else psutil.Process().memory_info().rss
        if result.status != "complete":
            if frames and not result.events:
                result.events = assemble_events(frames, settings.onset, settings.offset, settings.merge_gap_seconds)
            # Retain only clips fully written before interruption and remove dangling links.
            result.clips = [clip for clip in result.clips if (staging / clip.filename).is_file()]
            valid_clip_ids = {clip.id for clip in result.clips}
            for event in result.events:
                event.clip_ids = [clip_id for clip_id in event.clip_ids if clip_id in valid_clip_ids]
            result.metrics = None
        if result.metrics is None and result.source:
            result.metrics = calculate_metrics(result.events, result.clips, result.source.duration_seconds,
                                                result.analyzed_intervals, complete=False)
        (staging / "run.log").write_text("\n".join(result.warnings) + "\n", encoding="utf-8")
        print("[5/5] Writing reports", file=sys.stderr)
        write_reports(staging, result, make_zip=result.status == "complete")
        (staging / ".active").unlink(missing_ok=True)
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + token[:6]
        digest_part = result.source.sha256[:12] if result.source else "unknown"
        final = output_root / f"{safe_stem(input_path.name)}_{digest_part}_{run_id}"
        _publish(staging, final)
        print(str(final.resolve()))
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dog-audio")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("input", type=Path)
    analyze_parser.add_argument("--output", type=Path, required=True)
    analyze_parser.add_argument("--config", type=Path)
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("--offline", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "doctor":
            return doctor(args.offline)
        return analyze(args.input, args.output, args.config)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_INVOCATION


if __name__ == "__main__":
    raise SystemExit(main())
