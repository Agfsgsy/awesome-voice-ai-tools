# Permanent XTTS checkpoint-directory server fix for Ibn Al-Waqadi Studio 6.2.0.
# This script does not rebuild the application and does not edit main.py or HTML.
# It replaces only the generated local XTTS worker with a compatible server,
# starts it, writes the local runtime record, and opens the Studio.

$ErrorActionPreference = 'Stop'

function Step([string]$Text) {
    Write-Host $Text -ForegroundColor Cyan
}

function Find-CompleteModel([string[]]$Roots) {
    foreach ($root in $Roots) {
        if ([string]::IsNullOrWhiteSpace($root) -or -not (Test-Path -LiteralPath $root)) { continue }
        try {
            foreach ($item in (Get-ChildItem -LiteralPath $root -Filter 'model.pth' -File -Recurse -Force -ErrorAction SilentlyContinue)) {
                $dir = $item.Directory.FullName
                $config = Join-Path $dir 'config.json'
                $vocab = Join-Path $dir 'vocab.json'
                if ($item.Length -ge 500000000 -and
                    (Test-Path -LiteralPath $config) -and
                    (Test-Path -LiteralPath $vocab) -and
                    (Get-Item -LiteralPath $config).Length -ge 500 -and
                    (Get-Item -LiteralPath $vocab).Length -ge 10000) {
                    return $dir
                }
            }
        } catch {}
    }
    return $null
}

$engine = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine'
$python = Join-Path $engine 'venv\Scripts\python.exe'
$server = Join-Path $engine 'xtts_persistent_server.py'
$runtime = Join-Path $engine 'xtts_runtime.json'
$stdout = Join-Path $engine 'xtts_server_stdout.log'
$stderr = Join-Path $engine 'xtts_server_stderr.log'
$app = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
$permanent = Join-Path $engine 'Start_XTTS_Fixed_620.ps1'
$desktop = [Environment]::GetFolderPath('Desktop')
$launcher = Join-Path $desktop 'Start Ibn Al-Waqadi Studio XTTS Fixed.cmd'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'

Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host ' Ibn Al-Waqadi Studio 6.2 - XTTS checkpoint_dir server fix' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'No model download, application build, interface edit, or user-data deletion.' -ForegroundColor Yellow
Write-Host ''

Step '[1/8] Closing only the Studio and old XTTS worker...'
Get-Process -Name 'VoiceAIStudioArabic' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
try {
    Get-CimInstance Win32_Process | Where-Object {
        $exe = [string]$_.ExecutablePath
        $cmd = [string]$_.CommandLine
        ($exe -and $exe.StartsWith($engine, [StringComparison]::OrdinalIgnoreCase)) -or
        ($cmd -and $cmd.IndexOf($engine, [StringComparison]::OrdinalIgnoreCase) -ge 0)
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
} catch {}
Start-Sleep -Seconds 2
if (Test-Path -LiteralPath $runtime) {
    Copy-Item -LiteralPath $runtime -Destination ($runtime + '.backup-' + $stamp) -Force
    Remove-Item -LiteralPath $runtime -Force -ErrorAction SilentlyContinue
}

Step '[2/8] Locating the completed XTTS model...'
if (-not (Test-Path -LiteralPath $python)) { throw "XTTS Python environment was not found: $python" }
$roots = @(
    (Join-Path $env:LOCALAPPDATA 'tts'),
    (Join-Path $engine 'tts_cache'),
    (Join-Path $engine 'tts_ready_cache'),
    (Join-Path $env:USERPROFILE '.cache\tts'),
    (Join-Path $env:USERPROFILE '.cache\huggingface\hub')
)
$modelDir = Find-CompleteModel -Roots $roots
if (-not $modelDir) { throw 'A complete XTTS model.pth/config.json/vocab.json folder was not found.' }
Write-Host "XTTS_MODEL_DIR=$modelDir" -ForegroundColor Green
Write-Host ('XTTS_MODEL_BYTES=' + (Get-Item -LiteralPath (Join-Path $modelDir 'model.pth')).Length) -ForegroundColor Green

Step '[3/8] Preserving and replacing only the generated XTTS server file...'
New-Item -ItemType Directory -Path $engine -Force | Out-Null
if (Test-Path -LiteralPath $server) {
    Copy-Item -LiteralPath $server -Destination ($server + '.backup-' + $stamp) -Force
}

$serverSource = @'
from __future__ import annotations
import json
import os
import re
import sys
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
    raw = [p.strip() for p in re.split(r"(?<=[.!?؟؛\n])\s+", text) if p.strip()]
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

    # Quadro T2000 4 GB is not sufficient for reliable XTTS loading; use CPU.
    device = "cpu"
    try:
        torch.set_num_threads(max(2, min(8, os.cpu_count() or 4)))
    except Exception:
        pass

    config = XttsConfig()
    config.load_json(str(config_path))
    model = Xtts.init_from_config(config)
    # Official XTTS pretrained model folders must be passed as checkpoint_dir.
    model.load_checkpoint(config, checkpoint_dir=str(model_dir), eval=True, use_deepspeed=False)
    model.to(device)

    class Handler(BaseHTTPRequestHandler):
        server_version = "IbnWaqadiXTTSFixed/2.0"

        def log_message(self, _format, *_args):
            return

        def authorized(self):
            return self.headers.get("X-Ibn-Waqadi-Token", "") == token

        def do_GET(self):
            if not self.authorized():
                return send(self, 403, {"success": False, "error": "forbidden"})
            if self.path != "/health":
                return send(self, 404, {"success": False, "error": "not found"})
            return send(self, 200, {"success": True, "ready": True, "device": device})

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

                gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(audio_path=samples)
                pieces = []
                for index, segment in enumerate(split_text(text)):
                    result = model.inference(
                        segment,
                        language,
                        gpt_cond_latent,
                        speaker_embedding,
                        temperature=0.70,
                    )
                    wave = torch.tensor(result["wav"], dtype=torch.float32).cpu().flatten()
                    pieces.append(wave)
                    if index + 1 < len(split_text(text)):
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
                    "trace": traceback.format_exc()[-4000:],
                })

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.4)


