# استوديو ابن الواقدي 6.2.0 — إصلاح الواجهة والشيلات دون حذف البيانات
$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}

# يحتوي هذا الإصدار على واجهة 6.2.0 الكاملة، Voice Clone Pro، وأداة الشيلات المصلحة.
$SourceCommit = "3f5367790827faf41d999e0255989b2be4b69d11"
$RawRoot = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/$SourceCommit"

function Section([string]$Text) {
    Write-Host ""
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ("=" * 76) -ForegroundColor DarkCyan
}

function Find-ProjectRoot {
    $candidates = @(
        (Join-Path $env:USERPROFILE "Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "OneDrive\Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Downloads\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"),
        (Join-Path $env:USERPROFILE "OneDrive\Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"),
        (Join-Path $env:USERPROFILE "Downloads\awesome-voice-ai-tools-agent-professional-tts-engine")
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate "BUILD_WINDOWS_INSTALLER.bat"))) {
            return [string](Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ""
}

# هذه القائمة تعيد فقط ملفات البرنامج التي تأثرت بالتحديث القديم، وتضيف ملفات الإصلاح.
# لا تتضمن مجلدات المفاتيح أو الجلسات أو الأصوات أو المخرجات الموجودة في LocalAppData.
$Files = @(
    "main.py",
    "desktop_app.py",
    "BUILD_WINDOWS_INSTALLER.bat",
    "VoiceAIStudio.spec",
    "requirements.txt",
    "requirements-desktop.txt",
    "pyproject.toml",
    "setup.py",
    "config/default.json",
    "installer/VoiceAIStudio.iss",
    "scripts/validate_unified_release.py",
    "scripts/validate_yemeni_hotfix.py",
    "backend/core/config.py",
    "backend/api/unified_studio_routes.py",
    "backend/api/download_export_runtime.py",
    "backend/api/yemeni_creative_routes.py",
    "backend/api/yemeni_creative_hotfix.py",
    "backend/api/voice_clone_routes.py",
    "backend/api/studio_pro_routes.py",
    "backend/plugins/coqui_plugin.py",
    "frontend/static/studio_shell.html",
    "frontend/static/voice_clone.html",
    "frontend/static/yemeni_creative.html",
    "frontend/static/yemeni_creative_pro.html"
)

$Project = Find-ProjectRoot
if (-not $Project) {
    Write-Host "لم أجد مجلد مشروع استوديو ابن الواقدي." -ForegroundColor Red
    Write-Host "ضع مجلد VoiceAIStudio-Pro-Latest على سطح المكتب، ثم أعد تشغيل الأمر." -ForegroundColor Yellow
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Backup = Join-Path $Project ("Backups\Before-Shila-Repair-" + $Stamp)
$Temp = Join-Path $env:TEMP ("IbnWaqadi-Shila-Repair-" + [guid]::NewGuid().ToString("N"))
$DataFolder = Join-Path $env:LOCALAPPDATA "VoiceAIStudioArabic"
$DataExistedBefore = Test-Path -LiteralPath $DataFolder
New-Item -ItemType Directory -Force -Path $Backup, $Temp | Out-Null

try {
    Section "إصلاح استوديو ابن الواقدي 6.2.0 — الواجهة والشيلات"
    Write-Host "مجلد المشروع: $Project" -ForegroundColor Green
    Write-Host "لن يتم حذف أو تنظيف: المفاتيح، الجلسات، ملفات الصوت، النماذج، أو المخرجات." -ForegroundColor Yellow

    Stop-Process -Name "VoiceAIStudioArabic" -Force -ErrorAction SilentlyContinue

    Write-Host "[1/6] أخذ نسخة احتياطية من ملفات المصدر الحالية..." -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        if (Test-Path -LiteralPath $Local) {
            $BackupFile = Join-Path $Backup ($Relative -replace "/", "\")
            New-Item -ItemType Directory -Force -Path (Split-Path $BackupFile) | Out-Null
            Copy-Item -LiteralPath $Local -Destination $BackupFile -Force
        }
    }

    Write-Host "[2/6] تنزيل واجهة 6.2.0 الكاملة وملفات إصلاح الشيلات إلى مجلد مؤقت..." -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $Url = "$RawRoot/$Relative"
        $TempFile = Join-Path $Temp ($Relative -replace "/", "\")
        New-Item -ItemType Directory -Force -Path (Split-Path $TempFile) | Out-Null
        Write-Host ("  + " + $Relative) -ForegroundColor DarkCyan
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $TempFile -TimeoutSec 600
        if (-not (Test-Path -LiteralPath $TempFile) -or (Get-Item -LiteralPath $TempFile).Length -eq 0) {
            throw "لم يكتمل تنزيل الملف: $Relative"
        }
    }

    Write-Host "[3/6] تركيب الملفات بعد اكتمال جميع التنزيلات..." -ForegroundColor Cyan
    foreach ($Relative in $Files) {
        $TempFile = Join-Path $Temp ($Relative -replace "/", "\")
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        New-Item -ItemType Directory -Force -Path (Split-Path $Local) | Out-Null
        Copy-Item -LiteralPath $TempFile -Destination $Local -Force
    }

    Write-Host "[4/6] بناء البرنامج وفحص جميع أدوات 6.2.0..." -ForegroundColor Cyan
    $Builder = Join-Path $Project "BUILD_WINDOWS_INSTALLER.bat"
    $OldCI = $env:CI
    $env:CI = "1"
    try {
        $Build = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", "call `"$Builder`"") -WorkingDirectory $Project -Wait -PassThru
    } finally {
        if ($null -eq $OldCI) { Remove-Item Env:CI -ErrorAction SilentlyContinue } else { $env:CI = $OldCI }
    }
    if ($Build.ExitCode -ne 0) {
        throw "فشل بناء البرنامج أو فحص واجهة 6.2.0. رمز الخروج: $($Build.ExitCode)"
    }

    Write-Host "[5/6] اختبار أزرار إنشاء الشيلة والزامل قبل التثبيت..." -ForegroundColor Cyan
    Push-Location $Project
    try {
        py -3.11 scripts\validate_yemeni_hotfix.py
        if ($LASTEXITCODE -ne 0) { throw "فشل اختبار أزرار الشيلات." }
    } finally {
        Pop-Location
    }

    $Setup = Join-Path $Project "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $Setup)) {
        throw "لم يتم إنشاء ملف تثبيت البرنامج."
    }

    Write-Host "[6/6] تثبيت الإصلاح فوق البرنامج الحالي دون إزالة بياناته..." -ForegroundColor Cyan
    $Install = Start-Process -FilePath $Setup -ArgumentList @(
        "/VERYSILENT",
        "/SUPPRESSMSGBOXES",
        "/NORESTART",
        "/SP-",
        "/TASKS=desktopicon"
    ) -Wait -PassThru
    if ($Install.ExitCode -ne 0) {
        throw "تعذر تثبيت الإصلاح. رمز الخروج: $($Install.ExitCode)"
    }

    if ($DataExistedBefore -and -not (Test-Path -LiteralPath $DataFolder)) {
        throw "توقف فحص الأمان لأن مجلد بيانات البرنامج لم يعد ظاهرًا."
    }

    $Exe = Join-Path $env:LOCALAPPDATA "Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "اكتمل التثبيت لكن ملف تشغيل البرنامج غير موجود."
    }

    Start-Process -FilePath $Exe

    Section "تم الإصلاح بنجاح"
    Write-Host "✓ عادت واجهة Voice Clone Pro 6.2.0 وكل القوائم المصممة." -ForegroundColor Green
    Write-Host "✓ بقيت أداة استنساخ الصوت وأدوات المقابلات والاستوديو الكامل." -ForegroundColor Green
    Write-Host "✓ أضيف زر: إنشاء شيلة الآن، وزر: إنشاء زامل الآن." -ForegroundColor Green
    Write-Host "✓ الإنشاء المحلي يعمل فورًا دون مفتاح Gemini." -ForegroundColor Green
    Write-Host "✓ Gemini أصبح خيارًا منفصلًا بمهلة تمنع تعليق الزر." -ForegroundColor Green
    Write-Host "✓ لم يتم لمس مجلد البيانات: $DataFolder" -ForegroundColor Green
    Write-Host "النسخة الاحتياطية للمصدر: $Backup" -ForegroundColor DarkGray
}
catch {
    Write-Host ""
    Write-Host ("حدث خطأ: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "جارٍ إعادة ملفات المصدر التي كانت موجودة قبل الإصلاح..." -ForegroundColor Yellow
    foreach ($Relative in $Files) {
        $BackupFile = Join-Path $Backup ($Relative -replace "/", "\")
        $Local = Join-Path $Project ($Relative -replace "/", "\")
        if (Test-Path -LiteralPath $BackupFile) {
            New-Item -ItemType Directory -Force -Path (Split-Path $Local) | Out-Null
            Copy-Item -LiteralPath $BackupFile -Destination $Local -Force
        }
    }
    Write-Host "لم تُحذف المفاتيح أو الجلسات أو الأصوات أو المخرجات." -ForegroundColor Yellow
    Write-Host "النسخة الاحتياطية: $Backup" -ForegroundColor DarkGray
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}
finally {
    Remove-Item -LiteralPath $Temp -Recurse -Force -ErrorAction SilentlyContinue
}
