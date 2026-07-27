# Ibn Al-Waqadi Studio 6.1 - fast finalizer after successful staged install.
# ASCII-only for Windows PowerShell 5.1.
# No rebuild. No reinstall. It only saves the already installed add-on integration
# into the source project, creates a safe backup in LocalAppData, and launches the app.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$FeatureCommit = "65b565cd947af1edb8204cb22752c9db080d888f"
$RawRoot = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/$FeatureCommit"
$NavHtml = @'
      <div class="group">&#1575;&#1604;&#1573;&#1576;&#1583;&#1575;&#1593; &#1575;&#1604;&#1610;&#1605;&#1606;&#1610;</div>
      <button class="navItem yemeni" data-page="/static/yemeni_creative.html" data-title="&#1575;&#1604;&#1573;&#1607;&#1583;&#1575;&#1569;&#1575;&#1578; &#1608;&#1575;&#1604;&#1571;&#1588;&#1593;&#1575;&#1585; &#1575;&#1604;&#1610;&#1605;&#1606;&#1610;&#1577;" data-desc="&#1586;&#1575;&#1605;&#1604; &#1608;&#1588;&#1610;&#1604;&#1577; &#1608;&#1602;&#1589;&#1610;&#1583;&#1577; &#1608;&#1606;&#1580;&#1575;&#1581; &#1608;&#1605;&#1608;&#1587;&#1610;&#1602;&#1609; &#1571;&#1589;&#1604;&#1610;&#1577;"><span class="navIcon">&#127486;&#127466;</span><span class="navCopy"><span class="navTitle">&#1575;&#1604;&#1573;&#1607;&#1583;&#1575;&#1569;&#1575;&#1578; &#1608;&#1575;&#1604;&#1571;&#1588;&#1593;&#1575;&#1585; &#1575;&#1604;&#1610;&#1605;&#1606;&#1610;&#1577;</span><span class="navDesc">&#1606;&#1580;&#1575;&#1581; &#8226; &#1578;&#1601;&#1608;&#1602; &#8226; &#1586;&#1575;&#1605;&#1604; &#8226; &#1588;&#1610;&#1604;&#1577; &#8226; &#1573;&#1607;&#1583;&#1575;&#1569;</span></span></button>
'@

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
    param([string]$Text, [string]$Pattern, [string]$Replacement, [string]$Description)
    $Options = [System.Text.RegularExpressions.RegexOptions]::Multiline
    $Regex = New-Object System.Text.RegularExpressions.Regex -ArgumentList @($Pattern, $Options)
    if (-not $Regex.IsMatch($Text)) {
        throw "Patch marker was not found: $Description"
    }
    return $Regex.Replace($Text, $Replacement, 1)
}

