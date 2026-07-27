# ASCII-only repair script for Windows PowerShell 5.1
# Preserves user data, keys, sessions, voice samples, generated audio and projects.

$ErrorActionPreference = 'Stop'
$SourceCommit = 'c67515777b886beb98f8c9abff01e2c22789d674'
$RawRoot = 'https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/' + $SourceCommit

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
}

function Find-ProjectRoot {
    $Candidates = @(
        (Join-Path $env:USERPROFILE 'Desktop\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'OneDrive\Desktop\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'Downloads\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'Desktop\awesome-voice-ai-tools-agent-professional-tts-engine'),
        (Join-Path $env:USERPROFILE 'Downloads\awesome-voice-ai-tools-agent-professional-tts-engine')
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath (Join-Path $Candidate 'BUILD_WINDOWS_INSTALLER.bat'))) {
            return [string](Resolve-Path -LiteralPath $Candidate).Path
        }
    }
    return ''
}

function Local-Path([string]$Root, [string]$Relative) {
    $WindowsRelative = $Relative.Replace('/', [IO.Path]::DirectorySeparatorChar)
    return Join-Path $Root $WindowsRelative
}

$Files = @(
    'backend/api/voice_clone_routes.py',
    'backend/api/voice_clone_repair_runtime.py',
    'frontend/static/voice_clone.html',
    'backend/api/yemeni_creative_routes.py',
    'backend/api/yemeni_creative_hotfix.py',
    'frontend/static/yemeni_creative.html',
    'frontend/static/yemeni_creative_pro.html',
    'frontend/static/studio_shell.html',
    'frontend/static/studio_shell_preserved.html',
    'frontend/static/ultimate_studio.html',
    'backend/api/download_export_runtime.py',
    'main.py',
    'desktop_app.py',
    'scripts/validate_unified_release.py',
    'BUILD_WINDOWS_INSTALLER.bat'
)

$Project = Find-ProjectRoot
if (-not $Project) {
    Write-Host 'ERROR: Project folder was not found.' -ForegroundColor Red
    Write-Host 'Put VoiceAIStudio-Pro-Latest on Desktop, then run this command again.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close'
    exit 1
}

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = Join-Path $Project ('Backups\PreserveUI-Shila-XTTS-V2-' + $Stamp)
$TempRoot = Join-Path $env:TEMP ('IbnWaqadiRepairV2-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
New-Item -ItemType Directory -Force -Path $TempRoot | Out-Null

try {
    Write-Step 'Ibn Al-Waqadi Studio 6.2.0 - Safe Repair V2'
    Write-Host ('Project: ' + $Project) -ForegroundColor Green
    Write-Host 'No keys, sessions, samples, generated audio or projects will be deleted.' -ForegroundColor Yellow

    Stop-Process -Name 'VoiceAIStudioArabic' -Force -ErrorAction SilentlyContinue

    Write-Host '[1/6] Creating source-file backup...' -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Local = Local-Path $Project $Relative
        if (Test-Path -LiteralPath $Local) {
            $BackupFile = Local-Path $Backup $Relative
            $BackupDirectory = Split-Path -Parent $BackupFile
            New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
            Copy-Item -LiteralPath $Local -Destination $BackupFile -Force
        }
    }

    Write-Host '[2/6] Downloading the repaired files...' -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Url = $RawRoot + '/' + $Relative
        $TempFile = Local-Path $TempRoot $Relative
        $Local = Local-Path $Project $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TempFile) | Out-Null
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Local) | Out-Null
        Write-Host ('  + ' + $Relative) -ForegroundColor DarkCyan
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $TempFile -TimeoutSec 420
        if (-not (Test-Path -LiteralPath $TempFile)) {
            throw ('Download failed: ' + $Relative)
        }
        if ((Get-Item -LiteralPath $TempFile).Length -le 0) {
            throw ('Downloaded file is empty: ' + $Relative)
        }
        Copy-Item -LiteralPath $TempFile -Destination $Local -Force
    }

    Write-Host '[3/6] Checking Python and API contracts...' -ForegroundColor Cyan
    $PythonReady = $false
    try {
        & py -3.11 -V | Out-Null
        if ($LASTEXITCODE -eq 0) { $PythonReady = $true }
    } catch {
        $PythonReady = $false
    }

    if ($PythonReady) {
        Push-Location $Project
        try {
            & py -3.11 -m compileall -q main.py desktop_app.py backend scripts
            if ($LASTEXITCODE -ne 0) { throw 'Python source validation failed.' }
            & py -3.11 scripts\validate_unified_release.py
            if ($LASTEXITCODE -ne 0) { throw 'Release contract validation failed.' }
        } finally {
            Pop-Location
        }
    } else {
        Write-Host 'Python 3.11 is not available yet. The builder will install it automatically.' -ForegroundColor Yellow
    }

    Write-Host '[4/6] Repairing the existing XTTS environment...' -ForegroundColor Cyan
    $XttsPython = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic\voice_clones\local_engine\venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $XttsPython) {
        & $XttsPython -m pip install --disable-pip-version-check --no-input --upgrade --force-reinstall 'transformers==4.57.6'
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'XTTS Transformers compatibility was repaired.' -ForegroundColor Green
        } else {
            Write-Host 'XTTS will finish repairing when Setup Local Engine is pressed inside the app.' -ForegroundColor Yellow
        }
    } else {
        Write-Host 'XTTS environment does not exist yet. The app will create it with compatible versions.' -ForegroundColor Yellow
    }

    Write-Host '[5/6] Building and installing Studio 6.2.0...' -ForegroundColor Cyan
    $Builder = Join-Path $Project 'BUILD_WINDOWS_INSTALLER.bat'
    $BuildCommand = 'echo.|call "' + $Builder + '"'
    $Build = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/c', $BuildCommand) -WorkingDirectory $Project -Wait -PassThru
    if ($Build.ExitCode -ne 0) {
        throw ('Build failed with exit code ' + $Build.ExitCode)
    }

    $Setup = Join-Path $Project 'dist-installer\VoiceAIStudioSetup.exe'
    if (-not (Test-Path -LiteralPath $Setup)) {
        throw 'Installer file was not created.'
    }

    $InstallArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/TASKS=desktopicon')
    $Install = Start-Process -FilePath $Setup -ArgumentList $InstallArgs -Wait -PassThru
    if ($Install.ExitCode -ne 0) {
        throw ('Installation failed with exit code ' + $Install.ExitCode)
    }

    Write-Host '[6/6] Starting the repaired studio...' -ForegroundColor Cyan
    $Exe = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw 'Installed application executable was not found.'
    }
    Start-Process -FilePath $Exe

    Write-Step 'Repair completed successfully'
    Write-Host 'The preserved professional interface is active.' -ForegroundColor Green
    Write-Host 'Shila and zamil buttons are connected to the safe local writer.' -ForegroundColor Green
    Write-Host 'XTTS is pinned to Transformers 4.57.6.' -ForegroundColor Green
    Write-Host ('Backup: ' + $Backup) -ForegroundColor DarkGray
}
catch {
    Write-Host ''
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Restoring the source files from the backup...' -ForegroundColor Yellow
    foreach ($Relative in $Files) {
        $BackupFile = Local-Path $Backup $Relative
        $Local = Local-Path $Project $Relative
        if (Test-Path -LiteralPath $BackupFile) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Local) | Out-Null
            Copy-Item -LiteralPath $BackupFile -Destination $Local -Force
        }
    }
    Write-Host 'User keys, sessions, voice samples, generated audio and projects were not touched.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close'
    exit 1
}
finally {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