if __name__ == "__main__":
    main()
'@
$serverSource | Set-Content -LiteralPath $server -Encoding UTF8

Step '[4/8] Checking the corrected server syntax...'
& $python -m py_compile $server
if ($LASTEXITCODE -ne 0) { throw 'The corrected XTTS server has a Python syntax error.' }

Step '[5/8] Starting XTTS with checkpoint_dir on CPU...'
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
$token = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')

Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
$process = Start-Process -FilePath $python -ArgumentList @($server, [string]$port, $token, $modelDir) -WorkingDirectory $engine -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Write-Host "XTTS_PID=$($process.Id)" -ForegroundColor Green
Write-Host 'Loading the model into RAM. This can take several minutes on CPU...' -ForegroundColor Yellow

Step '[6/8] Waiting for the local XTTS health check...'
$headers = @{ 'X-Ibn-Waqadi-Token' = $token }
$ready = $false
$deadline = (Get-Date).AddMinutes(25)
$lastMessage = Get-Date
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) {
        $tail = if (Test-Path -LiteralPath $stderr) { (Get-Content -LiteralPath $stderr -Tail 80) -join "`n" } else { 'No stderr log.' }
        throw "The corrected XTTS server stopped while loading.`n$tail"
    }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -Headers $headers -TimeoutSec 3
        if ($health.ready) {
            $ready = $true
            break
        }
    } catch {}
    if (((Get-Date) - $lastMessage).TotalSeconds -ge 30) {
        Write-Host ('Still loading XTTS... ' + (Get-Date -Format 'HH:mm:ss')) -ForegroundColor DarkYellow
        $lastMessage = Get-Date
    }
    Start-Sleep -Seconds 3
}
if (-not $ready) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    throw 'XTTS did not become ready within 25 minutes.'
}
Write-Host 'XTTS_HEALTH_OK device=cpu' -ForegroundColor Green

Step '[7/8] Registering the healthy server for the Studio...'
$runtimePayload = [ordered]@{
    port = $port
    token = $token
    pid = $process.Id
    created_at = [DateTime]::UtcNow.ToString('o')
    fixed_checkpoint_dir = $true
    model_dir = $modelDir
}
$runtimePayload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runtime -Encoding UTF8

# Keep a permanent copy and create an easy Desktop launcher for future restarts.
try {
    if ($MyInvocation.MyCommand.Path -and ([IO.Path]::GetFullPath($MyInvocation.MyCommand.Path) -ne [IO.Path]::GetFullPath($permanent))) {
        Copy-Item -LiteralPath $MyInvocation.MyCommand.Path -Destination $permanent -Force
    }
    $cmdText = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$permanent`"`r`n"
    Set-Content -LiteralPath $launcher -Value $cmdText -Encoding ASCII
} catch {}

Step '[8/8] Opening Ibn Al-Waqadi Studio...'
if (Test-Path -LiteralPath $app) {
    Start-Process -FilePath $app
} else {
    Write-Host "Studio executable was not found at: $app" -ForegroundColor Yellow
}

Write-Host ''
Write-Host '========================================================================' -ForegroundColor DarkCyan
Write-Host 'SUCCESS: XTTS loaded correctly using checkpoint_dir and is ready.' -ForegroundColor Green
Write-Host "MODEL_DIR=$modelDir" -ForegroundColor Green
Write-Host "PORT=$port" -ForegroundColor Green
Write-Host 'Use the new Desktop launcher after restarting Windows.' -ForegroundColor Yellow
Write-Host 'Desktop file: Start Ibn Al-Waqadi Studio XTTS Fixed.cmd' -ForegroundColor Yellow
Write-Host 'No model redownload, rebuild, UI edit, or user-data deletion occurred.' -ForegroundColor Green
Write-Host '========================================================================' -ForegroundColor DarkCyan
Read-Host 'Press Enter to close'
