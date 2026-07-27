# Audio download fix only - ASCII-safe for Windows PowerShell 5.1
# This script does not change the application version and does not delete user data.

$ErrorActionPreference = 'Stop'

function Find-ProjectRoot {
    $candidates = @(
        (Join-Path $env:USERPROFILE 'Desktop\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'OneDrive\Desktop\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'Downloads\VoiceAIStudio-Pro-Latest'),
        (Join-Path $env:USERPROFILE 'Desktop\awesome-voice-ai-tools-agent-professional-tts-engine'),
        (Join-Path $env:USERPROFILE 'Downloads\awesome-voice-ai-tools-agent-professional-tts-engine')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'main.py')) {
            return [string](Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ''
}

function Write-Utf8NoBom {
    param([string]$Path, [string]$Text)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

$project = Find-ProjectRoot
if (-not $project) {
    Write-Host 'Project folder was not found.' -ForegroundColor Red
    Write-Host 'Expected VoiceAIStudio-Pro-Latest on Desktop or Downloads.' -ForegroundColor Yellow
    Read-Host 'Press Enter to close'
    exit 1
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $project ('Backups\AudioDownloadFixV2-' + $stamp)
$mainFile = Join-Path $project 'main.py'
$runtimeDir = Join-Path $project 'backend\api'
$runtimeFile = Join-Path $runtimeDir 'download_export_runtime.py'
$tempFile = Join-Path $env:TEMP ('download_export_runtime-' + $stamp + '.py')
$builder = Join-Path $project 'BUILD_WINDOWS_INSTALLER.bat'
$runtimeUrl = 'https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/85dc9ec1d9f1215908c5bc50a15b86a4c04380ce/backend/api/download_export_runtime.py'

try {
    Write-Host '============================================================' -ForegroundColor DarkCyan
    Write-Host ' Audio download fix only - same application version' -ForegroundColor Cyan
    Write-Host '============================================================' -ForegroundColor DarkCyan
    Write-Host ('Project: ' + $project) -ForegroundColor Green

    Stop-Process -Name 'VoiceAIStudioArabic' -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

    Copy-Item -LiteralPath $mainFile -Destination (Join-Path $backup 'main.py') -Force
    if (Test-Path -LiteralPath $runtimeFile) {
        Copy-Item -LiteralPath $runtimeFile -Destination (Join-Path $backup 'download_export_runtime.py') -Force
    }

    Write-Host '[1/4] Downloading the audio download runtime...' -ForegroundColor Cyan
    Invoke-WebRequest -UseBasicParsing -Uri $runtimeUrl -OutFile $tempFile -TimeoutSec 300
    if (-not (Test-Path -LiteralPath $tempFile)) {
        throw 'Runtime download did not complete.'
    }
    Copy-Item -LiteralPath $tempFile -Destination $runtimeFile -Force

    Write-Host '[2/4] Patching main.py without changing version files...' -ForegroundColor Cyan
    $content = [System.IO.File]::ReadAllText($mainFile, [System.Text.Encoding]::UTF8)
    $newline = [Environment]::NewLine
    $importLine = 'from backend.api.download_export_runtime import install_download_export_runtime'
    if (-not $content.Contains($importLine)) {
        $marker = 'from backend.core.config import'
        $index = $content.IndexOf($marker, [System.StringComparison]::Ordinal)
        if ($index -lt 0) {
            throw 'Could not locate the import marker in main.py.'
        }
        $content = $content.Insert($index, $importLine + $newline)
    }

    $callLine = 'install_download_export_runtime(app)'
    if (-not $content.Contains($callLine)) {
        $marker = 'def _validate_api_contracts'
        $index = $content.IndexOf($marker, [System.StringComparison]::Ordinal)
        if ($index -lt 0) {
            $marker = 'static_dir = FRONTEND_DIR'
            $index = $content.IndexOf($marker, [System.StringComparison]::Ordinal)
        }
        if ($index -lt 0) {
            throw 'Could not locate the runtime installation marker in main.py.'
        }
        $insertion = '# Audio download export runtime - download fix only' + $newline + $callLine + $newline + $newline
        $content = $content.Insert($index, $insertion)
    }
    Write-Utf8NoBom -Path $mainFile -Text $content

    Write-Host '[3/4] Validating and rebuilding the current version...' -ForegroundColor Cyan
    & py -3.11 -m py_compile $runtimeFile $mainFile
    if ($LASTEXITCODE -ne 0) {
        throw 'Python syntax validation failed.'
    }
    if (-not (Test-Path -LiteralPath $builder)) {
        throw 'BUILD_WINDOWS_INSTALLER.bat was not found.'
    }
    $buildCommand = 'echo.|call "' + $builder + '"'
    $build = Start-Process -FilePath 'cmd.exe' -ArgumentList @('/d', '/c', $buildCommand) -WorkingDirectory $project -Wait -PassThru
    if ($build.ExitCode -ne 0) {
        throw ('Build failed with exit code ' + $build.ExitCode)
    }

    Write-Host '[4/4] Installing the fixed build...' -ForegroundColor Cyan
    $setup = Join-Path $project 'dist-installer\VoiceAIStudioSetup.exe'
    if (-not (Test-Path -LiteralPath $setup)) {
        throw 'VoiceAIStudioSetup.exe was not created.'
    }
    $install = Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/TASKS=desktopicon') -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw ('Installer failed with exit code ' + $install.ExitCode)
    }

    $exe = Join-Path $env:LOCALAPPDATA 'Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe'
    if (Test-Path -LiteralPath $exe) {
        Start-Process -FilePath $exe
    }

    Write-Host ''
    Write-Host 'Audio download fix installed successfully.' -ForegroundColor Green
    Write-Host 'The application version was not changed by this patch.' -ForegroundColor Green
    Write-Host 'Downloaded audio will also be copied to Desktop\Ibn Al-Waqadi Studio folders.' -ForegroundColor Yellow
    Write-Host ('Backup: ' + $backup) -ForegroundColor DarkGray
}
catch {
    Write-Host ''
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    $savedMain = Join-Path $backup 'main.py'
    if (Test-Path -LiteralPath $savedMain) {
        Copy-Item -LiteralPath $savedMain -Destination $mainFile -Force
        Write-Host 'main.py was restored from backup.' -ForegroundColor Yellow
    }
    $savedRuntime = Join-Path $backup 'download_export_runtime.py'
    if (Test-Path -LiteralPath $savedRuntime) {
        Copy-Item -LiteralPath $savedRuntime -Destination $runtimeFile -Force
    }
    Read-Host 'Press Enter to close'
    exit 1
}
finally {
    Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
}
