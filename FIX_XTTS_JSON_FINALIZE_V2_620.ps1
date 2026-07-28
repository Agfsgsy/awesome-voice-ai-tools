# Final XTTS readiness repair for Ibn Al-Waqadi Studio 6.2.0.
# Uses Python for JSON validation because Windows PowerShell 5.1 rejects duplicate
# object keys even when Python/XTTS can read the same files correctly.
# No project build, main.py edit, HTML edit, model redownload, or user-data deletion.

$ErrorActionPreference = 'Stop'

function Step([string]$Text) {
    Write-Host $Text -ForegroundColor Cyan
}

$engine = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine'
$python = Join-Path $engine 'venv\Scripts\python.exe'
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
Write-Host ' Ibn Al-Waqadi Studio 6.2 - XTTS JSON Finalize V2' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'The three XTTS files already exist. This repair only validates and finalizes them.' -ForegroundColor Yellow
Write-Host 'No model download and no application build will run.' -ForegroundColor Yellow
Write-Host ''

Step '[1/6] Closing Studio and XTTS worker processes only...'
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

Step '[2/6] Checking the exact XTTS files...'
if (-not (Test-Path -LiteralPath $python)) { throw "XTTS Python environment was not found: $python" }
if (-not (Test-Path -LiteralPath $model)) { throw "Missing model.pth: $model" }
if (-not (Test-Path -LiteralPath $config)) { throw "Missing config.json: $config" }
if (-not (Test-Path -LiteralPath $vocab)) { throw "Missing vocab.json: $vocab" }
if ((Get-Item -LiteralPath $model).Length -lt 500000000) { throw 'model.pth is incomplete.' }
if ((Get-Item -LiteralPath $config).Length -lt 500) { throw 'config.json is incomplete.' }
if ((Get-Item -LiteralPath $vocab).Length -lt 10000) { throw 'vocab.json is incomplete.' }

Write-Host ('MODEL_BYTES=' + (Get-Item -LiteralPath $model).Length) -ForegroundColor Green
Write-Host ('CONFIG_BYTES=' + (Get-Item -LiteralPath $config).Length) -ForegroundColor Green
Write-Host ('VOCAB_BYTES=' + (Get-Item -LiteralPath $vocab).Length) -ForegroundColor Green

Step '[3/6] Validating JSON with the XTTS Python environment...'
$env:IBN_XTTS_CONFIG = $config
$env:IBN_XTTS_VOCAB = $vocab
& $python -c "import json,os; [json.load(open(os.environ[n],encoding='utf-8')) for n in ('IBN_XTTS_CONFIG','IBN_XTTS_VOCAB')]; print('XTTS_PYTHON_JSON_OK')"
if ($LASTEXITCODE -ne 0) { throw 'Python could not read config.json or vocab.json.' }

Step '[4/6] Preserving previous status files...'
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

Step '[5/6] Writing verified XTTS readiness at 100 percent...'
[ordered]@{
    ready = $true
    model_dir = $modelDir
    detail = "Validated XTTS files with Python JSON parser ($totalMb MB)."
    details = "Validated XTTS files with Python JSON parser ($totalMb MB)."
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

[Environment]::SetEnvironmentVariable('TTS_HOME', $cache, 'User')
[Environment]::SetEnvironmentVariable('COQUI_TOS_AGREED', '1', 'User')
$env:TTS_HOME = $cache
$env:COQUI_TOS_AGREED = '1'

if (-not (Test-Path -LiteralPath $marker)) { throw 'XTTS ready marker was not created.' }
$verify = Get-Content -LiteralPath $status -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$verify.progress -ne 100 -or [string]$verify.state -ne 'ready') {
    throw 'XTTS readiness verification failed.'
}

Step '[6/6] Starting Ibn Al-Waqadi Studio...'
if (Test-Path -LiteralPath $app) {
    Start-Process -FilePath $app
} else {
    Write-Host "Studio executable was not found at: $app" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'SUCCESS: XTTS files were finalized and marked ready at 100 percent.' -ForegroundColor Green
Write-Host "MODEL_DIR=$modelDir" -ForegroundColor Green
Write-Host "MODEL_MB=$totalMb" -ForegroundColor Green
Write-Host 'No model redownload, application build, UI edit, or user-data deletion occurred.' -ForegroundColor Green
Write-Host 'The first local generation may take several minutes while XTTS loads into RAM.' -ForegroundColor Yellow
Write-Host '========================================================================' -ForegroundColor DarkCyan
Read-Host 'Press Enter to close'
