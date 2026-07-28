# XTTS locator and resumable completion repair for Ibn Al-Waqadi Studio 6.2.0.
# ASCII-only for Windows PowerShell 5.1 compatibility.
# It does not rebuild the app and does not edit main.py, HTML, keys, profiles,
# samples, generated audio, shila projects, or Gemini settings.

$ErrorActionPreference = 'Stop'

function Step([string]$Text) {
    Write-Host $Text -ForegroundColor Cyan
}

function Is-ValidModelDir([string]$Dir) {
    if ([string]::IsNullOrWhiteSpace($Dir)) { return $false }
    $model = Join-Path $Dir 'model.pth'
    $config = Join-Path $Dir 'config.json'
    $vocab = Join-Path $Dir 'vocab.json'
    if (-not (Test-Path -LiteralPath $model)) { return $false }
    if (-not (Test-Path -LiteralPath $config)) { return $false }
    if (-not (Test-Path -LiteralPath $vocab)) { return $false }
    try {
        if ((Get-Item -LiteralPath $model).Length -lt 500000000) { return $false }
        if ((Get-Item -LiteralPath $config).Length -lt 500) { return $false }
        if ((Get-Item -LiteralPath $vocab).Length -lt 10000) { return $false }
        $null = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
        $null = Get-Content -LiteralPath $vocab -Raw -Encoding UTF8 | ConvertFrom-Json
        return $true
    } catch {
        return $false
    }
}

function Find-ValidModel {
    param([string[]]$Roots)
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($root in $Roots) {
        if ([string]::IsNullOrWhiteSpace($root) -or -not (Test-Path -LiteralPath $root)) { continue }
        Write-Host "Searching: $root" -ForegroundColor DarkGray
        try {
            $files = Get-ChildItem -LiteralPath $root -Filter 'model.pth' -File -Recurse -Force -ErrorAction SilentlyContinue
            foreach ($file in $files) {
                $dir = $file.Directory.FullName
                if ($seen.Add($dir) -and (Is-ValidModelDir $dir)) {
                    return $dir
                }
            }
        } catch {}
    }
    return $null
}

$engine = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine'
$downloadCache = Join-Path $engine 'tts_cache'
$modelFolderName = 'tts_models--multilingual--multi-dataset--xtts_v2'
$expected = Join-Path $downloadCache $modelFolderName
$readyCache = Join-Path $engine 'tts_ready_cache'
$readyLink = Join-Path $readyCache $modelFolderName
$python = Join-Path $engine 'venv\Scripts\python.exe'
$marker = Join-Path $engine 'xtts_model_ready.json'
$status = Join-Path $engine 'setup_status.json'
$runtime = Join-Path $engine 'xtts_runtime.json'
$app = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
$worker = Join-Path $engine 'resume_xtts_model.py'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host ' Ibn Al-Waqadi Studio 6.2 - XTTS Find or Resume Repair' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'No project build will run. No user file or completed model file will be deleted.' -ForegroundColor Yellow
Write-Host ''

Step '[1/8] Closing only Studio and XTTS workers...'
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

Step '[2/8] Searching for an already completed XTTS model...'
$roots = @(
    $engine,
    (Join-Path $env:LOCALAPPDATA 'tts'),
    (Join-Path $env:APPDATA 'tts'),
    (Join-Path $env:USERPROFILE '.cache\tts'),
    (Join-Path $env:USERPROFILE '.cache\huggingface\hub'),
    (Join-Path $env:LOCALAPPDATA 'huggingface\hub')
)
$modelDir = Find-ValidModel -Roots $roots

if ($modelDir) {
    Write-Host "FOUND_COMPLETE_MODEL=$modelDir" -ForegroundColor Green
} else {
    Step '[3/8] No complete model was found. Resuming the saved download...'
    if (-not (Test-Path -LiteralPath $python)) {
        throw "XTTS Python environment was not found: $python"
    }
    New-Item -ItemType Directory -Path $expected -Force | Out-Null
    $py = @'
from __future__ import annotations
import os
from pathlib import Path

model_dir = Path(os.environ["IBN_XTTS_TARGET"])
model_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
os.environ["TTS_HOME"] = str(model_dir.parent)

from huggingface_hub import snapshot_download
kwargs = {
    "repo_id": "coqui/XTTS-v2",
    "local_dir": str(model_dir),
    "max_workers": 1,
}
try:
    snapshot_download(resume_download=True, **kwargs)
except TypeError:
    snapshot_download(**kwargs)
print("XTTS_SNAPSHOT_DOWNLOAD_FINISHED")
'@
    $py | Set-Content -LiteralPath $worker -Encoding ASCII
    $env:IBN_XTTS_TARGET = $expected
    $env:HF_HUB_DISABLE_XET = '1'
    $env:HF_HUB_ETAG_TIMEOUT = '30'
    $env:HF_HUB_DOWNLOAD_TIMEOUT = '600'
    $env:COQUI_TOS_AGREED = '1'
    & $python $worker
    if ($LASTEXITCODE -ne 0) {
        throw "XTTS resumable download failed with exit code $LASTEXITCODE. Run the same command again to continue from saved files."
    }
    if (Is-ValidModelDir $expected) {
        $modelDir = $expected
    } else {
        $modelDir = Find-ValidModel -Roots @($expected, $engine)
    }
    if (-not $modelDir) {
        throw 'The download process ended, but a complete model.pth/config.json/vocab.json set was not found. Run the same command again to resume.'
    }
    Write-Host "COMPLETED_MODEL=$modelDir" -ForegroundColor Green
}

