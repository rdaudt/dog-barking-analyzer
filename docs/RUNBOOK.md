# Dog Barking Analyzer Runbook

This runbook is for the person operating Dog Barking Analyzer on Windows. It covers initial setup, routine analysis, result validation, offline operation, recovery, and troubleshooting.

## 1. Operating boundaries

- Supported inputs: M4A/AAC, MP3, and WAV files containing an audio stream.
- Processing is local and CPU-only. The application does not upload recordings or reports.
- Input files are treated as read-only and checked for changes during analysis.
- Timestamps are elapsed offsets from the beginning of the recording, not wall-clock times.
- YAMNet Bark scores are model confidence scores, not calibrated probabilities.
- An episode can contain several barks. Episode count is not bark count.
- No detections do not prove that a recording contains no barking.

## 2. First-time setup

### Prerequisites

Install these tools before cloning the repository:

- Windows 11 x64
- Git
- [uv](https://docs.astral.sh/uv/)
- 64-bit FFmpeg 6.1 or newer, with both `ffmpeg` and `ffprobe` on `PATH`
- An internet connection for the initial YAMNet download

Confirm that Git and uv are available:

```powershell
git --version
uv --version
```

Clone and initialize the application:

```powershell
git clone https://github.com/rdaudt/dog-barking-analyzer.git
cd dog-barking-analyzer
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Setup is successful only when it ends with `Setup complete.` The script creates the pinned Python 3.13 environment, verifies FFmpeg, caches YAMNet, resolves the Bark class by label, and proves that the cached model can be reloaded.

### Validate the installation

Run the offline diagnostic after setup and after dependency or machine changes:

```powershell
uv run dog-audio doctor --offline
```

Expected result:

- Exit code `0`
- FFmpeg and ffprobe version details
- `YAMNet: offline reload ready`
- A Bark class index and model digest

In PowerShell, inspect the last exit code with:

```powershell
$LASTEXITCODE
```

## 3. Prepare a recording

1. Download the recording from Google Drive or copy it from the recording device.
2. Store it in a local folder with enough free space for reports and MP3 clips.
3. Do not edit, replace, rename, or synchronize the file while analysis is running.
4. Confirm that the extension is `.m4a`, `.mp3`, or `.wav`.

The application requires free output space equal to the larger of 512 MiB or its conservative MP3-and-ZIP estimate. Low disk space is rejected before model inference begins.

## 4. Run an analysis

Create reports in a separate output root:

```powershell
uv run dog-audio analyze "C:\Recordings\night.m4a" --output "C:\BarkReports"
```

For the provisional sensitive preset:

```powershell
uv run dog-audio analyze "C:\Recordings\night.m4a" --output "C:\BarkReports" --config ".\config\sensitive.toml"
```

Use the default preset unless more sensitivity is deliberately required. The sensitive preset lowers the onset and continuation thresholds and can create more false detections.

### Monitor progress

The CLI reports these phases to stderr:

1. Inspecting input
2. Loading YAMNet
3. Analyzing audio
4. Exporting clips
5. Writing reports

On completion, stdout prints the absolute path of the new run directory. Re-running the same input creates another uniquely named directory and never overwrites a prior report.

## 5. Validate a completed run

A successful command exits with code `0`. Open the printed run directory and verify that it contains:

- `index.html`
- `summary.txt`
- `events.csv`
- `results.json`
- `run.log`
- `report.zip`
- `clips\` when episodes were detected

Perform these checks before handing off results:

1. Open `summary.txt` and confirm that its status is `complete`.
2. Open `index.html` in a browser and confirm that the report loads locally.
3. If episodes exist, play at least the first and last MP3 clip.
4. Confirm that elapsed timestamps and clip names agree between `summary.txt` and `index.html`.
5. Extract `report.zip` into a different folder and confirm that `index.html` still opens and uses relative clip links.
6. Confirm that the ZIP does not contain the original recording or `run.log`.

No-detection runs can legitimately have no `clips` directory. They must still contain the four report formats and `report.zip`.

## 6. Interpret the outputs

- **Episode:** A logical period assembled from Bark-scored model frames using onset/offset thresholds and the configured merge gap.
- **Active time:** The union of detected frame intervals, without double-counting overlaps.
- **Episode span:** Time from each episode's start to end, including short gaps merged into that episode.
- **Review time:** The union of padded clip intervals. Overlapping padded episodes share a clip.
- **Coverage:** The portion of the recording successfully analyzed. It is included only for complete runs.
- **Clip parts:** Export intervals longer than five minutes are split into numbered MP3 files without increasing the episode count.

Use the audio clips for human review. Do not interpret Bark scores as probabilities or use the report as proof of silence.

## 7. Google Drive handoff

1. Upload `summary.txt` from the completed run.
2. Upload every MP3 file under `clips\`.
3. Optionally upload `report.zip` for archival or desktop review.
4. Open at least one uploaded MP3 on the target phone.
5. Verify that playback works and that the filename appears in `summary.txt`.

Do not upload the original recording as part of the generated report unless the owner separately intends to share it.

## 8. Cancellation and incomplete runs

Press `Ctrl+C` once to cancel gracefully. The application publishes a diagnostic run with status `cancelled`, retains fully written clips and valid analyzed events, omits whole-recording coverage, and does not create `report.zip`.

Other interrupted or failed work can have status `partial` or `failed`. Preserve the directory until troubleshooting is complete because `results.json` and `run.log` contain the diagnostic context.

The application removes abandoned staging directories older than 24 hours when a new run starts. It does not remove a staging directory owned by a live process. Do not manually delete a `.staging-...` directory while another analysis may be active.

## 9. Troubleshooting by exit code

| Exit code | Meaning | Operator action |
| ---: | --- | --- |
| `0` | Complete | Perform the completed-run validation checklist. |
| `2` | Invocation or configuration error | Check command spelling, quoting, paths, and TOML settings. |
| `3` | Invalid input | Confirm the file exists, is non-empty, is not corrupt, and contains supported audio. |
| `4` | Dependency or model failure | Run `doctor --offline`, verify FFmpeg is on `PATH`, then rerun `setup.ps1` with internet access if the model cache is missing or invalid. |
| `5` | Processing failure | Read `run.log` and the warnings in `results.json`; retain the diagnostic directory. |
| `130` | Cancelled | Review the cancelled result or start a new analysis. |

### FFmpeg or ffprobe is not found

```powershell
ffmpeg -version
ffprobe -version
```

If either command fails, install FFmpeg 6.1 or newer, add its `bin` directory to the system or user `PATH`, open a new terminal, and rerun the diagnostic.

### Offline model check fails

Connect the machine to the internet and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
uv run dog-audio doctor --offline
```

Do not copy an unknown or partial TensorFlow Hub cache into place. The offline diagnostic loads the cached SavedModel and verifies its Bark class before returning success.

### Input is rejected

Inspect its streams:

```powershell
ffprobe -v error -show_streams -show_format -of json "C:\Recordings\night.m4a"
```

The file must contain a supported AAC, MP3, or WAV audio stream. Renaming an unsupported file extension does not convert it.

### Insufficient disk space

Choose an output root on a drive with more free space. Do not delete an active staging directory. Completed run directories are independent and may be archived or removed according to the owner's retention policy.

### Source changed during analysis

Copy the recording to a local, non-synchronized folder and run it again. Pause editing and cloud synchronization for that file until analysis completes.

## 10. Collect diagnostics for escalation

When a problem persists, retain and provide:

- The exact command used, with private paths redacted if needed
- The process exit code
- `run.log`
- `results.json`
- Output from `uv run dog-audio doctor --offline`
- Output from `ffmpeg -version` and `ffprobe -version`
- Windows version and available disk space

Do not provide the source recording unless its owner explicitly authorizes sharing it. Review `results.json` and logs for filenames before sending diagnostics outside the machine.

## 11. Updating and verifying the application

From a clean repository checkout:

```powershell
git pull --ff-only
uv sync --frozen
uv run pytest -q
uv run dog-audio doctor --offline
```

Do not continue with routine operation if the test suite or offline diagnostic fails. Record the failure and follow the troubleshooting guidance above.

