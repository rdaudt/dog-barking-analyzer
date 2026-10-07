import csv
import hashlib
import importlib.metadata
import math
import os
from pathlib import Path
from typing import Iterator

import numpy as np

from .media import decode_pcm
from .models import Frame

MODEL_URI = "https://tfhub.dev/google/yamnet/1"
FRAME_WINDOW = 0.96
FRAME_HOP = 0.48


def model_cache_dir() -> Path:
    configured = os.environ.get("TFHUB_CACHE_DIR")
    if configured:
        return Path(configured)
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    return base / "dog-audio" / "tfhub"


def resolve_bark_index(class_map_path: Path) -> int:
    with class_map_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("display_name", "").strip().casefold() == "bark":
                return int(row["index"])
    raise RuntimeError("YAMNet class map does not contain the Bark label")


def owns_frame(center: float, core_start: float, core_end: float, final: bool) -> bool:
    return core_start <= center <= core_end if final else core_start <= center < core_end


def directory_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    elif path.exists():
        for item in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(item.relative_to(path).as_posix().encode())
            with item.open("rb") as handle:
                while block := handle.read(1024 * 1024):
                    digest.update(block)
    return digest.hexdigest()


class Yamnet:
    def __init__(self, uri: str = MODEL_URI):
        cache = model_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("TFHUB_CACHE_DIR", str(cache))
        import tensorflow_hub as hub
        resolved = Path(hub.resolve(uri))
        self.model = hub.load(str(resolved))
        raw_path = self.model.class_map_path().numpy()
        self.class_map_path = Path(raw_path.decode() if isinstance(raw_path, bytes) else str(raw_path))
        self.bark_index = resolve_bark_index(self.class_map_path)
        self.digest = directory_digest(resolved)

    def score(self, waveform: np.ndarray) -> np.ndarray:
        scores, _, _ = self.model(waveform)
        return np.asarray(scores)[:, self.bark_index]

    @staticmethod
    def versions() -> dict[str, str]:
        names = ("tensorflow", "tensorflow-hub", "numpy", "pydantic", "jinja2", "psutil")
        return {name: importlib.metadata.version(name) for name in names}


def iter_inference(source: Path, duration: float, chunk_seconds: float, context_seconds: float,
                   yamnet: Yamnet) -> Iterator[tuple[list[Frame], tuple[float, float]]]:
    core_count = max(1, math.ceil(duration / chunk_seconds))
    for number in range(core_count):
        core_start = number * chunk_seconds
        core_end = min(duration, (number + 1) * chunk_seconds)
        segment_start = max(0.0, core_start - context_seconds)
        segment_end = min(duration, core_end + context_seconds)
        waveform = np.frombuffer(decode_pcm(source, segment_start, segment_end-segment_start), dtype="<f4")
        scores = yamnet.score(waveform)
        frames: list[Frame] = []
        for index, score in enumerate(scores):
            local_start = index * FRAME_HOP
            global_start = segment_start + local_start
            global_end = global_start + FRAME_WINDOW
            center = global_start + FRAME_WINDOW / 2
            if not owns_frame(center, core_start, core_end, final=number == core_count-1):
                continue
            if global_start < 0 or global_end > duration:
                if core_start != 0 and core_end != duration:
                    continue
            frames.append(Frame(start_seconds=max(0, global_start), end_seconds=min(duration, global_end),
                                score=float(score)))
        yield frames, (core_start, core_end)
