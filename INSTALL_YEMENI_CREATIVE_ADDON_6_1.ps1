# Ibn Al-Waqadi Studio - Yemeni Creative 6.1 add-on installer.
# ASCII-only for Windows PowerShell 5.1.
# Builds in a temporary staging folder first. The original source is updated only
# after the staged application has compiled, passed a route smoke test, built, and installed.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$FeatureCommit = "65b565cd947af1edb8204cb22752c9db080d888f"
$RawRoot = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/$FeatureCommit"
$TargetVersion = "6.1.0"
$NavBase64 = "ICAgICAgPGRpdiBjbGFzcz0iZ3JvdXAiPtin2YTYpdio2K/Yp9i5INin2YTZitmF2YbZijwvZGl2PgogICAgICA8YnV0dG9uIGNsYXNzPSJuYXZJdGVtIHllbWVuaSIgZGF0YS1wYWdlPSIvc3RhdGljL3llbWVuaV9jcmVhdGl2ZS5odG1sIiBkYXRhLXRpdGxlPSLYp9mE2KXZh9iv2KfYodin2Kog2YjYp9mE2KPYtNi52KfYsSDYp9mE2YrZhdmG2YrYqSIgZGF0YS1kZXNjPSLYstin2YXZhCDZiNi2YrZhNipINmI2YLYtdmK2K/YqSDZiNmG2KzYp9itINmI2YXZiNiz2YrZgtmJINij2LXZhNmK2KkiPjxzcGFuIGNsYXNzPSJuYXZJY29uIj7wn4e+8J+Hqjwvc3Bhbj48c3BhbiBjbGFzcz0ibmF2Q29weSI+PHNwYW4gY2xhc3M9Im5hdlRpdGxlIj7Yp9mE2KXZh9iv2KfYodin2Kog2YjYp9mE2KPYtNi52KfYsSDYp9mE2YrZhdmG2YrYqTwvc3Bhbj48c3BhbiBjbGFzcz0ibmF2RGVzYyI+2YbYrNin2K0g4oCiINiq2YHZiNmCIOKAoiDYstin2YXZhCDigKIg2LTZitmE2Kkg4oCiINil2YfYr9in2KE8L3NwYW4+PC9zcGFuPjwvYnV0dG9uPgo="

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host ("=" * 74) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 74) -ForegroundColor DarkCyan
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
        if ([string]::IsNullOrWhiteSpace($Candidate)) { continue }
        if ((Test-Path -LiteralPath (Join-Path $Candidate "main.py") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $Candidate "VoiceAIStudio.spec") -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $Candidate "frontend\static\studio_shell.html") -PathType Leaf)) {
            return [string](Resolve-Path -LiteralPath $Candidate).Path
        }
    }
    return ""
}

function Read-Utf8 {
    param([string]$Path)
    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Write-Utf8 {
    param([string]$Path, [string]$Text)
    $Encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $Encoding)
}

function Replace-Required {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Replacement,
        [string]$Description
    )
    $Regex = New-Object System.Text.RegularExpressions.Regex(
        $Pattern,
        [System.Text.RegularExpressions.RegexOptions]::Multiline
    )
    if (-not $Regex.IsMatch($Text)) {
        throw "Patch marker was not found: $Description"
    }
    return $Regex.Replace($Text, $Replacement, 1)
}

function Find-Iscc {
    $Candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
            return $Candidate
        }
    }
    $Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($Command) { return $Command.Source }
    return ""
}

