# Ibn Al-Waqadi Studio 6.2.0 - Voice Clone Pro safe installer.
# ASCII-only for Windows PowerShell 5.1.
# It builds from an exact snapshot in TEMP and installs the verified application.
# It never writes to or deletes the user's source project. LocalAppData user data,
# keys, sessions, existing generated audio, and voice profiles are preserved.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$SourceCommit = "77fde2bb678ec500b4d1feecd373abaefc6c0389"
$ArchiveUrl = "https://github.com/Agfsgsy/awesome-voice-ai-tools/archive/$SourceCommit.zip"

function Step {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
}

function Ensure-Python311 {
    & py -3.11 -V *> $null
    if ($LASTEXITCODE -eq 0) { return }
    $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "Python 3.11 is missing and Windows Package Manager is unavailable."
    }
    Write-Host "Installing Python 3.11..." -ForegroundColor Yellow
    & winget install --id Python.Python.3.11 --exact --silent --accept-package-agreements --accept-source-agreements
    & py -3.11 -V *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 installation did not complete. Restart Windows and run this command again."
    }
}

function Find-Iscc {
    $Candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $Candidates += (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
    }
    if ($env:ProgramFiles) {
        $Candidates += (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
    }
    if ($env:LOCALAPPDATA) {
        $Candidates += (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    }
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) { return $Candidate }
    }
    $Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    return ""
}

function Validate-Snapshot {
    param([string]$Root)
    $Checks = @(
        @{ Path = "backend\api\voice_clone_routes.py"; Marker = "speaker_wav" },
        @{ Path = "backend\api\voice_clone_routes.py"; Marker = "coqui-tts==0.27.5" },
        @{ Path = "backend\plugins\coqui_plugin.py"; Marker = "speaker_wav=str(reference)" },
        @{ Path = "backend\api\studio_pro_routes.py"; Marker = "generate_from_profile" },
        @{ Path = "frontend\static\voice_clone.html"; Marker = "/api/voice-clone/generate" },
        @{ Path = "frontend\static\studio_shell.html"; Marker = "/static/voice_clone.html" },
        @{ Path = "backend\core\config.py"; Marker = 'APP_VERSION = "6.2.0"' },
        @{ Path = "installer\VoiceAIStudio.iss"; Marker = '#define MyAppVersion "6.2.0"' },
        @{ Path = "scripts\validate_unified_release.py"; Marker = 'EXPECTED_VERSION = "6.2.0"' }
    )
    foreach ($Check in $Checks) {
        $File = Join-Path $Root $Check.Path
        if (-not (Test-Path -LiteralPath $File -PathType Leaf)) {
            throw "Snapshot file is missing: $($Check.Path)"
        }
        if ((Get-Item -LiteralPath $File).Length -lt 50) {
            throw "Snapshot file is incomplete: $($Check.Path)"
        }
        if (-not (Select-String -LiteralPath $File -SimpleMatch -Pattern $Check.Marker -Quiet)) {
            throw "Snapshot marker is missing in $($Check.Path): $($Check.Marker)"
        }
    }
}

$TempRoot = Join-Path $env:TEMP ("IbnWaqadi-VoiceClone62-" + [guid]::NewGuid().ToString("N"))
$Archive = Join-Path $TempRoot "source.zip"
$Extract = Join-Path $TempRoot "source"
$LogRoot = Join-Path $env:LOCALAPPDATA "VoiceAIStudioArabic\logs"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = Join-Path $LogRoot ("voice-clone-pro-6.2-install-" + $Stamp + ".log")
$TranscriptStarted = $false

