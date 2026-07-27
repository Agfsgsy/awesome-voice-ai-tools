# Ibn Al-Waqadi Studio - Yemeni Creative 6.1 add-on installer.
# ASCII-only for Windows PowerShell 5.1.
# The original source is not changed until a staged copy compiles, passes its
# route smoke test, builds a complete installer, and installs successfully.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$FeatureCommit = "65b565cd947af1edb8204cb22752c9db080d888f"
$RawRoot = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/$FeatureCommit"
$TargetVersion = "6.1.0"
$NavHtml = @'
      <div class="group">&#1575;&#1604;&#1573;&#1576;&#1583;&#1575;&#1593; &#1575;&#1604;&#1610;&#1605;&#1606;&#1610;</div>
      <button class="navItem yemeni" data-page="/static/yemeni_creative.html" data-title="&#1575;&#1604;&#1573;&#1607;&#1583;&#1575;&#1569;&#1575;&#1578; &#1608;&#1575;&#1604;&#1571;&#1588;&#1593;&#1575;&#1585; &#1575;&#1604;&#1610;&#1605;&#1606;&#1610;&#1577;" data-desc="&#1586;&#1575;&#1605;&#1604; &#1608;&#1588;&#1610;&#1604;&#1577; &#1608;&#1602;&#1589;&#1610;&#1583;&#1577; &#1608;&#1606;&#1580;&#1575;&#1581; &#1608;&#1605;&#1608;&#1587;&#1610;&#1602;&#1609; &#1571;&#1589;&#1604;&#1610;&#1577;"><span class="navIcon">&#127486;&#127466;</span><span class="navCopy"><span class="navTitle">&#1575;&#1604;&#1573;&#1607;&#1583;&#1575;&#1569;&#1575;&#1578; &#1608;&#1575;&#1604;&#1571;&#1588;&#1593;&#1575;&#1585; &#1575;&#1604;&#1610;&#1605;&#1606;&#1610;&#1577;</span><span class="navDesc">&#1606;&#1580;&#1575;&#1581; &#8226; &#1578;&#1601;&#1608;&#1602; &#8226; &#1586;&#1575;&#1605;&#1604; &#8226; &#1588;&#1610;&#1604;&#1577; &#8226; &#1573;&#1607;&#1583;&#1575;&#1569;</span></span></button>
'@

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
    $Encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($Path, $Text, $Encoding)
}

function Replace-Required {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Replacement,
        [string]$Description
    )
    $Options = [System.Text.RegularExpressions.RegexOptions]::Multiline
    $Regex = New-Object System.Text.RegularExpressions.Regex -ArgumentList @($Pattern, $Options)
    if (-not $Regex.IsMatch($Text)) {
        throw "Patch marker was not found: $Description"
    }
    return $Regex.Replace($Text, $Replacement, 1)
}

function Ensure-Python311 {
    & py -3.11 -V *> $null
    if ($LASTEXITCODE -eq 0) { return }

    $Winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "Python 3.11 is missing and winget is unavailable."
    }

    Write-Host "Installing Python 3.11..." -ForegroundColor Yellow
    & winget install --id Python.Python.3.11 --exact --silent --accept-package-agreements --accept-source-agreements
    & py -3.11 -V *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Python 3.11 installation did not complete. Restart Windows and run this installer again."
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

