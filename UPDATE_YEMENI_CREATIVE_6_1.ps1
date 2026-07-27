# Ibn Al-Waqadi Studio 6.1.0 updater.
# ASCII-only source for Windows PowerShell 5.1 compatibility.
# This updater never deletes LocalAppData, saved keys, sessions, voices, or outputs.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$SourceCommit = "65b565cd947af1edb8204cb22752c9db080d888f"
$RawRoot = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/$SourceCommit"

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
}

function Find-ProjectRoot {
    $Candidates = @(
        (Join-Path $env:USERPROFILE "Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "OneDrive\Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Downloads\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"),
        (Join-Path $env:USERPROFILE "Downloads\awesome-voice-ai-tools-agent-professional-tts-engine")
    )

    foreach ($Candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($Candidate)) {
            continue
        }
        $Builder = Join-Path $Candidate "BUILD_WINDOWS_INSTALLER.bat"
        $Main = Join-Path $Candidate "main.py"
        if ((Test-Path -LiteralPath $Builder -PathType Leaf) -and (Test-Path -LiteralPath $Main -PathType Leaf)) {
            return [string](Resolve-Path -LiteralPath $Candidate).Path
        }
    }

    return ""
}

function Local-Path {
    param(
        [string]$Root,
        [string]$Relative
    )
    return Join-Path $Root ($Relative.Replace("/", "\"))
}

function Test-DownloadedRelease {
    param([string]$Root)

    $Checks = @(
        @{ Path = "backend/api/yemeni_creative_routes.py"; Marker = '@router.post("/produce")' },
        @{ Path = "backend/api/yemeni_creative_routes.py"; Marker = '"320k"' },
        @{ Path = "frontend/static/yemeni_creative.html"; Marker = "/api/yemeni-creative/produce" },
        @{ Path = "frontend/static/studio_shell.html"; Marker = "/static/yemeni_creative.html" },
        @{ Path = "backend/core/config.py"; Marker = 'APP_VERSION = "6.1.0"' },
        @{ Path = "main.py"; Marker = "yemeni_creative_router" },
        @{ Path = "scripts/validate_unified_release.py"; Marker = 'EXPECTED_VERSION = "6.1.0"' },
        @{ Path = "installer/VoiceAIStudio.iss"; Marker = '#define MyAppVersion "6.1.0"' }
    )

    foreach ($Check in $Checks) {
        $File = Local-Path -Root $Root -Relative $Check.Path
        if (-not (Test-Path -LiteralPath $File -PathType Leaf)) {
            throw "Preflight file is missing: $($Check.Path)"
        }
        if ((Get-Item -LiteralPath $File).Length -lt 2) {
            throw "Preflight file is empty: $($Check.Path)"
        }
        $Found = Select-String -LiteralPath $File -SimpleMatch -Pattern $Check.Marker -Quiet
        if (-not $Found) {
            throw "Preflight marker is missing in $($Check.Path): $($Check.Marker)"
        }
    }
}

$Files = @(
    "backend/api/yemeni_creative_routes.py",
    "frontend/static/yemeni_creative.html",
    "backend/api/download_export_runtime.py",
    "backend/api/unified_studio_routes.py",
    "backend/core/config.py",
    "frontend/static/studio_shell.html",
    "main.py",
    "desktop_app.py",
    "scripts/validate_unified_release.py",
    "pyproject.toml",
    "setup.py",
    "config/default.json",
    "installer/VoiceAIStudio.iss",
    "BUILD_WINDOWS_INSTALLER.bat"
)

$Project = Find-ProjectRoot
if ([string]::IsNullOrWhiteSpace($Project)) {
    Write-Host "Project folder was not found." -ForegroundColor Red
    Write-Host "Expected folder: Desktop\VoiceAIStudio-Pro-Latest" -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Project ("Backups\YemeniCreative-6.1-" + $Stamp)
$Temp = Join-Path $env:TEMP ("IbnWaqadi-6.1-" + [guid]::NewGuid().ToString("N"))
$Applied = $false

try {
    Write-Step "Ibn Al-Waqadi Studio 6.1.0 - safe preflight"
    Write-Host "Project: $Project" -ForegroundColor Green
    Write-Host "Saved keys, sessions, voices, and audio outputs will not be removed." -ForegroundColor Yellow

    if (-not (Test-Path -LiteralPath $env:TEMP -PathType Container)) {
        throw "Windows TEMP folder is not available."
    }

    $DriveName = ([System.IO.Path]::GetPathRoot($Project)).TrimEnd("\").TrimEnd(":")
    $Drive = Get-PSDrive -Name $DriveName -ErrorAction Stop
    if ($Drive.Free -lt 3221225472) {
        throw "At least 3 GB of free disk space is required for the Windows build."
    }

    New-Item -ItemType Directory -Force -Path $Temp | Out-Null

    Write-Step "1/6 - Download every update file to a temporary folder"
    foreach ($Relative in $Files) {
        $Url = "$RawRoot/$Relative"
        $TempFile = Local-Path -Root $Temp -Relative $Relative
        $TempDirectory = Split-Path -Parent $TempFile
        New-Item -ItemType Directory -Force -Path $TempDirectory | Out-Null
        Write-Host ("Downloading: " + $Relative) -ForegroundColor DarkCyan
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $TempFile -TimeoutSec 420
        if (-not (Test-Path -LiteralPath $TempFile -PathType Leaf)) {
            throw "Download failed: $Relative"
        }
        if ((Get-Item -LiteralPath $TempFile).Length -eq 0) {
            throw "Downloaded file is empty: $Relative"
        }
    }

    Write-Step "2/6 - Validate downloaded release before changing the project"
    Test-DownloadedRelease -Root $Temp
    Write-Host "Preflight validation passed." -ForegroundColor Green

    Write-Step "3/6 - Back up the current source files"
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    foreach ($Relative in $Files) {
        $CurrentFile = Local-Path -Root $Project -Relative $Relative
        if (Test-Path -LiteralPath $CurrentFile -PathType Leaf) {
            $BackupFile = Local-Path -Root $Backup -Relative $Relative
            $BackupDirectory = Split-Path -Parent $BackupFile
            New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
            Copy-Item -LiteralPath $CurrentFile -Destination $BackupFile -Force
        }
    }

    Write-Step "4/6 - Apply the already validated files"
    Stop-Process -Name "VoiceAIStudioArabic" -Force -ErrorAction SilentlyContinue
    foreach ($Relative in $Files) {
        $TempFile = Local-Path -Root $Temp -Relative $Relative
        $CurrentFile = Local-Path -Root $Project -Relative $Relative
        $CurrentDirectory = Split-Path -Parent $CurrentFile
        New-Item -ItemType Directory -Force -Path $CurrentDirectory | Out-Null
        Copy-Item -LiteralPath $TempFile -Destination $CurrentFile -Force
    }
    $Applied = $true

    Write-Step "5/6 - Build and validate the Windows installer"
    $Builder = Join-Path $Project "BUILD_WINDOWS_INSTALLER.bat"
    $BuildCommand = 'set CI=1&&call "' + $Builder + '"'
    $Build = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", $BuildCommand) -WorkingDirectory $Project -Wait -PassThru
    if ($Build.ExitCode -ne 0) {
        throw "Windows build failed with exit code $($Build.ExitCode)."
    }

    $Setup = Join-Path $Project "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $Setup -PathType Leaf)) {
        throw "The installer file was not created."
    }
    if ((Get-Item -LiteralPath $Setup).Length -lt 1048576) {
        throw "The installer file is unexpectedly small."
    }

    Write-Step "6/6 - Install version 6.1.0"
    $InstallArguments = @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/TASKS=desktopicon"
    )
    $Install = Start-Process -FilePath $Setup -ArgumentList $InstallArguments -Wait -PassThru
    if ($Install.ExitCode -ne 0) {
        throw "Installer failed with exit code $($Install.ExitCode)."
    }

    $Exe = Join-Path $env:LOCALAPPDATA "Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
        throw "Installation completed, but the desktop application executable was not found."
    }

    Start-Process -FilePath $Exe
    Write-Step "Version 6.1.0 installed successfully"
    Write-Host "The Yemeni Creative tool is now available in the studio menu." -ForegroundColor Green
    Write-Host "Source backup: $Backup" -ForegroundColor DarkGray
}
catch {
    Write-Host ""
    Write-Host ("UPDATE ERROR: " + $_.Exception.Message) -ForegroundColor Red

    if ($Applied -and (Test-Path -LiteralPath $Backup -PathType Container)) {
        Write-Host "Restoring the previous source files..." -ForegroundColor Yellow
        foreach ($Relative in $Files) {
            $BackupFile = Local-Path -Root $Backup -Relative $Relative
            if (Test-Path -LiteralPath $BackupFile -PathType Leaf) {
                $CurrentFile = Local-Path -Root $Project -Relative $Relative
                $CurrentDirectory = Split-Path -Parent $CurrentFile
                New-Item -ItemType Directory -Force -Path $CurrentDirectory | Out-Null
                Copy-Item -LiteralPath $BackupFile -Destination $CurrentFile -Force
            }
        }
        Write-Host "Previous source files were restored." -ForegroundColor Yellow
    }

    Write-Host "LocalAppData, keys, sessions, voices, and generated audio were not deleted." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}
finally {
    if (Test-Path -LiteralPath $Temp) {
        Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
