# استوديو ابن الواقدي 6.1.0 — تحديث الإهداءات والأشعار اليمنية
# تحديث إضافي غير هدّام: يحفظ المفاتيح والجلسات والمخرجات، ويأخذ نسخة احتياطية من ملفات المصدر.

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}

$SourceCommit = "3e22250a289fdd77b5b4c8ecdeff54bb88cca7b2"
$RawRoot = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/$SourceCommit"

function Header([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkCyan
}

function Find-ProjectRoot {
    $candidates = @(
        (Join-Path $env:USERPROFILE "Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "OneDrive\Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Downloads\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"),
        (Join-Path $env:USERPROFILE "Downloads\awesome-voice-ai-tools-agent-professional-tts-engine")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate "BUILD_WINDOWS_INSTALLER.bat"))) {
            return [string](Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ""
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
if (-not $Project) {
    Write-Host "لم أجد مجلد مشروع استوديو ابن الواقدي." -ForegroundColor Red
    Write-Host "ضع مجلد VoiceAIStudio-Pro-Latest على سطح المكتب ثم أعد تشغيل الأمر." -ForegroundColor Yellow
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Project ("Backups\YemeniCreative-6.1-" + $Stamp)
$Temp = Join-Path $env:TEMP ("IbnWaqadi-6.1-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Backup, $Temp | Out-Null

try {
    Header "استوديو ابن الواقدي 6.1.0 — الإهداءات والأشعار اليمنية"
    Write-Host "المشروع: $Project" -ForegroundColor Green
    Write-Host "لن تُحذف بيانات LocalAppData أو المفاتيح أو الجلسات أو المخرجات." -ForegroundColor Yellow

    Stop-Process -Name "VoiceAIStudioArabic" -Force -ErrorAction SilentlyContinue

    Write-Host "[1/5] حفظ نسخة احتياطية من ملفات المصدر الحالية..." -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        if (Test-Path -LiteralPath $Local) {
            $BackupFile = Join-Path $Backup ($Relative -replace "/", "\")
            New-Item -ItemType Directory -Force -Path (Split-Path $BackupFile) | Out-Null
            Copy-Item -LiteralPath $Local -Destination $BackupFile -Force
        }
    }

    Write-Host "[2/5] تنزيل ملفات الإضافة 6.1.0 فقط..." -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Url = "$RawRoot/$Relative"
        $TempFile = Join-Path $Temp ($Relative -replace "/", "\")
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        New-Item -ItemType Directory -Force -Path (Split-Path $TempFile), (Split-Path $Local) | Out-Null
        Write-Host ("  + " + $Relative) -ForegroundColor DarkCyan
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $TempFile -TimeoutSec 420
        if (-not (Test-Path -LiteralPath $TempFile) -or (Get-Item -LiteralPath $TempFile).Length -eq 0) {
            throw "لم يكتمل تنزيل: $Relative"
        }
        Copy-Item -LiteralPath $TempFile -Destination $Local -Force
    }

    Write-Host "[3/5] فحص ملفات Python وعقود الإصدار..." -ForegroundColor Cyan
    py -3.11 -m compileall -q `
        (Join-Path $Project "main.py") `
        (Join-Path $Project "desktop_app.py") `
        (Join-Path $Project "backend") `
        (Join-Path $Project "scripts")
    if ($LASTEXITCODE -ne 0) { throw "فشل الفحص النحوي لملفات الإصدار 6.1." }

    Push-Location $Project
    try {
        py -3.11 scripts\validate_unified_release.py
        if ($LASTEXITCODE -ne 0) { throw "فشل فحص عقود الإصدار 6.1." }
    } finally {
        Pop-Location
    }

    Write-Host "[4/5] بناء ملف Windows وتثبيته..." -ForegroundColor Cyan
    $Builder = Join-Path $Project "BUILD_WINDOWS_INSTALLER.bat"
    $BuildCommand = 'echo.|call "' + $Builder + '"'
    $Build = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", $BuildCommand) -WorkingDirectory $Project -Wait -PassThru
    if ($Build.ExitCode -ne 0) { throw "فشل بناء البرنامج. رمز الخروج: $($Build.ExitCode)" }

    $Setup = Join-Path $Project "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $Setup)) { throw "لم يتم إنشاء ملف التثبيت." }
    $Install = Start-Process -FilePath $Setup -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/TASKS=desktopicon") -Wait -PassThru
    if ($Install.ExitCode -ne 0) { throw "تعذر تثبيت الإصدار. رمز الخروج: $($Install.ExitCode)" }

    Write-Host "[5/5] فتح استوديو ابن الواقدي..." -ForegroundColor Cyan
    $Exe = Join-Path $env:LOCALAPPDATA "Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
    if (-not (Test-Path -LiteralPath $Exe)) { throw "اكتمل التثبيت لكن ملف التشغيل غير موجود." }

    $Shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "استوديو ابن الواقدي.lnk"
    if (-not (Test-Path -LiteralPath $Shortcut)) {
        $Shell = New-Object -ComObject WScript.Shell
        $Link = $Shell.CreateShortcut($Shortcut)
        $Link.TargetPath = $Exe
        $Link.WorkingDirectory = Split-Path $Exe
        $Link.IconLocation = $Exe
        $Link.Save()
    }
    Start-Process -FilePath $Exe

    Header "تم تثبيت الإصدار 6.1.0 بنجاح"
    Write-Host "الأداة الجديدة: الإهداءات والأشعار اليمنية." -ForegroundColor Green
    Write-Host "الحفظ: سطح المكتب\استوديو ابن الواقدي\الأعمال اليمنية" -ForegroundColor Green
    Write-Host "النسخة الاحتياطية: $Backup" -ForegroundColor DarkGray
}
catch {
    Write-Host ""
    Write-Host ("حدث خطأ: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "جارٍ إعادة ملفات المصدر التي كانت موجودة قبل التحديث..." -ForegroundColor Yellow
    foreach ($Relative in $Files) {
        $BackupFile = Join-Path $Backup ($Relative -replace "/", "\")
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        if (Test-Path -LiteralPath $BackupFile) {
            New-Item -ItemType Directory -Force -Path (Split-Path $Local) | Out-Null
            Copy-Item -LiteralPath $BackupFile -Destination $Local -Force
        }
    }
    Write-Host "لم تُمس المفاتيح أو الجلسات أو المخرجات الصوتية." -ForegroundColor Yellow
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}
finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