function Patch-Source {
    param([string]$Root)

    $MainPath = Join-Path $Root "main.py"
    $ShellPath = Join-Path $Root "frontend\static\studio_shell.html"
    $ConfigPath = Join-Path $Root "backend\core\config.py"
    $InstallerPath = Join-Path $Root "installer\VoiceAIStudio.iss"

    $Main = Read-Utf8 $MainPath
    if ($Main -notmatch "yemeni_creative_routes") {
        if ($Main -match "(?m)^from backend\.api\.ultimate_studio_routes import router as ultimate_studio_router\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(from backend\.api\.ultimate_studio_routes import router as ultimate_studio_router\r?)$" -Replacement ('$1' + "`nfrom backend.api.yemeni_creative_routes import router as yemeni_creative_router") -Description "main import"
        }
        elseif ($Main -match "(?m)^from backend\.api\.dashboard_routes import router as dashboard_router\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(from backend\.api\.dashboard_routes import router as dashboard_router\r?)$" -Replacement ('$1' + "`nfrom backend.api.yemeni_creative_routes import router as yemeni_creative_router") -Description "main import fallback"
        }
        else {
            throw "No safe import position was found in main.py."
        }
    }

    if ($Main -notmatch "app\.include_router\(yemeni_creative_router\)") {
        if ($Main -match "(?m)^app\.include_router\(ultimate_studio_router\)\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(app\.include_router\(ultimate_studio_router\)\r?)$" -Replacement ('$1' + "`napp.include_router(yemeni_creative_router)") -Description "router registration"
        }
        elseif ($Main -match "(?m)^app\.include_router\(dashboard_router\)\r?$") {
            $Main = Replace-Required -Text $Main -Pattern "(?m)^(app\.include_router\(dashboard_router\)\r?)$" -Replacement ('$1' + "`napp.include_router(yemeni_creative_router)") -Description "router registration fallback"
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
            throw "Producer navigation marker was not found."
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

    if (Test-Path -LiteralPath $InstallerPath -PathType Leaf) {
        $Installer = Read-Utf8 $InstallerPath
        $Installer = Replace-Required -Text $Installer -Pattern '(?m)^#define MyAppVersion\s+"[^"]+"\s*$' -Replacement '#define MyAppVersion "6.1.0"' -Description "installer version"
        Write-Utf8 -Path $InstallerPath -Text $Installer
    }
}

$Project = Find-ProjectRoot
$InstalledExe = Join-Path $env:LOCALAPPDATA "Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
if ([string]::IsNullOrWhiteSpace($Project)) {
    Write-Host "Project folder was not found." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}
if (-not (Test-Path -LiteralPath $InstalledExe -PathType Leaf)) {
    Write-Host "The installed application was not found. The previous install did not finish." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path $env:LOCALAPPDATA "VoiceAIStudioArabic\source-backups"
$Backup = Join-Path $BackupRoot ("YemeniAddon-6.1-" + $Stamp)
$Temp = Join-Path $env:TEMP ("IbnWaqadi-Finalize-" + [guid]::NewGuid().ToString("N"))
$Changed = @(
    "backend/api/yemeni_creative_routes.py",
    "frontend/static/yemeni_creative.html",
    "main.py",
    "frontend/static/studio_shell.html",
    "backend/core/config.py",
    "installer/VoiceAIStudio.iss"
)
$ExistingBefore = @{}
$Applied = $false

try {
    Write-Host "The application is already installed. Finishing source integration only..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Backup, $Temp | Out-Null

    foreach ($Relative in $Changed) {
        $Original = Join-Path $Project ($Relative.Replace("/", "\"))
        $ExistingBefore[$Relative] = Test-Path -LiteralPath $Original -PathType Leaf
        if ($ExistingBefore[$Relative]) {
            $BackupFile = Join-Path $Backup ($Relative.Replace("/", "\"))
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $BackupFile) | Out-Null
            Copy-Item -LiteralPath $Original -Destination $BackupFile -Force
        }
    }

    $FeatureFiles = @(
        "backend/api/yemeni_creative_routes.py",
        "frontend/static/yemeni_creative.html"
    )
    foreach ($Relative in $FeatureFiles) {
        $Downloaded = Join-Path $Temp ($Relative.Replace("/", "\"))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Downloaded) | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri "$RawRoot/$Relative" -OutFile $Downloaded -TimeoutSec 420
        if (-not (Test-Path -LiteralPath $Downloaded -PathType Leaf) -or (Get-Item -LiteralPath $Downloaded).Length -lt 100) {
            throw "Feature download failed: $Relative"
        }
        $Destination = Join-Path $Project ($Relative.Replace("/", "\"))
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Downloaded -Destination $Destination -Force
    }

    Patch-Source -Root $Project
    $Applied = $true

    & py -3.11 -m compileall -q (Join-Path $Project "main.py") (Join-Path $Project "backend")
    if ($LASTEXITCODE -ne 0) {
        throw "Python source check failed."
    }

    $MainCheck = Read-Utf8 (Join-Path $Project "main.py")
    $ShellCheck = Read-Utf8 (Join-Path $Project "frontend\static\studio_shell.html")
    if ($MainCheck -notmatch "yemeni_creative_router" -or $ShellCheck -notmatch "/static/yemeni_creative\.html") {
        throw "Final integration check failed."
    }

    $Desktop = [Environment]::GetFolderPath("Desktop")
    $Shortcut = Join-Path $Desktop "Ibn Al-Waqadi Studio.lnk"
    try {
        $ShellObject = New-Object -ComObject WScript.Shell
        $Link = $ShellObject.CreateShortcut($Shortcut)
        $Link.TargetPath = $InstalledExe
        $Link.WorkingDirectory = Split-Path -Parent $InstalledExe
        $Link.IconLocation = $InstalledExe
        $Link.Save()
    }
    catch {
        Write-Host "Shortcut creation was skipped, but the application is ready." -ForegroundColor Yellow
    }

    Start-Process -FilePath $InstalledExe
    Write-Host "DONE: Yemeni Creative 6.1 is installed and the source project is synchronized." -ForegroundColor Green
    Write-Host "Backup: $Backup" -ForegroundColor DarkGray
}
catch {
    Write-Host ("FINALIZE ERROR: " + $_.Exception.Message) -ForegroundColor Red
    if ($Applied) {
        foreach ($Relative in $Changed) {
            $Original = Join-Path $Project ($Relative.Replace("/", "\"))
            $BackupFile = Join-Path $Backup ($Relative.Replace("/", "\"))
            if (Test-Path -LiteralPath $BackupFile -PathType Leaf) {
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Original) | Out-Null
                Copy-Item -LiteralPath $BackupFile -Destination $Original -Force
            }
            elseif (-not $ExistingBefore[$Relative] -and (Test-Path -LiteralPath $Original -PathType Leaf)) {
                Remove-Item -LiteralPath $Original -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Write-Host "The installed application remains available and user data was not deleted." -ForegroundColor Yellow
    Read-Host "Press Enter to close"
    exit 1
}
finally {
    if (Test-Path -LiteralPath $Temp) {
        Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
