from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Frame(Contract):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    score: float = Field(ge=0, le=1)


class SourceIdentity(Contract):
    filename: str
    sha256: str
    size_bytes: int
    duration_seconds: float
    codec: str
    format_name: str


class Event(Contract):
    id: str
    start_seconds: float
    end_seconds: float
    start_elapsed: str
    end_elapsed: str
    span_seconds: float
    peak_score: float
    mean_score: float
    clip_ids: list[str] = []


class Clip(Contract):
    id: str
    event_ids: list[str]
    start_seconds: float
    end_seconds: float
    filename: str
    part_index: int
    part_count: int


class Metrics(Contract):
    analyzed_seconds: float
    coverage_percent: float | None = None
    active_seconds: float
    episode_span_seconds: float
    review_seconds: float
    first_detection_seconds: float | None = None
    longest_episode_seconds: float | None = None
    episode_count: int


class Processing(Contract):
    started_utc: str
    finished_utc: str | None = None
    runtime_seconds: float | None = None
    real_time_factor: float | None = None
    peak_working_set_bytes: int | None = None
    model_uri: str = "https://tfhub.dev/google/yamnet/1"
    model_digest: str | None = None
    bark_class_index: int | None = None
    dependencies: dict[str, str] = {}


class RunResult(Contract):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["complete", "partial", "failed", "cancelled"]
    source: SourceIdentity | None = None
    settings: dict
    events: list[Event] = []
    clips: list[Clip] = []
    metrics: Metrics | None = None
    processing: Processing
    analyzed_intervals: list[tuple[float, float]] = []
    warnings: list[str] = []

