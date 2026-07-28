# Ibn Al-Waqadi Studio 6.2.0 - complete persistent XTTS repair.
# Windows PowerShell 5.1 compatible, ASCII source.
# This repair does not rebuild the application and does not edit main.py or HTML.
# It installs an independent local XTTS service, keeps it alive, writes UTF-8 JSON
# without BOM, registers automatic startup, and opens the Studio only after health OK.

$ErrorActionPreference = 'Stop'

$TaskName = 'IbnWaqadiXTTSAlwaysOn620'
$Engine = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine'
$Python = Join-Path $Engine 'venv\Scripts\python.exe'
$ServiceDir = Join-Path $Engine 'fixed_service'
$ServerFile = Join-Path $ServiceDir 'xtts_fixed_server.py'
$WatchdogFile = Join-Path $ServiceDir 'xtts_watchdog.ps1'
$LauncherFile = Join-Path $ServiceDir 'launch_studio.ps1'
$ConfigFile = Join-Path $ServiceDir 'service_config.json'
$RuntimeFile = Join-Path $Engine 'xtts_runtime.json'
$MarkerFile = Join-Path $Engine 'xtts_model_ready.json'
$StatusFile = Join-Path $Engine 'setup_status.json'
$StdoutFile = Join-Path $ServiceDir 'xtts_fixed_stdout.log'
$StderrFile = Join-Path $ServiceDir 'xtts_fixed_stderr.log'
$WatchdogLog = Join-Path $ServiceDir 'xtts_watchdog.log'
$App = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
$Desktop = [Environment]::GetFolderPath('Desktop')
$DesktopLauncher = Join-Path $Desktop 'Start Ibn Al-Waqadi Studio - XTTS Always On.cmd'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Step([string]$Text) {
    Write-Host $Text -ForegroundColor Cyan
}