try {
    New-Item -ItemType Directory -Force -Path $TempRoot, $Extract, $LogRoot | Out-Null
    try {
        Start-Transcript -LiteralPath $LogFile -Force | Out-Null
        $TranscriptStarted = $true
    }
    catch {}

    Step "Ibn Al-Waqadi Studio 6.2.0 - Voice Clone Pro safe installation"
    Write-Host "No source project files will be changed or deleted." -ForegroundColor Yellow
    Write-Host "Keys, sessions, old tools, generated audio, and LocalAppData will be preserved." -ForegroundColor Yellow

    Ensure-Python311

    $SystemDriveName = (${env:SystemDrive}).TrimEnd(":")
    $Drive = Get-PSDrive -Name $SystemDriveName -ErrorAction Stop
    if ($Drive.Free -lt 5368709120) {
        throw "At least 5 GB of free disk space is required for the temporary Windows build."
    }

    Step "1/6 - Download the exact Voice Clone Pro 6.2 source snapshot"
    try {
        Import-Module BitsTransfer -ErrorAction SilentlyContinue
        Start-BitsTransfer -Source $ArchiveUrl -Destination $Archive -ErrorAction Stop
    }
    catch {
        Invoke-WebRequest -UseBasicParsing -Uri $ArchiveUrl -OutFile $Archive -TimeoutSec 900
    }
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf) -or (Get-Item -LiteralPath $Archive).Length -lt 100000) {
        throw "The source snapshot download is missing or incomplete."
    }

    Step "2/6 - Extract and validate every Voice Clone Pro file"
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extract -Force
    $SnapshotDirectory = Get-ChildItem -LiteralPath $Extract -Directory | Select-Object -First 1
    if (-not $SnapshotDirectory) { throw "The source snapshot could not be located after extraction." }
    $Snapshot = $SnapshotDirectory.FullName
    Validate-Snapshot -Root $Snapshot
    Write-Host "Snapshot validation passed." -ForegroundColor Green

    Step "3/6 - Install the lightweight desktop build requirements"
    Push-Location $Snapshot
    try {
        & py -3.11 -m pip install --upgrade pip wheel
        if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
        & py -3.11 -m pip install -r requirements.txt -r requirements-desktop.txt
        if ($LASTEXITCODE -ne 0) { throw "Desktop dependency installation failed." }
    }
    finally {
        Pop-Location
    }

    Step "4/6 - Compile and run the complete release validator"
    Push-Location $Snapshot
    try {
        & py -3.11 -m compileall -q main.py desktop_app.py backend scripts
        if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }
        & py -3.11 scripts\validate_unified_release.py
        if ($LASTEXITCODE -ne 0) { throw "Voice Clone Pro release validation failed." }
    }
    finally {
        Pop-Location
    }

    Step "5/6 - Build the Windows application and verified installer"
    Push-Location $Snapshot
    try {
        Remove-Item -LiteralPath (Join-Path $Snapshot "build"), (Join-Path $Snapshot "dist"), (Join-Path $Snapshot "dist-installer") -Recurse -Force -ErrorAction SilentlyContinue
        & py -3.11 -m PyInstaller --noconfirm --clean VoiceAIStudio.spec
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
        $PortableExe = Join-Path $Snapshot "dist\VoiceAIStudioArabic\VoiceAIStudioArabic.exe"
        if (-not (Test-Path -LiteralPath $PortableExe -PathType Leaf)) {
            throw "The desktop executable was not created."
        }

        $Iscc = Find-Iscc
        if ([string]::IsNullOrWhiteSpace($Iscc)) {
            $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
            if (-not $Winget) { throw "Inno Setup is missing and winget is unavailable." }
            & winget install --id JRSoftware.InnoSetup --exact --silent --accept-package-agreements --accept-source-agreements
            $Iscc = Find-Iscc
        }
        if ([string]::IsNullOrWhiteSpace($Iscc)) { throw "Inno Setup compiler was not found." }
        New-Item -ItemType Directory -Force -Path (Join-Path $Snapshot "dist-installer") | Out-Null
        & $Iscc "installer\VoiceAIStudio.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
    }
    finally {
        Pop-Location
    }

    $Setup = Join-Path $Snapshot "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $Setup -PathType Leaf) -or (Get-Item -LiteralPath $Setup).Length -lt 1048576) {
        throw "The verified Windows installer is missing or incomplete."
    }

    Step "6/6 - Install, verify, and launch without touching the source project"
    Stop-Process -Name "VoiceAIStudioArabic" -Force -ErrorAction SilentlyContinue
    $Install = Start-Process -FilePath $Setup -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/TASKS=desktopicon"
    ) -Wait -PassThru
    if ($Install.ExitCode -ne 0) { throw "Installer failed with exit code $($Install.ExitCode)." }

    $InstalledExe = Join-Path $env:LOCALAPPDATA "Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
    if (-not (Test-Path -LiteralPath $InstalledExe -PathType Leaf)) {
        throw "Installation completed, but the application executable was not found."
    }

    Start-Process -FilePath $InstalledExe
    Write-Host ""
    Write-Host "SUCCESS: Voice Clone Pro 6.2.0 is installed and running." -ForegroundColor Green
    Write-Host "Open the main menu and choose Voice Clone Pro." -ForegroundColor Green
    Write-Host "The source project was not changed." -ForegroundColor Green
    Write-Host "Installation log: $LogFile" -ForegroundColor DarkGray
}
catch {
    Write-Host ""
    Write-Host ("INSTALL ERROR: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "No source project files, keys, sessions, generated audio, or voice profiles were deleted." -ForegroundColor Yellow
    Write-Host "Log file: $LogFile" -ForegroundColor DarkGray
    Read-Host "Press Enter to close"
    exit 1
}
finally {
    if ($TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
