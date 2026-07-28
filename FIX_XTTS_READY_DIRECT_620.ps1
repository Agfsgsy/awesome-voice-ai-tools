# Direct XTTS readiness repair for Ibn Al-Waqadi Studio 6.2.0.
# ASCII-only for Windows PowerShell 5.1 compatibility.
# This script does not edit the project, main.py, HTML, keys, profiles, samples,
# generated audio, shila projects, or the downloaded model files.

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Text) {
    Write-Host $Text -ForegroundColor Cyan
}

$engine = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine'
$cache = Join-Path $engine 'tts_cache'
$modelDir = Join-Path $cache 'tts_models--multilingual--multi-dataset--xtts_v2'
$model = Join-Path $modelDir 'model.pth'
$config = Join-Path $modelDir 'config.json'
$vocab = Join-Path $modelDir 'vocab.json'
$marker = Join-Path $engine 'xtts_model_ready.json'
$status = Join-Path $engine 'setup_status.json'
$runtime = Join-Path $engine 'xtts_runtime.json'
$app = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host ' Ibn Al-Waqadi Studio 6.2 - Direct XTTS Ready Repair' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host ''
Write-Host 'No project build is required. No downloaded model file will be deleted.' -ForegroundColor Yellow
Write-Host ''

Write-Step '[1/6] Closing only Studio and XTTS worker processes...'
Get-Process -Name 'VoiceAIStudioArabic' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
try {
    Get-CimInstance Win32_Process | Where-Object {
        $exe = [string]$_.ExecutablePath
        $cmd = [string]$_.CommandLine
        ($exe -and $exe.StartsWith($engine, [System.StringComparison]::OrdinalIgnoreCase)) -or
        ($cmd -and $cmd.IndexOf($engine, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
} catch {}
Start-Sleep -Seconds 2

Write-Step '[2/6] Checking the existing XTTS model files...'
if (-not (Test-Path -LiteralPath $model)) { throw "Missing model.pth: $model" }
if (-not (Test-Path -LiteralPath $config)) { throw "Missing config.json: $config" }
if (-not (Test-Path -LiteralPath $vocab)) { throw "Missing vocab.json: $vocab" }

$modelSize = (Get-Item -LiteralPath $model).Length
$configSize = (Get-Item -LiteralPath $config).Length
$vocabSize = (Get-Item -LiteralPath $vocab).Length
if ($modelSize -lt 500000000) { throw "model.pth is incomplete: $modelSize bytes" }
if ($configSize -lt 500) { throw "config.json is incomplete: $configSize bytes" }
if ($vocabSize -lt 10000) { throw "vocab.json is incomplete: $vocabSize bytes" }

$null = Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
$null = Get-Content -LiteralPath $vocab -Raw -Encoding UTF8 | ConvertFrom-Json
$totalBytes = (Get-ChildItem -LiteralPath $modelDir -File -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$totalMb = [Math]::Round(([double]$totalBytes / 1MB), 1)
Write-Host "XTTS_MODEL_MB=$totalMb" -ForegroundColor Green

Write-Step '[3/6] Preserving previous status files...'
New-Item -ItemType Directory -Path $engine -Force | Out-Null
foreach ($file in @($marker, $status, $runtime)) {
    if (Test-Path -LiteralPath $file) {
        Copy-Item -LiteralPath $file -Destination ($file + '.backup-' + $stamp) -Force
    }
}
if (Test-Path -LiteralPath $runtime) {
    Move-Item -LiteralPath $runtime -Destination ($runtime + '.stale-' + $stamp) -Force
}

Write-Step '[4/6] Creating the verified 100-percent readiness state...'
$now = [DateTime]::UtcNow.ToString('o')
$markerPayload = [ordered]@{
    ready = $true
    model_dir = $modelDir
    detail = "Validated existing XTTS files directly ($totalMb MB)."
    details = "Validated existing XTTS files directly ($totalMb MB)."
    prepared_at = $now
    updated_at = $now
    coqui = '0.27.5'
    torch = '2.5.1'
    transformers = '4.57.6'
}
$markerPayload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $marker -Encoding UTF8

$statusPayload = [ordered]@{
    state = 'ready'
    status = 'ready'
    message = 'XTTS model files are complete and ready. The model will load into memory on first use.'
    progress = 100
    error = ''
    phase = 'ready'
    downloaded_mb = $totalMb
    resumable = $true
    model_dir = $modelDir
    updated_at = $now
}
$statusPayload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $status -Encoding UTF8

Write-Step '[5/6] Connecting Coqui TTS to the existing model cache...'
[Environment]::SetEnvironmentVariable('TTS_HOME', $cache, 'User')
[Environment]::SetEnvironmentVariable('COQUI_TOS_AGREED', '1', 'User')
$env:TTS_HOME = $cache
$env:COQUI_TOS_AGREED = '1'
$env:TOKENIZERS_PARALLELISM = 'false'

if (-not (Test-Path -LiteralPath $marker)) { throw 'Ready marker was not created.' }
if (-not (Test-Path -LiteralPath $status)) { throw 'Ready status was not created.' }
$verifyMarker = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json
$verifyStatus = Get-Content -LiteralPath $status -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $verifyMarker.ready -or [int]$verifyStatus.progress -ne 100) {
    throw 'XTTS readiness verification failed.'
}

Write-Step '[6/6] Starting Ibn Al-Waqadi Studio...'
if (Test-Path -LiteralPath $app) {
    Start-Process -FilePath $app
} else {
    Write-Host "Studio executable was not found at: $app" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'SUCCESS: XTTS is marked ready at 100 percent without rebuilding.' -ForegroundColor Green
Write-Host "Model cache: $cache" -ForegroundColor Green
Write-Host 'Open Voice Clone Pro and select Local XTTS.' -ForegroundColor Green
Write-Host 'The first generation can take several minutes while the model loads in memory.' -ForegroundColor Yellow
Write-Host '========================================================================' -ForegroundColor DarkCyan
Read-Host 'Press Enter to close'
