$ErrorActionPreference = 'Stop'

$SourceCommit = '3f5367790827faf41d999e0255989b2be4b69d11'
$RawRoot = 'https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/' + $SourceCommit

function Show-Section([string]$Text) {
    Write-Host ''
    Write-Host ('=' * 76) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('=' * 76) -ForegroundColor DarkCyan
}

function Find-ProjectRoot {
    $Candidates = @(
        (Join-Path $env:USERPROFILE 'Desktop\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'OneDrive\Desktop\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'Downloads\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'Desktop\awesome-voice-ai-tools-agent-professional-tts-engine'),
        (Join-Path $env:USERPROFILE 'OneDrive\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine'),
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
    'main.py',
    'desktop_app.py',
    'BUILD_WINDOWS_INSTALLER.bat',
    'VoiceAIStudio.spec',
    'requirements.txt',
    'requirements-desktop.txt',
    'pyproject.toml',
    'setup.py',
    'config/default.json',
    'installer/VoiceAIStudio.iss',
    'scripts/validate_unified_release.py',
    'scripts/validate_yemeni_hotfix.py',
    'backend/core/config.py',
    'backend/api/unified_studio_routes.py',
    'backend/api/download_export_runtime.py',
    'backend/api/yemeni_creative_routes.py',
    'backend/api/yemeni_creative_hotfix.py',
    'backend/api/voice_clone_routes.py',
    'backend/api/studio_pro_routes.py',
    'backend/plugins/coqui_plugin.py',
    'frontend/static/studio_shell.html',
    'frontend/static/voice_clone.html',
    'frontend/static/yemeni_creative.html',
    'frontend/static/yemeni_creative_pro.html'
)

$Project = Find-ProjectRoot
if (-not $Project) {
    Write-Host 'ERROR: Project folder was not found.' -ForegroundColor Red
    Write-Host 'Place VoiceAIStudio-Pro-Latest on Desktop, then run this command again.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close'
    exit 1
}

$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = Join-Path $Project ('Backups\Before-Shila-Repair-' + $Stamp)
$Temp = Join-Path $env:TEMP ('IbnWaqadi-Shila-Repair-' + [guid]::NewGuid().ToString('N'))
$DataFolder = Join-Path $env:LOCALAPPDATA 'VoiceAIStudioArabic'
$DataExistedBefore = Test-Path -LiteralPath $DataFolder
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
New-Item -ItemType Directory -Force -Path $Temp | Out-Null

try {
    Show-Section 'Ibn Al-Waqadi Studio 6.2.0 - UI and Shila repair'
    Write-Host ('Project: ' + $Project) -ForegroundColor Green
    Write-Host 'Keys, sessions, voices, models, and generated outputs will not be deleted.' -ForegroundColor Yellow

    Stop-Process -Name 'VoiceAIStudioArabic' -Force -ErrorAction SilentlyContinue

    Write-Host '[1/6] Backing up current source files...' -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Local = Local-Path $Project $Relative
        if (Test-Path -LiteralPath $Local) {
            $BackupFile = Local-Path $Backup $Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $BackupFile) | Out-Null
            Copy-Item -LiteralPath $Local -Destination $BackupFile -Force
        }
    }

    Write-Host '[2/6] Downloading the complete 6.2.0 UI and Shila repair files...' -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Url = $RawRoot + '/' + $Relative
        $TempFile = Local-Path $Temp $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TempFile) | Out-Null
        Write-Host ('  + ' + $Relative) -ForegroundColor DarkCyan
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $TempFile -TimeoutSec 600
        if (-not (Test-Path -LiteralPath $TempFile)) {
            throw ('Download failed: ' + $Relative)
        }
        if ((Get-Item -LiteralPath $TempFile).Length -eq 0) {
            throw ('Downloaded file is empty: ' + $Relative)
        }
    }

    Write-Host '[3/6] Installing downloaded source files...' -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $TempFile = Local-Path $Temp $Relative
        $Local = Local-Path $Project $Relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Local) | Out-Null
        Copy-Item -LiteralPath $TempFile -Destination $Local -Force
    }

    Write-Host '[4/6] Building and validating the full Windows application...' -ForegroundColor Cyan
    $Builder = Join-Path $Project 'BUILD_WINDOWS_INSTALLER.bat'
    $PreviousCI = $env:CI
    $env:CI = '1'
    try {
        $BuildArgs = @('/d', '/c', ('call "' + $Builder + '"'))
        $Build = Start-Process -FilePath 'cmd.exe' -ArgumentList $BuildArgs -WorkingDirectory $Project -Wait -PassThru
    }
    finally {
        if ($null -eq $PreviousCI) {
            Remove-Item Env:CI -ErrorAction SilentlyContinue
        }
        else {
            $env:CI = $PreviousCI
        }
    }

    if ($Build.ExitCode -ne 0) {
        throw ('Build failed. Exit code: ' + $Build.ExitCode)
    }

    Write-Host '[5/6] Testing Shila and Zamil buttons before installation...' -ForegroundColor Cyan
    Push-Location $Project
    try {
        & py -3.11 'scripts\validate_yemeni_hotfix.py'
        if ($LASTEXITCODE -ne 0) {
            throw 'Shila validation failed.'
        }
    }
    finally {
        Pop-Location
    }

    $Setup = Join-Path $Project 'dist-installer\VoiceAIStudioSetup.exe'
    if (-not (Test-Path -LiteralPath $Setup)) {
        throw 'Windows installer was not created.'
    }

    Write-Host '[6/6] Installing the repair without deleting application data...' -ForegroundColor Cyan
    $InstallArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/TASKS=desktopicon')
    $Install = Start-Process -FilePath $Setup -ArgumentList $InstallArgs -Wait -PassThru
    if ($Install.ExitCode -ne 0) {
        throw ('Installer failed. Exit code: ' + $Install.ExitCode)
    }

    if ($DataExistedBefore -and -not (Test-Path -LiteralPath $DataFolder)) {
        throw 'Safety check failed: application data folder is missing.'
    }

    $Exe = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw 'Installed application executable was not found.'
    }

    Start-Process -FilePath $Exe

    Show-Section 'Repair completed successfully'
    Write-Host 'The full 6.2.0 interface and Voice Clone Pro were restored.' -ForegroundColor Green
    Write-Host 'Shila and Zamil creation buttons were added and tested.' -ForegroundColor Green
    Write-Host 'Local writing works without Gemini. Gemini remains optional.' -ForegroundColor Green
    Write-Host ('Application data preserved at: ' + $DataFolder) -ForegroundColor Green
    Write-Host ('Source backup: ' + $Backup) -ForegroundColor DarkGray
}
catch {
    Write-Host ''
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Restoring source files from the backup...' -ForegroundColor Yellow

    foreach ($Relative in $Files) {
        $BackupFile = Local-Path $Backup $Relative
        $Local = Local-Path $Project $Relative
        if (Test-Path -LiteralPath $BackupFile) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Local) | Out-Null
            Copy-Item -LiteralPath $BackupFile -Destination $Local -Force
        }
    }

    Write-Host 'Keys, sessions, voices, and generated outputs were not deleted.' -ForegroundColor Yellow
    Write-Host ('Backup: ' + $Backup) -ForegroundColor DarkGray
    Read-Host 'Press Enter to close'
    exit 1
}
finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
