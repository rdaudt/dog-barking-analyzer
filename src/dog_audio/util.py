import re
from pathlib import Path


def format_elapsed(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours}:{minutes:02d}:{secs:02d}.{millis:03d}"


def safe_stem(name: str) -> str:
    stem = Path(name.strip()).stem
    stem = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip(" ._")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if not stem or stem.upper() in reserved:
        return "recording"
    return stem[:80]