function Patch-StagingProject {
    param([string]$Root)

    $MainPath = Join-Path $Root "main.py"
    $ShellPath = Join-Path $Root "frontend\static\studio_shell.html"
    $ConfigPath = Join-Path $Root "backend\core\config.py"
    $InstallerPath = Join-Path $Root "installer\VoiceAIStudio.iss"

    $Main = Read-Utf8 $MainPath
    if ($Main -notmatch "yemeni_creative_routes") {
        if ($Main -match "(?m)^from backend\.api\.ultimate_studio_routes import router as ultimate_studio_router\r?$") {
            $Main = Replace-Required $Main "(?m)^(from backend\.api\.ultimate_studio_routes import router as ultimate_studio_router\r?)$" ('$1' + "`nfrom backend.api.yemeni_creative_routes import router as yemeni_creative_router") "main import after ultimate studio"
        }
        elseif ($Main -match "(?m)^from backend\.api\.dashboard_routes import router as dashboard_router\r?$") {
            $Main = Replace-Required $Main "(?m)^(from backend\.api\.dashboard_routes import router as dashboard_router\r?)$" ('$1' + "`nfrom backend.api.yemeni_creative_routes import router as yemeni_creative_router") "main import after dashboard"
        }
        else {
            throw "No safe import position was found in main.py."
        }
    }

    if ($Main -notmatch "app\.include_router\(yemeni_creative_router\)") {
        if ($Main -match "(?m)^app\.include_router\(ultimate_studio_router\)\r?$") {
            $Main = Replace-Required $Main "(?m)^(app\.include_router\(ultimate_studio_router\)\r?)$" ('$1' + "`napp.include_router(yemeni_creative_router)") "router registration after ultimate studio"
        }
        elseif ($Main -match "(?m)^app\.include_router\(dashboard_router\)\r?$") {
            $Main = Replace-Required $Main "(?m)^(app\.include_router\(dashboard_router\)\r?)$" ('$1' + "`napp.include_router(yemeni_creative_router)") "router registration after dashboard"
        }
        else {
            throw "No safe router position was found in main.py."
        }
    }
    Write-Utf8 $MainPath $Main

    $Shell = Read-Utf8 $ShellPath
    if ($Shell -notmatch "/static/yemeni_creative\.html") {
        $ProducerPattern = '(?m)^[ \t]*<button[^>]+data-page="/static/producer\.html"'
        $Match = [regex]::Match($Shell, $ProducerPattern)
        if (-not $Match.Success) {
            throw "The producer navigation marker was not found in studio_shell.html."
        }
        $Nav = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($NavBase64))
        $Shell = $Shell.Insert($Match.Index, $Nav)
    }
    $Shell = [regex]::Replace($Shell, "Professional Studio\s+[0-9]+\.[0-9]+(?:\.[0-9]+)?", "Professional Studio 6.1.0", 1)
    $Shell = [regex]::Replace($Shell, "VERSION='[0-9]+\.[0-9]+(?:\.[0-9]+)?'", "VERSION='6.1.0'", 1)
    Write-Utf8 $ShellPath $Shell

    $Config = Read-Utf8 $ConfigPath
    $Config = Replace-Required $Config '(?m)^APP_VERSION\s*=\s*"[^"]+"\s*$' 'APP_VERSION = "6.1.0"' "APP_VERSION"
    if ($Config -match '(?m)^APP_RELEASE\s*=') {
        $Config = [regex]::Replace($Config, '(?m)^APP_RELEASE\s*=\s*"[^"]*"\s*$', 'APP_RELEASE = "Yemeni Creative Add-on"', 1)
    }
    Write-Utf8 $ConfigPath $Config

    $Installer = Read-Utf8 $InstallerPath
    $Installer = Replace-Required $Installer '(?m)^#define MyAppVersion\s+"[^"]+"\s*$' '#define MyAppVersion "6.1.0"' "installer version"
    Write-Utf8 $InstallerPath $Installer
}

