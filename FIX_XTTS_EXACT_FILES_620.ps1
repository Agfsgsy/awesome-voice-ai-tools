# Exact-file XTTS repair for Ibn Al-Waqadi Studio 6.2.0.
# ASCII-only for Windows PowerShell 5.1 compatibility.
# No project build, main.py edit, HTML edit, or user-data deletion is performed.

$ErrorActionPreference = 'Stop'

function Step([string]$Text) {
    Write-Host $Text -ForegroundColor Cyan
}

$engine = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine'
$python = Join-Path $engine 'venv\Scripts\python.exe'
$cache = Join-Path $engine 'tts_cache'
$modelDir = Join-Path $cache 'tts_models--multilingual--multi-dataset--xtts_v2'
$worker = Join-Path $engine 'download_exact_xtts_files.py'
$marker = Join-Path $engine 'xtts_model_ready.json'
$status = Join-Path $engine 'setup_status.json'
$runtime = Join-Path $engine 'xtts_runtime.json'
$app = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host ' Ibn Al-Waqadi Studio 6.2 - Exact XTTS Files Repair' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'This repair downloads/finalizes only model.pth, config.json and vocab.json.' -ForegroundColor Yellow
Write-Host 'Existing downloaded pieces are reused. No project build will run.' -ForegroundColor Yellow
Write-Host ''