function Write-NoBomText([string]$Path, [string]$Text) {
    $Parent = Split-Path -Parent $Path
    if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Write-NoBomJson([string]$Path, $Value) {
    Write-NoBomText $Path ($Value | ConvertTo-Json -Depth 10)
}

function Find-CompleteModel([string[]]$Roots) {
    $Seen = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($Root in $Roots) {
        if ([string]::IsNullOrWhiteSpace($Root) -or -not (Test-Path -LiteralPath $Root)) { continue }
        Write-Host "Searching model files: $Root" -ForegroundColor DarkGray
        try {
            foreach ($Item in (Get-ChildItem -LiteralPath $Root -Filter 'model.pth' -File -Recurse -Force -ErrorAction SilentlyContinue)) {
                $Dir = $Item.Directory.FullName
                if (-not $Seen.Add($Dir)) { continue }
                $Cfg = Join-Path $Dir 'config.json'
                $Voc = Join-Path $Dir 'vocab.json'
                if ($Item.Length -ge 500000000 -and
                    (Test-Path -LiteralPath $Cfg) -and
                    (Test-Path -LiteralPath $Voc) -and
                    (Get-Item -LiteralPath $Cfg).Length -ge 500 -and
                    (Get-Item -LiteralPath $Voc).Length -ge 10000) {
                    return $Dir
                }
            }
        } catch {}
    }
    return $null
}

function Test-LocalHealth([int]$Port, [string]$Token, [int]$TimeoutSec = 3) {
    try {
        $Headers = @{ 'X-Ibn-Waqadi-Token' = $Token }
        $Result = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Headers $Headers -TimeoutSec $TimeoutSec
        return [bool]$Result.ready
    } catch {
        return $false
    }
}

Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host ' Ibn Al-Waqadi Studio 6.2 - Complete XTTS Always-On Repair' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'One repair: correct checkpoint loading, persistent service, auto restart,' -ForegroundColor Yellow
Write-Host 'UTF-8 JSON without BOM, automatic Windows startup, and verified health.' -ForegroundColor Yellow
Write-Host 'No model download, application rebuild, UI edit, or user-data deletion.' -ForegroundColor Yellow
Write-Host ''

Step '[1/10] Closing the Studio and stopping old broken XTTS workers...'
Get-Process -Name 'VoiceAIStudioArabic' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
try {
    Get-CimInstance Win32_Process | Where-Object {
        $Exe = [string]$_.ExecutablePath
        $Cmd = [string]$_.CommandLine
        ($Exe -and $Exe.StartsWith($Engine, [StringComparison]::OrdinalIgnoreCase)) -or
        ($Cmd -and ($Cmd.IndexOf($Engine, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or $Cmd.IndexOf('IbnWaqadiXTTSAlwaysOn620', [StringComparison]::OrdinalIgnoreCase) -ge 0))
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Seconds 3

Step '[2/10] Locating and validating the completed XTTS model...'
if (-not (Test-Path -LiteralPath $Python)) {
    throw "XTTS Python environment was not found: $Python"
}
$Roots = @(
    (Join-Path $env:LOCALAPPDATA 'tts'),
    (Join-Path $Engine 'tts_cache'),
    (Join-Path $Engine 'tts_ready_cache'),
    (Join-Path $env:USERPROFILE '.cache\tts'),
    (Join-Path $env:USERPROFILE '.cache\huggingface\hub'),
    (Join-Path $env:LOCALAPPDATA 'huggingface\hub')
)
$ModelDir = Find-CompleteModel -Roots $Roots
if (-not $ModelDir) {
    throw 'A complete XTTS model.pth/config.json/vocab.json folder was not found.'
}
$env:IBN_XTTS_MODEL = $ModelDir
& $Python -c "import json,os;from pathlib import Path;p=Path(os.environ['IBN_XTTS_MODEL']);json.load(open(p/'config.json',encoding='utf-8'));json.load(open(p/'vocab.json',encoding='utf-8'));assert (p/'model.pth').stat().st_size>500_000_000;print('XTTS_MODEL_VALID',p)"
if ($LASTEXITCODE -ne 0) { throw 'The completed XTTS files failed Python validation.' }
$ModelBytes = (Get-ChildItem -LiteralPath $ModelDir -File -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$ModelMb = [Math]::Round(([double]$ModelBytes / 1MB), 1)
Write-Host "XTTS_MODEL_DIR=$ModelDir" -ForegroundColor Green
Write-Host "XTTS_MODEL_MB=$ModelMb" -ForegroundColor Green

Step '[3/10] Preserving previous runtime and status files...'
New-Item -ItemType Directory -Path $ServiceDir -Force | Out-Null
foreach ($File in @($RuntimeFile, $MarkerFile, $StatusFile)) {
    if (Test-Path -LiteralPath $File) {
        Copy-Item -LiteralPath $File -Destination ($File + '.backup-' + $Stamp) -Force
    }
}
if (Test-Path -LiteralPath $RuntimeFile) {
    Remove-Item -LiteralPath $RuntimeFile -Force -ErrorAction SilentlyContinue
}

Step '[4/10] Installing the corrected XTTS server...'
$ServerSource = @'
from __future__ import annotations
import json
import os
import re
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def send(handler, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def split_text(text, limit=260):
    raw = [p.strip() for p in re.split(r"(?<=[.!?\u061f\u061b\n])\s+", text) if p.strip()]
    result = []
    for part in raw or [text.strip()]:
        while len(part) > limit:
            cut = part.rfind(" ", 0, limit)
            if cut < 80:
                cut = limit
            result.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            result.append(part)
    return result


def main():
    if len(sys.argv) != 4:
        raise SystemExit("port, token and model_dir are required")
    port = int(sys.argv[1])
    token = sys.argv[2]
    model_dir = Path(sys.argv[3]).resolve()
    config_path = model_dir / "config.json"
    model_path = model_dir / "model.pth"
    vocab_path = model_dir / "vocab.json"
    for required in (config_path, model_path, vocab_path):
        if not required.exists():
            raise FileNotFoundError(str(required))

    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("OMP_NUM_THREADS", str(max(2, min(8, os.cpu_count() or 4))))
    os.environ.setdefault("MKL_NUM_THREADS", str(max(2, min(8, os.cpu_count() or 4))))

    import torch
    import torchaudio
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    device = "cpu"
    try:
        torch.set_num_threads(max(2, min(8, os.cpu_count() or 4)))
    except Exception:
        pass

    config = XttsConfig()
    config.load_json(str(config_path))
    model = Xtts.init_from_config(config)
    try:
        model.load_checkpoint(config, checkpoint_dir=str(model_dir), eval=True, use_deepspeed=False)
    except TypeError:
        model.load_checkpoint(config, checkpoint_dir=str(model_dir), eval=True)
    model.to(device)
    inference_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "IbnWaqadiXTTSAlwaysOn/3.0"

        def log_message(self, _format, *_args):
            return

        def authorized(self):
            return self.headers.get("X-Ibn-Waqadi-Token", "") == token

        def do_GET(self):
            if not self.authorized():
                return send(self, 403, {"success": False, "error": "forbidden"})
            if self.path != "/health":
                return send(self, 404, {"success": False, "error": "not found"})
            return send(self, 200, {"success": True, "ready": True, "device": device, "server": "fixed-3.0"})

        def do_POST(self):
            if not self.authorized():
                return send(self, 403, {"success": False, "error": "forbidden"})
            if self.path != "/generate":
                return send(self, 404, {"success": False, "error": "not found"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    raise ValueError("invalid request size")
                job = json.loads(self.rfile.read(length).decode("utf-8"))
                text = str(job.get("text") or "").strip()
                samples = [str(x) for x in (job.get("samples") or []) if str(x).strip()]
                output = Path(str(job.get("output") or ""))
                language = str(job.get("language") or "ar").split("-")[0]
                if not text or not samples or not output.name:
                    raise ValueError("text, samples and output are required")
                for sample in samples:
                    if not Path(sample).exists():
                        raise FileNotFoundError(sample)

                segments = split_text(text)
                with inference_lock:
                    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(audio_path=samples)
                    pieces = []
                    for index, segment in enumerate(segments):
                        result = model.inference(
                            segment,
                            language,
                            gpt_cond_latent,
                            speaker_embedding,
                            temperature=0.70,
                            length_penalty=1.0,
                            repetition_penalty=5.0,
                            top_k=50,
                            top_p=0.85,
                        )
                        wave = torch.tensor(result["wav"], dtype=torch.float32).cpu().flatten()
                        pieces.append(wave)
                        if index + 1 < len(segments):
                            pieces.append(torch.zeros(int(24000 * 0.22), dtype=torch.float32))
                    combined = torch.cat(pieces) if pieces else torch.zeros(1, dtype=torch.float32)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    torchaudio.save(str(output), combined.unsqueeze(0), 24000)
                if not output.exists() or output.stat().st_size < 1024:
                    raise RuntimeError("XTTS did not create a usable output")
                return send(self, 200, {"success": True, "device": device, "output": str(output)})
            except Exception as exc:
                return send(self, 500, {
                    "success": False,
                    "error": str(exc),
                    "trace": traceback.format_exc()[-5000:],
                })

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.4)


if __name__ == "__main__":
    main()
'@
Write-NoBomText $ServerFile $ServerSource
& $Python -m py_compile $ServerFile
if ($LASTEXITCODE -ne 0) { throw 'The corrected XTTS server has a Python syntax error.' }

Step '[5/10] Installing the automatic watchdog and no-BOM runtime writer...'
$ServiceConfig = [ordered]@{
    python = $Python
    server = $ServerFile
    model_dir = $ModelDir
    engine = $Engine
    runtime = $RuntimeFile
    marker = $MarkerFile
    status = $StatusFile
    stdout = $StdoutFile
    stderr = $StderrFile
    watchdog_log = $WatchdogLog
    model_mb = $ModelMb
}
Write-NoBomJson $ConfigFile $ServiceConfig

$WatchdogSource = @'
$ErrorActionPreference = 'Continue'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$MutexCreated = $false
$Mutex = New-Object System.Threading.Mutex($true, 'Local\IbnWaqadiXTTSAlwaysOn620', [ref]$MutexCreated)
if (-not $MutexCreated) { exit 0 }
$ServiceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigFile = Join-Path $ServiceDir 'service_config.json'

function Write-NoBomJson([string]$Path, $Value) {
    try {
        $Parent = Split-Path -Parent $Path
        if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
        [System.IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 10), $Utf8NoBom)
    } catch {}
}

function Log([string]$Text) {
    try {
        $Line = ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $Text)
        Add-Content -LiteralPath $Config.watchdog_log -Value $Line -Encoding UTF8
    } catch {}
}

function Free-Port {
    $Listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $Listener.Start()
    $Port = ([Net.IPEndPoint]$Listener.LocalEndpoint).Port
    $Listener.Stop()
    return [int]$Port
}

function Healthy([int]$Port, [string]$Token) {
    try {
        $Headers = @{ 'X-Ibn-Waqadi-Token' = $Token }
        $Result = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -Headers $Headers -TimeoutSec 3
        return [bool]$Result.ready
    } catch { return $false }
}

function Write-ReadyState([int]$Port, [string]$Token, [int]$Pid) {
    $Now = [DateTime]::UtcNow.ToString('o')
    Write-NoBomJson $Config.runtime ([ordered]@{
        port = $Port
        token = $Token
        pid = $Pid
        created_at = $Now
        fixed_checkpoint_dir = $true
        always_on = $true
        model_dir = $Config.model_dir
    })
    Write-NoBomJson $Config.marker ([ordered]@{
        ready = $true
        prepared_at = $Now
        updated_at = $Now
        model_dir = $Config.model_dir
        details = 'Healthy persistent XTTS server using checkpoint_dir.'
        coqui = '0.27.5'
        torch = '2.5.1'
        transformers = '4.57.6'
    })
    Write-NoBomJson $Config.status ([ordered]@{
        state = 'ready'
        status = 'ready'
        message = 'XTTS is loaded in memory and ready for immediate local production.'
        progress = 100
        error = ''
        phase = 'ready'
        downloaded_mb = $Config.model_mb
        model_dir = $Config.model_dir
        persistent_worker = $true
        updated_at = $Now
    })
}

$Config = Get-Content -LiteralPath $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
$Process = $null
$Port = 0
$Token = ''

try {
    while ($true) {
        try {
            $NeedsStart = $true
            if ($Process -and -not $Process.HasExited -and $Port -gt 0 -and $Token) {
                $NeedsStart = -not (Healthy $Port $Token)
            }
            if ($NeedsStart) {
                if ($Process -and -not $Process.HasExited) {
                    Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
                }
                Remove-Item -LiteralPath $Config.runtime -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $Config.stdout, $Config.stderr -Force -ErrorAction SilentlyContinue
                $Port = Free-Port
                $Token = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
                $Process = Start-Process -FilePath $Config.python -ArgumentList @($Config.server, [string]$Port, $Token, $Config.model_dir) -WorkingDirectory $Config.engine -WindowStyle Hidden -RedirectStandardOutput $Config.stdout -RedirectStandardError $Config.stderr -PassThru
                Log ('Started fixed XTTS PID=' + $Process.Id + ' PORT=' + $Port)
                $Deadline = (Get-Date).AddMinutes(35)
                $Ready = $false
                while ((Get-Date) -lt $Deadline) {
                    if ($Process.HasExited) { break }
                    if (Healthy $Port $Token) { $Ready = $true; break }
                    Start-Sleep -Seconds 3
                }
                if (-not $Ready) {
                    $Tail = ''
                    try { $Tail = (Get-Content -LiteralPath $Config.stderr -Tail 60) -join ' | ' } catch {}
                    Log ('XTTS load failed or timed out. ' + $Tail)
                    Write-NoBomJson $Config.status ([ordered]@{
                        state = 'failed'
                        status = 'failed'
                        message = 'The persistent XTTS server could not load.'
                        progress = 0
                        error = $Tail
                        updated_at = [DateTime]::UtcNow.ToString('o')
                    })
                    if ($Process -and -not $Process.HasExited) { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue }
                    $Process = $null
                    Start-Sleep -Seconds 15
                    continue
                }
                Log 'XTTS health check succeeded.'
            }
            if ($Process -and -not $Process.HasExited -and (Healthy $Port $Token)) {
                Write-ReadyState $Port $Token $Process.Id
            }
        } catch {
            Log ('Watchdog loop error: ' + $_.Exception.Message)
        }
        Start-Sleep -Seconds 5
    }
} finally {
    try { $Mutex.ReleaseMutex() } catch {}
    try { $Mutex.Dispose() } catch {}
}
'@
Write-NoBomText $WatchdogFile $WatchdogSource

Step '[6/10] Installing automatic startup and restart protection...'
try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue } catch {}
$PowerShellExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$Action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogFile`""
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'Persistent local XTTS service for Ibn Al-Waqadi Studio 6.2' -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Step '[7/10] Installing the permanent Desktop launcher...'
$LauncherSource = @"
`$ErrorActionPreference = 'SilentlyContinue'
try { Start-ScheduledTask -TaskName '$TaskName' } catch {
    Start-Process -FilePath '$PowerShellExe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','$WatchdogFile' -WindowStyle Hidden
}
`$Runtime = '$RuntimeFile'
`$Ready = `$false
`$Deadline = (Get-Date).AddMinutes(35)
while ((Get-Date) -lt `$Deadline) {
    try {
        `$Data = Get-Content -LiteralPath `$Runtime -Raw -Encoding UTF8 | ConvertFrom-Json
        `$Headers = @{ 'X-Ibn-Waqadi-Token' = [string]`$Data.token }
        `$Health = Invoke-RestMethod -Uri ('http://127.0.0.1:' + [int]`$Data.port + '/health') -Headers `$Headers -TimeoutSec 3
        if (`$Health.ready) { `$Ready = `$true; break }
    } catch {}
    Start-Sleep -Seconds 3
}
if (`$Ready -and (Test-Path -LiteralPath '$App')) { Start-Process -FilePath '$App' }
elseif (-not `$Ready) { Start-Process notepad.exe '$StderrFile' }
"@
Write-NoBomText $LauncherFile $LauncherSource
$CmdText = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$LauncherFile`"`r`n"
[System.IO.File]::WriteAllText($DesktopLauncher, $CmdText, [System.Text.Encoding]::ASCII)

Step '[8/10] Waiting for the real XTTS health check...'
$Ready = $false
$ReadyPort = 0
$Deadline = (Get-Date).AddMinutes(35)
$LastNotice = Get-Date
while ((Get-Date) -lt $Deadline) {
    try {
        if (Test-Path -LiteralPath $RuntimeFile) {
            $RuntimeData = Get-Content -LiteralPath $RuntimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $ReadyPort = [int]$RuntimeData.port
            $ReadyToken = [string]$RuntimeData.token
            if ($ReadyPort -gt 0 -and $ReadyToken -and (Test-LocalHealth $ReadyPort $ReadyToken 3)) {
                $Ready = $true
                break
            }
        }
    } catch {}
    if (((Get-Date) - $LastNotice).TotalSeconds -ge 30) {
        Write-Host ('Still loading XTTS on CPU... ' + (Get-Date -Format 'HH:mm:ss')) -ForegroundColor DarkYellow
        $LastNotice = Get-Date
    }
    Start-Sleep -Seconds 3
}
if (-not $Ready) {
    $Tail = if (Test-Path -LiteralPath $StderrFile) { (Get-Content -LiteralPath $StderrFile -Tail 100) -join "`n" } else { 'No XTTS stderr log was created.' }
    throw "XTTS did not pass the health check.`n$Tail"
}
Write-Host "XTTS_HEALTH_OK PORT=$ReadyPort DEVICE=cpu" -ForegroundColor Green

Step '[9/10] Confirming the Studio can read no-BOM runtime and 100-percent status...'
$RuntimeCheck = Get-Content -LiteralPath $RuntimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
$StatusCheck = Get-Content -LiteralPath $StatusFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$RuntimeCheck.port -ne $ReadyPort -or [int]$StatusCheck.progress -ne 100 -or [string]$StatusCheck.state -ne 'ready') {
    throw 'Runtime/status verification failed.'
}
Write-Host 'XTTS_RUNTIME_JSON_OK_NO_BOM' -ForegroundColor Green
Write-Host 'XTTS_STATUS_READY_100' -ForegroundColor Green

Step '[10/10] Opening Ibn Al-Waqadi Studio...'
if (Test-Path -LiteralPath $App) {
    Start-Process -FilePath $App
} else {
    Write-Host "Studio executable was not found at: $App" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'SUCCESS: XTTS is healthy, persistent, automatic, and ready at 100 percent.' -ForegroundColor Green
Write-Host "MODEL_DIR=$ModelDir" -ForegroundColor Green
Write-Host "MODEL_MB=$ModelMb" -ForegroundColor Green
Write-Host "TASK=$TaskName" -ForegroundColor Green
Write-Host "DESKTOP_LAUNCHER=$DesktopLauncher" -ForegroundColor Green
Write-Host 'The watchdog restarts XTTS automatically if it stops.' -ForegroundColor Green
Write-Host 'After Windows restarts, the service starts automatically at logon.' -ForegroundColor Green
Write-Host 'No model redownload, application rebuild, UI edit, or user-data deletion occurred.' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Read-Host 'Press Enter to close'
