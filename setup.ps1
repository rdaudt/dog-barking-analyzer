$ErrorActionPreference = "Stop"

Write-Host "Synchronizing the pinned Python 3.13 environment..."
uv sync --frozen

foreach ($program in @("ffmpeg", "ffprobe")) {
    $command = Get-Command $program -ErrorAction SilentlyContinue
    if (-not $command) { throw "$program is not available on PATH" }
    $versionOutput = @(& $program -version 2>&1)
    $programExitCode = $LASTEXITCODE
    if ($programExitCode -ne 0) { throw "$program failed its version check (exit $programExitCode)" }
    $firstLine = $versionOutput[0]
    if ($firstLine -match 'version N-') {
        Write-Host "$program`: $firstLine"
        continue
    }
    if ($firstLine -notmatch 'version\s+n?(\d+)\.(\d+)') { throw "Could not parse $program version: $firstLine" }
    $version = [version]::new([int]$Matches[1], [int]$Matches[2])
    if ($version -lt [version]::new(6, 1)) { throw "$program 6.1 or newer is required; found $version" }
    Write-Host "$program`: $firstLine"
}

Write-Host "Caching YAMNet and verifying its Bark label..."
uv run python -c "from dog_audio.inference import Yamnet; m=Yamnet(); print('Bark class:',m.bark_index,'digest:',m.digest)"
if ($LASTEXITCODE -ne 0) { throw "YAMNet cache setup failed" }

Write-Host "Proving the cached model is visible to offline diagnostics..."
uv run dog-audio doctor --offline
if ($LASTEXITCODE -ne 0) { throw "Offline YAMNet cache verification failed" }

Write-Host "Setup complete."