$Project = Find-ProjectRoot
if ([string]::IsNullOrWhiteSpace($Project)) {
    Write-Host "Project folder was not found." -ForegroundColor Red
    Write-Host "Expected: Desktop\VoiceAIStudio-Pro-Latest" -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Stage = Join-Path $env:TEMP ("IbnWaqadi-YemeniAddon-" + [guid]::NewGuid().ToString("N"))
$Backup = Join-Path $Project ("Backups\YemeniAddon-6.1-" + $Stamp)
$StageReady = $false

try {
    Write-Step "Ibn Al-Waqadi Studio 6.1 - feature-only safe installer"
    Write-Host "Original project: $Project" -ForegroundColor Green
    Write-Host "The existing project will not be changed until the staged build is installed successfully." -ForegroundColor Yellow

    $DriveName = ([System.IO.Path]::GetPathRoot($Project)).TrimEnd("\").TrimEnd(":")
    $Drive = Get-PSDrive -Name $DriveName -ErrorAction Stop
    if ($Drive.Free -lt 4294967296) {
        throw "At least 4 GB of free disk space is required for isolated staging and build."
    }

    Write-Step "1/7 - Copy the current project to an isolated staging folder"
    New-Item -ItemType Directory -Force -Path $Stage | Out-Null
    $RoboArgs = @(
        $Project,
        $Stage,
        "/E",
        "/R:2",
        "/W:2",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP",
        "/XD",
        ".git",
        "build",
        "dist",
        "dist-installer",
        "Backups",
        "__pycache__",
        "/XF",
        "*.pyc"
    )
    & robocopy @RoboArgs | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "Staging copy failed with Robocopy code $LASTEXITCODE."
    }

    Write-Step "2/7 - Download only the two new feature files"
    $Downloads = @(
        "backend/api/yemeni_creative_routes.py",
        "frontend/static/yemeni_creative.html"
    )
    foreach ($Relative in $Downloads) {
        $Destination = Join-Path $Stage ($Relative.Replace("/", "\"))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri "$RawRoot/$Relative" -OutFile $Destination -TimeoutSec 420
        if (-not (Test-Path -LiteralPath $Destination -PathType Leaf) -or (Get-Item -LiteralPath $Destination).Length -lt 100) {
            throw "Feature download failed: $Relative"
        }
    }

    Write-Step "3/7 - Add the feature links without replacing the studio"
    Patch-StagingProject -Root $Stage

    Write-Step "4/7 - Install build requirements and compile the staged copy"
    Push-Location $Stage
    try {
        py -3.11 -m pip install -r requirements.txt -r requirements-desktop.txt
        if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

        py -3.11 -m compileall -q main.py desktop_app.py backend
        if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }

        $Smoke = @'
from fastapi.routing import APIRoute
from main import app
routes={(r.path,m) for r in app.routes if isinstance(r,APIRoute) for m in (r.methods or set())}
required={("/api/yemeni-creative/catalog","GET"),("/api/yemeni-creative/write","POST"),("/api/yemeni-creative/produce","POST")}
missing=required-routes
assert not missing, f"Missing Yemeni Creative routes: {sorted(missing)}"
print("YEMENI_ADDON_SMOKE_OK")
'@
        $SmokeFile = Join-Path $Stage "yemeni_addon_smoke.py"
        Write-Utf8 $SmokeFile $Smoke
        py -3.11 $SmokeFile
        if ($LASTEXITCODE -ne 0) { throw "Feature route smoke test failed." }
        Remove-Item -LiteralPath $SmokeFile -Force -ErrorAction SilentlyContinue
    }
    finally {
        Pop-Location
    }

    Write-Step "5/7 - Build the staged Windows application directly"
    Push-Location $Stage
    try {
        Remove-Item -LiteralPath (Join-Path $Stage "build"), (Join-Path $Stage "dist"), (Join-Path $Stage "dist-installer") -Recurse -Force -ErrorAction SilentlyContinue
        py -3.11 -m PyInstaller --noconfirm --clean VoiceAIStudio.spec
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

        $Exe = Join-Path $Stage "dist\VoiceAIStudioArabic\VoiceAIStudioArabic.exe"
        if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
            throw "The staged application executable was not created."
        }

        $Iscc = Find-Iscc
        if ([string]::IsNullOrWhiteSpace($Iscc)) {
            $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
            if (-not $Winget) { throw "Inno Setup is missing and winget is unavailable." }
            & winget install --id JRSoftware.InnoSetup --exact --silent --accept-package-agreements --accept-source-agreements
            $Iscc = Find-Iscc
        }
        if ([string]::IsNullOrWhiteSpace($Iscc)) { throw "Inno Setup compiler was not found." }

        New-Item -ItemType Directory -Force -Path (Join-Path $Stage "dist-installer") | Out-Null
        & $Iscc "installer\VoiceAIStudio.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed." }
    }
    finally {
        Pop-Location
    }

    $Setup = Join-Path $Stage "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $Setup -PathType Leaf) -or (Get-Item -LiteralPath $Setup).Length -lt 1048576) {
        throw "The staged installer is missing or incomplete."
    }
    $StageReady = $true

    Write-Step "6/7 - Install the verified staged application"
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
        throw "Installed executable was not found."
    }

    Write-Step "7/7 - Save only the successful add-on changes to the source project"
    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
    $Changed = @(
        "backend/api/yemeni_creative_routes.py",
        "frontend/static/yemeni_creative.html",
        "main.py",
        "frontend/static/studio_shell.html",
        "backend/core/config.py",
        "installer/VoiceAIStudio.iss"
    )
    foreach ($Relative in $Changed) {
        $Original = Join-Path $Project ($Relative.Replace("/", "\"))
        if (Test-Path -LiteralPath $Original -PathType Leaf) {
            $BackupFile = Join-Path $Backup ($Relative.Replace("/", "\"))
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $BackupFile) | Out-Null
            Copy-Item -LiteralPath $Original -Destination $BackupFile -Force
        }
        $StagedFile = Join-Path $Stage ($Relative.Replace("/", "\"))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Original) | Out-Null
        Copy-Item -LiteralPath $StagedFile -Destination $Original -Force
    }

    Start-Process -FilePath $InstalledExe
    Write-Step "Yemeni Creative add-on 6.1 installed successfully"
    Write-Host "Only the requested feature and its two integration links were added." -ForegroundColor Green
    Write-Host "Keys, sessions, old tools, generated audio, and user data were not deleted." -ForegroundColor Green
    Write-Host "Source backup: $Backup" -ForegroundColor DarkGray
}
catch {
    Write-Host ""
    Write-Host ("ADD-ON ERROR: " + $_.Exception.Message) -ForegroundColor Red
    if (-not $StageReady) {
        Write-Host "The original project was not changed because the isolated build did not pass." -ForegroundColor Yellow
    }
    Write-Host "Keys, sessions, voices, old tools, and generated audio were not deleted." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}
finally {
    if (Test-Path -LiteralPath $Stage) {
        Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
    }
}
