# Dog Barking Analyzer

A local, CPU-only Windows CLI that finds suspected dog-bark episodes in M4A/AAC, MP3, and WAV recordings using Google's YAMNet model. It creates timestamped MP3 review clips and portable HTML, text, CSV, JSON, and ZIP reports. The recording is read-only and is never included in the report ZIP.

Operational procedures are in the [runbook](docs/RUNBOOK.md). The original product requirements are archived in [docs](docs/dog-barking-analyzer-prd.pdf).

## Install

Install 64-bit Windows FFmpeg 6.1 or newer, Git, and [uv](https://docs.astral.sh/uv/). Then run:

```powershell
git clone https://github.com/rdaudt/dog-barking-analyzer.git
cd dog-barking-analyzer
.\setup.ps1
```

The setup pins Python 3.13 and all Python dependencies from `uv.lock`, checks FFmpeg/ffprobe, downloads YAMNet into the TensorFlow Hub cache, and verifies that the cache is available for offline use. After setup, analysis does not require a network connection:

```powershell
uv run dog-audio doctor --offline
```

## Analyze a recording

```powershell
uv run dog-audio analyze "C:\Recordings\night.m4a" --output "C:\BarkReports"
uv run dog-audio analyze "C:\Recordings\night.m4a" --output "C:\BarkReports" --config config\sensitive.toml
```

Progress goes to stderr. On completion, stdout contains the new run directory. Every analysis creates a unique directory; existing reports are not overwritten.

The default preset starts an episode at a Bark score of 0.30 and continues it at 0.20. The provisional sensitive preset uses 0.20/0.10 and may produce more false detections. Both use 60-second cores, 0.96-second context, a 3-second merge gap, 2-second clip padding, 5-minute clip parts, and 128 kbps MP3.

## Outputs

- `index.html`: portable overview with native audio controls
- `summary.txt`: phone-readable episode list and clip names
- `events.csv`: exact episode values for spreadsheets
- `results.json`: schema-versioned machine-readable result
- `clips/*.mp3`: padded review audio, split at five minutes if needed
- `report.zip`: complete portable report (successful runs only)
- `run.log`: local diagnostics; intentionally excluded from the ZIP

Elapsed times are offsets from the beginning of the recording, not wall-clock times. Active time is the union of detected frame intervals; episode span includes gaps merged into an episode; review time is the union of padded clip intervals. Overlapping padded episodes share a clip and do not double-count review time.

## Google Drive handoff

Drive integration is manual in this MVP:

1. Download the recording from Google Drive to the PC.
2. Run `dog-audio analyze` against that local file.
3. Upload `summary.txt` and every file under `clips` to Drive.
4. Open the uploaded MP3 files on the phone and verify playback before deleting local copies.

All inference remains on the PC. The tool does not upload recordings or results.

## Important limitations

YAMNet Bark scores are model confidence scores, not calibrated probabilities. Episode count is not bark count: several barks can form one episode, and one long episode may be split into multiple clip files. No detection does not prove silence or prove that no dog bark occurred. Apartment-specific precision/recall calibration, wall-clock metadata, GUI, batch processing, annotations, other dog vocalizations, folder watching, and automatic Drive transfers are outside this MVP.

The CLI records runtime, real-time factor, dependency versions, model asset digest, Bark class index, and peak working set in `results.json`. Performance has no pass/fail threshold; record reference measurements on the target i7-8550U/24 GB PC using a representative recording.

## Exit codes

- `0`: complete
- `2`: invocation or configuration error
- `3`: invalid or unsupported input
- `4`: dependency or model failure
- `5`: processing failure
- `130`: cancelled with Ctrl+C

Failed, partial, and cancelled runs retain diagnostic reports and any valid analyzed intervals, but omit whole-recording percentages and the ZIP.

## Development

```powershell
uv sync --frozen
uv run pytest
uv run coverage run -m pytest
uv run coverage report
```
