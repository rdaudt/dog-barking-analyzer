import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .models import Clip, SourceIdentity


class InputError(RuntimeError):
    pass


class DependencyError(RuntimeError):
    pass


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def parse_probe(data: dict, path: Path, digest: str, size: int) -> SourceIdentity:
    streams = [item for item in data.get("streams", []) if item.get("codec_type") == "audio"]
    if not streams:
        raise InputError("input has no audio stream")
    codec = str(streams[0].get("codec_name", "")).lower()
    format_name = str(data.get("format", {}).get("format_name", "")).lower()
    allowed = codec in {"aac", "mp3", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_f64le"}
    allowed = allowed and ("wav" in format_name or "mp3" in format_name or any(x in format_name for x in ("m4a", "mov", "mp4")))
    if not allowed:
        raise InputError(f"unsupported audio codec/container: {codec or 'unknown'}/{format_name or 'unknown'}")
    try:
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise InputError("input duration is unavailable") from error
    if duration <= 0:
        raise InputError("input is empty")
    return SourceIdentity(filename=path.name, sha256=digest, size_bytes=size,
                          duration_seconds=duration, codec=codec, format_name=format_name)


def probe_input(path: Path) -> SourceIdentity:
    if not path.is_file() or path.stat().st_size == 0:
        raise InputError("input is missing or empty")
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    digest = sha256_file(path)
    try:
        process = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                  "-of", "json", str(path)], capture_output=True, text=True, check=False)
    except FileNotFoundError as error:
        raise DependencyError("ffprobe is not installed or not on PATH") from error
    if process.returncode:
        raise InputError(f"ffprobe could not read input: {process.stderr.strip()}")
    try:
        result = parse_probe(json.loads(process.stdout), path, digest, before[0])
    except json.JSONDecodeError as error:
        raise InputError("ffprobe returned invalid metadata") from error
    after = (path.stat().st_size, path.stat().st_mtime_ns)
    if before != after or sha256_file(path) != digest:
        raise InputError("source changed while it was being inspected")
    return result


def required_free_bytes(duration_seconds: float, mp3_kbps: int) -> int:
    estimated_mp3 = duration_seconds * mp3_kbps * 1000 / 8
    estimated_zip = estimated_mp3 * 1.05
    estimate = int((estimated_mp3 + estimated_zip) * 2.5 + 100 * 1024 * 1024)
    return max(512 * 1024 * 1024, estimate)


def ensure_space(output_root: Path, needed: int) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output_root).free < needed:
        raise OSError(f"insufficient output space: need at least {needed} bytes free")


def decode_pcm(path: Path, start: float, duration: float) -> bytes:
    command = ["ffmpeg", "-v", "error", "-ss", f"{start:.6f}", "-t", f"{duration:.6f}",
               "-i", str(path), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"]
    try:
        process = subprocess.run(command, capture_output=True, check=False)
    except FileNotFoundError as error:
        raise DependencyError("ffmpeg is not installed or not on PATH") from error
    if process.returncode:
        raise RuntimeError(process.stderr.decode(errors="replace").strip())
    return process.stdout


def export_clip(source: Path, clip: Clip, destination: Path, kbps: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{clip.start_seconds:.6f}",
            "-t", f"{clip.end_seconds-clip.start_seconds:.6f}", "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1",
            "-codec:a", "libmp3lame", "-b:a", f"{kbps}k", str(destination)], capture_output=True, check=False)
    except FileNotFoundError as error:
        raise DependencyError("ffmpeg is not installed or not on PATH") from error
    if process.returncode:
        raise RuntimeError(process.stderr.decode(errors="replace").strip())