function Patch-StagingProject {
    param([string]$Root)

    $MainPath = Join-Path $Root "main.py"
    $ShellPath = Join-Path $Root "frontend\static\studio_shell.html"
    $ConfigPath = Join-Path $Root "backend\core\config.py"
    $InstallerPath = Join-Path $Root "installer\VoiceAIStudio.iss"

    $Main = Read-Utf8 $MainPath
    if ($Main -notmatch "yemeni_creative_routes") {
        if ($Main -match "(?m)^from backend\.api\.ultimate_studio_routes import router as ultimate_studio_router\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(from backend\.api\.ultimate_studio_routes import router as ultimate_studio_router\r?)$" -Replacement ('$1' + "`nfrom backend.api.yemeni_creative_routes import router as yemeni_creative_router") -Description "main import after ultimate studio"
        }
        elseif ($Main -match "(?m)^from backend\.api\.dashboard_routes import router as dashboard_router\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(from backend\.api\.dashboard_routes import router as dashboard_router\r?)$" -Replacement ('$1' + "`nfrom backend.api.yemeni_creative_routes import router as yemeni_creative_router") -Description "main import after dashboard"
        }
        else {
            throw "No safe import position was found in main.py."
        }
    }

    if ($Main -notmatch "app\.include_router\(yemeni_creative_router\)") {
        if ($Main -match "(?m)^app\.include_router\(ultimate_studio_router\)\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(app\.include_router\(ultimate_studio_router\)\r?)$" -Replacement ('$1' + "`napp.include_router(yemeni_creative_router)") -Description "router registration after ultimate studio"
        }
        elseif ($Main -match "(?m)^app\.include_router\(dashboard_router\)\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(app\.include_router\(dashboard_router\)\r?)$" -Replacement ('$1' + "`napp.include_router(yemeni_creative_router)") -Description "router registration after dashboard"
        }
        else {
            throw "No safe router position was found in main.py."
        }
    }
    Write-Utf8 -Path $MainPath -Text $Main

    $Shell = Read-Utf8 $ShellPath
    if ($Shell -notmatch "/static/yemeni_creative\.html") {
        $ProducerPattern = '(?m)^[ \t]*<button[^>]+data-page="/static/producer\.html"'
        $Match = [System.Text.RegularExpressions.Regex]::Match($Shell, $ProducerPattern)
        if (-not $Match.Success) {
            throw "The producer navigation marker was not found in studio_shell.html."
        }
        $Shell = $Shell.Insert($Match.Index, $NavHtml)
    }
    $Shell = [System.Text.RegularExpressions.Regex]::Replace($Shell, "Professional Studio\s+[0-9]+\.[0-9]+(?:\.[0-9]+)?", "Professional Studio 6.1.0")
    $Shell = [System.Text.RegularExpressions.Regex]::Replace($Shell, "VERSION='[0-9]+\.[0-9]+(?:\.[0-9]+)?'", "VERSION='6.1.0'")
    Write-Utf8 -Path $ShellPath -Text $Shell

    $Config = Read-Utf8 $ConfigPath
    $Config = Replace-Required -Text $Config -Pattern '(?m)^APP_VERSION\s*=\s*"[^"]+"\s*$' -Replacement 'APP_VERSION = "6.1.0"' -Description "APP_VERSION"
    if ($Config -match '(?m)^APP_RELEASE\s*=') {
        $Config = [System.Text.RegularExpressions.Regex]::Replace($Config, '(?m)^APP_RELEASE\s*=\s*"[^"]*"\s*$', 'APP_RELEASE = "Yemeni Creative Add-on"')
    }
    Write-Utf8 -Path $ConfigPath -Text $Config

    $Installer = Read-Utf8 $InstallerPath
    $Installer = Replace-Required -Text $Installer -Pattern '(?m)^#define MyAppVersion\s+"[^"]+"\s*$' -Replacement '#define MyAppVersion "6.1.0"' -Description "installer version"
    Write-Utf8 -Path $InstallerPath -Text $Installer
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
$SourceSaved = $false

try {
    Write-Step "Ibn Al-Waqadi Studio 6.1 - feature-only safe installer"
    Write-Host "Original project: $Project" -ForegroundColor Green
    Write-Host "The original project stays untouched until the staged installer succeeds." -ForegroundColor Yellow

    Ensure-Python311

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

    Write-Step "3/7 - Add only the feature links to the staged copy"
    Patch-StagingProject -Root $Stage

    Write-Step "4/7 - Compile and smoke-test the staged copy"
    Push-Location $Stage
    try {
        & py -3.11 -m pip install -r requirements.txt -r requirements-desktop.txt
        if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }

        & py -3.11 -m compileall -q main.py desktop_app.py backend
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
        Write-Utf8 -Path $SmokeFile -Text $Smoke
        & py -3.11 $SmokeFile
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
        & py -3.11 -m PyInstaller --noconfirm --clean VoiceAIStudio.spec
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

        $StagedExe = Join-Path $Stage "dist\VoiceAIStudioArabic\VoiceAIStudioArabic.exe"
        if (-not (Test-Path -LiteralPath $StagedExe -PathType Leaf)) {
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
    $SourceSaved = $true

    Start-Process -FilePath $InstalledExe
    Write-Step "Yemeni Creative add-on 6.1 installed successfully"
    Write-Host "Only the requested feature and its integration links were added." -ForegroundColor Green
    Write-Host "Keys, sessions, old tools, generated audio, and user data were not deleted." -ForegroundColor Green
    Write-Host "Source backup: $Backup" -ForegroundColor DarkGray
}
catch {
    Write-Host ""
    Write-Host ("ADD-ON ERROR: " + $_.Exception.Message) -ForegroundColor Red
    if (-not $SourceSaved) {
        Write-Host "The original source project was not changed." -ForegroundColor Yellow
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
