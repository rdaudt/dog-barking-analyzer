import csv
import json
import zipfile
from html import escape
from pathlib import Path

from .models import RunResult


CSV_COLUMNS = ["event ID", "start seconds", "end seconds", "start elapsed", "end elapsed",
               "span seconds", "peak Bark score", "mean Bark score", "clip filenames"]


def _safe_csv(value: object) -> object:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def write_reports(directory: Path, result: RunResult, make_zip: bool) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    (directory / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    title = f"Dog Barking Analyzer — {result.source.filename if result.source else 'incomplete run'}"
    lines = [title, f"Status: {result.status}", f"Episodes: {len(result.events)}"]
    if result.metrics:
        lines.extend([f"Analyzed: {result.metrics.analyzed_seconds:.2f} seconds",
                      f"Active time: {result.metrics.active_seconds:.2f} seconds",
                      f"Review time: {result.metrics.review_seconds:.2f} seconds"])
        if result.metrics.coverage_percent is not None:
            lines.append(f"Coverage: {result.metrics.coverage_percent:.2f}%")
    lines.append("")
    for event in result.events:
        filenames = [clip.filename for clip in result.clips if clip.id in event.clip_ids]
        lines.append(f"{event.id} {event.start_elapsed}–{event.end_elapsed} | " + ", ".join(filenames))
    if result.warnings:
        lines.extend(["", "Warnings:", *(f"- {warning}" for warning in result.warnings)])
    (directory / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (directory / "events.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for event in result.events:
            names = ";".join(clip.filename for clip in result.clips if clip.id in event.clip_ids)
            writer.writerow(map(_safe_csv, [event.id, event.start_seconds, event.end_seconds,
                event.start_elapsed, event.end_elapsed, event.span_seconds, event.peak_score,
                event.mean_score, names]))

    cards = "".join(f'<article><h2>{escape(event.id)} — {escape(event.start_elapsed)}</h2>'
        + "".join(f'<audio controls preload="metadata" src="{escape(clip.filename)}"></audio>'
                  for clip in result.clips if clip.id in event.clip_ids) + "</article>" for event in result.events)
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(title)}</title><style>body{{font:16px system-ui;max-width:52rem;margin:auto;padding:1rem;background:#f7f4ed;color:#18201b}}article{{background:white;padding:1rem;margin:1rem 0;border-radius:.6rem}}audio{{width:100%}}</style>
<h1>{escape(title)}</h1><p>Status: {escape(result.status)} · Episodes: {len(result.events)}</p>{cards}</html>'''
    (directory / "index.html").write_text(html, encoding="utf-8")

    if make_zip and result.status == "complete":
        archive = directory / "report.zip"
        allowed = ["index.html", "summary.txt", "events.csv", "results.json"]
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name in allowed:
                bundle.write(directory / name, name)
            for clip in result.clips:
                path = directory / clip.filename
                if path.is_file():
                    bundle.write(path, clip.filename)