Step '[1/7] Stopping the repeating downloader and Studio workers...'
Get-Process -Name 'VoiceAIStudioArabic' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
try {
    Get-CimInstance Win32_Process | Where-Object {
        $exe = [string]$_.ExecutablePath
        $cmd = [string]$_.CommandLine
        ($exe -and $exe.StartsWith($engine, [System.StringComparison]::OrdinalIgnoreCase)) -or
        ($cmd -and $cmd.IndexOf($engine, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Seconds 2

Step '[2/7] Checking the XTTS Python environment...'
if (-not (Test-Path -LiteralPath $python)) {
    throw "XTTS Python environment was not found: $python"
}
New-Item -ItemType Directory -Path $modelDir -Force | Out-Null

Step '[3/7] Downloading the three exact required files with automatic retries...'
$py = @'
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from huggingface_hub import hf_hub_download

repo_id = "coqui/XTTS-v2"
target = Path(os.environ["IBN_XTTS_TARGET"]).resolve()
target.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "900")
os.environ.setdefault("COQUI_TOS_AGREED", "1")

required = {
    "model.pth": 500_000_000,
    "config.json": 500,
    "vocab.json": 10_000,
}


def valid(path: Path, minimum: int) -> bool:
    if not path.exists() or path.stat().st_size < minimum:
        return False
    if path.suffix.lower() == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
    return True


def materialize(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except Exception:
        shutil.copy2(source, destination)

for filename, minimum in required.items():
    destination = target / filename
    if valid(destination, minimum):
        print(f"EXISTING_OK {filename} {destination.stat().st_size}", flush=True)
        continue

    last_error = None
    for attempt in range(1, 21):
        try:
            print(f"DOWNLOADING {filename} ATTEMPT {attempt}/20", flush=True)
            downloaded = Path(
                hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=str(target),
                    force_download=False,
                )
            )
            materialize(downloaded, destination)
            if not valid(destination, minimum):
                raise RuntimeError(
                    f"{filename} is still incomplete: "
                    f"{destination.stat().st_size if destination.exists() else 0} bytes"
                )
            print(f"FILE_OK {filename} {destination.stat().st_size}", flush=True)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            print(f"RETRY {filename}: {type(exc).__name__}: {exc}", flush=True)
            if attempt < 20:
                time.sleep(min(60, 5 + attempt * 3))
    if last_error is not None:
        raise RuntimeError(f"Could not complete {filename}: {last_error}")

for filename, minimum in required.items():
    path = target / filename
    if not valid(path, minimum):
        raise RuntimeError(f"Final validation failed for {filename}")

print("XTTS_EXACT_FILES_READY", flush=True)
'@
$py | Set-Content -LiteralPath $worker -Encoding ASCII

$env:IBN_XTTS_TARGET = $modelDir
$env:HF_HUB_DISABLE_XET = '1'
$env:HF_HUB_ETAG_TIMEOUT = '30'
$env:HF_HUB_DOWNLOAD_TIMEOUT = '900'
$env:COQUI_TOS_AGREED = '1'
& $python $worker
if ($LASTEXITCODE -ne 0) {
    throw "Exact XTTS file download failed with exit code $LASTEXITCODE. Run the same command again; saved pieces will be reused."
}

Step '[4/7] Verifying the completed files...'
$model = Join-Path $modelDir 'model.pth'
$config = Join-Path $modelDir 'config.json'
$vocab = Join-Path $modelDir 'vocab.json'
foreach ($file in @($model, $config, $vocab)) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing final file: $file" }
}
if ((Get-Item -LiteralPath $model).Length -lt 500000000) { throw 'model.pth is incomplete.' }
if ((Get-Item -LiteralPath $config).Length -lt 500) { throw 'config.json is incomplete.' }
if ((Get-Item -LiteralPath $vocab).Length -lt 10000) { throw 'vocab.json is incomplete.' }
$null = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
$null = Get-Content -LiteralPath $vocab -Raw -Encoding UTF8 | ConvertFrom-Json
$totalBytes = (Get-ChildItem -LiteralPath $modelDir -File -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$totalMb = [Math]::Round(([double]$totalBytes / 1MB), 1)
Write-Host "XTTS_MODEL_MB=$totalMb" -ForegroundColor Green

Step '[5/7] Preserving old status and writing verified readiness...'
foreach ($file in @($marker, $status, $runtime)) {
    if (Test-Path -LiteralPath $file) {
        Copy-Item -LiteralPath $file -Destination ($file + '.backup-' + $stamp) -Force
    }
}
if (Test-Path -LiteralPath $runtime) {
    Move-Item -LiteralPath $runtime -Destination ($runtime + '.stale-' + $stamp) -Force
}
$now = [DateTime]::UtcNow.ToString('o')
[ordered]@{
    ready = $true
    model_dir = $modelDir
    detail = "Validated exact XTTS files ($totalMb MB)."
    details = "Validated exact XTTS files ($totalMb MB)."
    prepared_at = $now
    updated_at = $now
    coqui = '0.27.5'
    torch = '2.5.1'
    transformers = '4.57.6'
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $marker -Encoding UTF8

[ordered]@{
    state = 'ready'
    status = 'ready'
    message = 'XTTS exact files are complete and ready. The model will load on first generation.'
    progress = 100
    error = ''
    phase = 'ready'
    downloaded_mb = $totalMb
    resumable = $true
    model_dir = $modelDir
    updated_at = $now
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $status -Encoding UTF8

Step '[6/7] Saving the correct XTTS cache location...'
[Environment]::SetEnvironmentVariable('TTS_HOME', $cache, 'User')
[Environment]::SetEnvironmentVariable('COQUI_TOS_AGREED', '1', 'User')
$env:TTS_HOME = $cache
$env:COQUI_TOS_AGREED = '1'

Step '[7/7] Starting Ibn Al-Waqadi Studio...'
if (Test-Path -LiteralPath $app) {
    Start-Process -FilePath $app
} else {
    Write-Host "Studio executable was not found at: $app" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'SUCCESS: XTTS exact files are complete and ready at 100 percent.' -ForegroundColor Green
Write-Host "MODEL_DIR=$modelDir" -ForegroundColor Green
Write-Host "MODEL_MB=$totalMb" -ForegroundColor Green
Write-Host 'No application build or user-data deletion was performed.' -ForegroundColor Green
Write-Host 'The first local generation may take several minutes while XTTS loads into RAM.' -ForegroundColor Yellow
Write-Host '========================================================================' -ForegroundColor DarkCyan
Read-Host 'Press Enter to close'
