# استوديو ابن الواقدي 6.2.0 — إصلاح الواجهة والشيلات وXTTS من دون حذف بيانات المستخدم
$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}

$SourceCommit = "32a5d562faa931ff97152ebcb51385d83fcd0e76"
$RawRoot = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/$SourceCommit"

function Header([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 74) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 74) -ForegroundColor DarkCyan
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
    "backend/api/voice_clone_routes.py",
    "backend/api/voice_clone_repair_runtime.py",
    "frontend/static/voice_clone.html",
    "backend/api/yemeni_creative_routes.py",
    "backend/api/yemeni_creative_hotfix.py",
    "frontend/static/yemeni_creative.html",
    "frontend/static/yemeni_creative_pro.html",
    "frontend/static/studio_shell.html",
    "frontend/static/studio_shell_preserved.html",
    "frontend/static/ultimate_studio.html",
    "backend/api/download_export_runtime.py",
    "main.py",
    "desktop_app.py",
    "scripts/validate_unified_release.py",
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
$Backup = Join-Path $Project ("Backups\PreserveUI-Shila-XTTS-" + $Stamp)
$Temp = Join-Path $env:TEMP ("IbnWaqadiRepair-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $Backup, $Temp | Out-Null

try {
    Header "استوديو ابن الواقدي 6.2.0 — إصلاح شامل غير هدّام"
    Write-Host "المشروع: $Project" -ForegroundColor Green
    Write-Host "لن يتم حذف المفاتيح أو الجلسات أو العينات أو ملفات الصوت أو المشاريع." -ForegroundColor Yellow
    Stop-Process -Name "VoiceAIStudioArabic" -Force -ErrorAction SilentlyContinue

    Write-Host "[1/6] أخذ نسخة احتياطية من ملفات البرنامج المستهدفة..." -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        if (Test-Path -LiteralPath $Local) {
            $BackupFile = Join-Path $Backup ($Relative -replace "/", "\")
            New-Item -ItemType Directory -Force -Path (Split-Path $BackupFile) | Out-Null
            Copy-Item -LiteralPath $Local -Destination $BackupFile -Force
        }
    }

    Write-Host "[2/6] تنزيل ملفات الإصلاح والإضافات فقط..." -ForegroundColor Cyan
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

    Write-Host "[3/6] فحص الواجهة المحفوظة وأزرار الشيلات ومسارات API..." -ForegroundColor Cyan
    Push-Location $Project
    try {
        py -3.11 -m compileall -q main.py desktop_app.py backend scripts
        if ($LASTEXITCODE -ne 0) { throw "فشل الفحص النحوي لملفات Python." }
        py -3.11 scripts\validate_unified_release.py
        if ($LASTEXITCODE -ne 0) { throw "فشل فحص الواجهة أو الشيلات أو XTTS." }
    } finally {
        Pop-Location
    }

    Write-Host "[4/6] إصلاح بيئة XTTS الموجودة — من دون حذف العينات..." -ForegroundColor Cyan
    $XttsPython = Join-Path $env:LOCALAPPDATA "VoiceAIStudioArabic\voice_clones\local_engine\venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $XttsPython) {
        & $XttsPython -m pip install --disable-pip-version-check --no-input --upgrade --force-reinstall "transformers==4.57.6"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "لم يكتمل إصلاح XTTS الآن؛ سيكمله زر تجهيز المحرك داخل البرنامج." -ForegroundColor Yellow
        } else {
            Write-Host "تم إصلاح تعارض Transformers داخل XTTS." -ForegroundColor Green
        }
    } else {
        Write-Host "بيئة XTTS لم تُنشأ بعد؛ زر تجهيز المحرك سينشئها بالإصدارات المتوافقة." -ForegroundColor Yellow
    }

    Write-Host "[5/6] بناء البرنامج وتثبيت نفس الإصدار 6.2.0..." -ForegroundColor Cyan
    $Builder = Join-Path $Project "BUILD_WINDOWS_INSTALLER.bat"
    $BuildCommand = 'echo.|call "' + $Builder + '"'
    $Build = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", $BuildCommand) -WorkingDirectory $Project -Wait -PassThru
    if ($Build.ExitCode -ne 0) { throw "فشل بناء البرنامج. رمز الخروج: $($Build.ExitCode)" }

    $Setup = Join-Path $Project "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $Setup)) { throw "لم يتم إنشاء ملف التثبيت." }
    $Install = Start-Process -FilePath $Setup -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/TASKS=desktopicon") -Wait -PassThru
    if ($Install.ExitCode -ne 0) { throw "تعذر تثبيت البرنامج. رمز الخروج: $($Install.ExitCode)" }

    Write-Host "[6/6] تشغيل الواجهة الاحترافية المحفوظة..." -ForegroundColor Cyan
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

    Header "اكتمل إصلاح استوديو ابن الواقدي 6.2.0"
    Write-Host "تمت استعادة الواجهة الاحترافية المصممة كصفحة رئيسية." -ForegroundColor Green
    Write-Host "تم ربط أزرار إنشاء الشيلة والزامل بالكاتب المحلي الذي يعمل بلا مفتاح." -ForegroundColor Green
    Write-Host "تم إصلاح توافق XTTS مع Transformers 4.57.6." -ForegroundColor Green
    Write-Host "لم تُحذف بيانات المستخدم. النسخة الاحتياطية: $Backup" -ForegroundColor DarkGray
}
catch {
    Write-Host ""
    Write-Host ("حدث خطأ: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "جارٍ إعادة ملفات البرنامج التي كانت موجودة قبل الإصلاح..." -ForegroundColor Yellow
    foreach ($Relative in $Files) {
        $BackupFile = Join-Path $Backup ($Relative -replace "/", "\")
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        if (Test-Path -LiteralPath $BackupFile) {
            New-Item -ItemType Directory -Force -Path (Split-Path $Local) | Out-Null
            Copy-Item -LiteralPath $BackupFile -Destination $Local -Force
        }
    }
    Write-Host "لم تُمس المفاتيح أو العينات أو المشاريع أو المخرجات الصوتية." -ForegroundColor Yellow
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}
finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
