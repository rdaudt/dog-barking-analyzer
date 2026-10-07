from pathlib import Path
import tomllib

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    onset: float = Field(0.30, ge=0, le=1)
    offset: float = Field(0.20, ge=0, le=1)
    chunk_seconds: float = Field(60.0, gt=0)
    context_seconds: float = Field(0.96, gt=0)
    merge_gap_seconds: float = Field(3.0, ge=0)
    clip_padding_seconds: float = Field(2.0, ge=0)
    max_clip_seconds: float = Field(300.0, gt=0)
    mp3_kbps: int = Field(128, gt=0)

    @model_validator(mode="after")
    def validate_relationships(self):
        if self.offset >= self.onset:
            raise ValueError("offset must be less than onset")
        if self.clip_padding_seconds >= self.chunk_seconds:
            raise ValueError("clip padding must be less than chunk duration")
        return self


def load_settings(path: Path) -> Settings:
    with path.open("rb") as handle:
        return Settings.model_validate(tomllib.load(handle))