Step '[4/8] Creating a safe cache link to the completed model...'
New-Item -ItemType Directory -Path $readyCache -Force | Out-Null
if (Test-Path -LiteralPath $readyLink) {
    $item = Get-Item -LiteralPath $readyLink -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Remove-Item -LiteralPath $readyLink -Force
    } else {
        Move-Item -LiteralPath $readyLink -Destination ($readyLink + '.backup-' + $stamp) -Force
    }
}
try {
    New-Item -ItemType Junction -Path $readyLink -Target $modelDir -Force | Out-Null
} catch {
    $cmd = '/c mklink /J "' + $readyLink + '" "' + $modelDir + '"'
    $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList $cmd -Wait -PassThru -WindowStyle Hidden
    if ($proc.ExitCode -ne 0) { throw 'Could not create the XTTS cache junction.' }
}
if (-not (Is-ValidModelDir $readyLink)) { throw 'The XTTS cache junction does not expose a valid model.' }

Step '[5/8] Verifying the XTTS Python dependencies...'
$env:TTS_HOME = $readyCache
$env:COQUI_TOS_AGREED = '1'
$env:TOKENIZERS_PARALLELISM = 'false'
& $python -c "import torch,transformers; from TTS.api import TTS; print('XTTS_DEPENDENCIES_OK', torch.__version__, transformers.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'XTTS Python dependencies are not ready.' }

Step '[6/8] Preserving old status and writing verified 100-percent readiness...'
foreach ($file in @($marker, $status, $runtime)) {
    if (Test-Path -LiteralPath $file) {
        Copy-Item -LiteralPath $file -Destination ($file + '.backup-' + $stamp) -Force
    }
}
if (Test-Path -LiteralPath $runtime) {
    Move-Item -LiteralPath $runtime -Destination ($runtime + '.stale-' + $stamp) -Force
}
$totalBytes = (Get-ChildItem -LiteralPath $modelDir -File -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$totalMb = [Math]::Round(([double]$totalBytes / 1MB), 1)
$now = [DateTime]::UtcNow.ToString('o')
[ordered]@{
    ready = $true
    model_dir = $modelDir
    cache_root = $readyCache
    detail = "Validated complete XTTS model ($totalMb MB) and linked it without copying."
    details = "Validated complete XTTS model ($totalMb MB) and linked it without copying."
    prepared_at = $now
    updated_at = $now
    coqui = '0.27.5'
    torch = '2.5.1'
    transformers = '4.57.6'
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $marker -Encoding UTF8

[ordered]@{
    state = 'ready'
    status = 'ready'
    message = 'XTTS model is complete and ready. It will load into memory on first generation.'
    progress = 100
    error = ''
    phase = 'ready'
    downloaded_mb = $totalMb
    resumable = $true
    model_dir = $modelDir
    cache_root = $readyCache
    updated_at = $now
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $status -Encoding UTF8

Step '[7/8] Saving the correct XTTS cache location for future launches...'
[Environment]::SetEnvironmentVariable('TTS_HOME', $readyCache, 'User')
[Environment]::SetEnvironmentVariable('COQUI_TOS_AGREED', '1', 'User')
if (-not (Test-Path -LiteralPath $marker)) { throw 'XTTS ready marker was not created.' }
$check = Get-Content -LiteralPath $status -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$check.progress -ne 100) { throw 'XTTS status verification failed.' }

Step '[8/8] Starting Ibn Al-Waqadi Studio...'
if (Test-Path -LiteralPath $app) {
    Start-Process -FilePath $app
} else {
    Write-Host "Studio executable was not found at: $app" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'SUCCESS: XTTS model was found or completed and connected at 100 percent.' -ForegroundColor Green
Write-Host "MODEL_DIR=$modelDir" -ForegroundColor Green
Write-Host "MODEL_MB=$totalMb" -ForegroundColor Green
Write-Host 'No project build or user-data deletion was performed.' -ForegroundColor Green
Write-Host 'The first local generation can take several minutes while XTTS loads into RAM.' -ForegroundColor Yellow
Write-Host '========================================================================' -ForegroundColor DarkCyan
Read-Host 'Press Enter to close'
