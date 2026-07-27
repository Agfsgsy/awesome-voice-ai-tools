# استوديو ابن الواقدي — إصلاح تحميل الصوت فقط
# لا يغيّر رقم الإصدار، ولا يحذف المفاتيح أو الجلسات أو الأصوات أو المخرجات.

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}

function Find-ProjectRoot {
    $candidates = @(
        (Join-Path $env:USERPROFILE "Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "OneDrive\Desktop\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Downloads\VoiceAIStudio-Pro-Latest"),
        (Join-Path $env:USERPROFILE "Desktop\awesome-voice-ai-tools-agent-professional-tts-engine"),
        (Join-Path $env:USERPROFILE "Downloads\awesome-voice-ai-tools-agent-professional-tts-engine")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate "main.py")) {
            return [string](Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ""
}

function Add-LineBefore([string]$Content, [string]$Marker, [string]$Line) {
    $index = $Content.IndexOf($Marker, [StringComparison]::Ordinal)
    if ($index -lt 0) { throw "لم أجد موضع الربط المطلوب داخل main.py: $Marker" }
    return $Content.Insert($index, $Line + [Environment]::NewLine)
}

$project = Find-ProjectRoot
if (-not $project) {
    Write-Host "لم أجد مجلد مشروع استوديو ابن الواقدي." -ForegroundColor Red
    Write-Host "يجب أن يكون المجلد VoiceAIStudio-Pro-Latest على سطح المكتب أو داخل التنزيلات." -ForegroundColor Yellow
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $project ("Backups\AudioDownloadFix-" + $stamp)
$mainFile = Join-Path $project "main.py"
$runtimeDir = Join-Path $project "backend\api"
$runtimeFile = Join-Path $runtimeDir "download_export_runtime.py"
$tempFile = Join-Path $env:TEMP ("download_export_runtime-" + $stamp + ".py")
$builder = Join-Path $project "BUILD_WINDOWS_INSTALLER.bat"

try {
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host " إصلاح تحميل الصوت فقط — مع الحفاظ على نفس الإصدار" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor DarkCyan
    Write-Host "المشروع: $project" -ForegroundColor Green

    Stop-Process -Name "VoiceAIStudioArabic" -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $backup, $runtimeDir | Out-Null
    Copy-Item -LiteralPath $mainFile -Destination (Join-Path $backup "main.py") -Force
    if (Test-Path -LiteralPath $runtimeFile) {
        Copy-Item -LiteralPath $runtimeFile -Destination (Join-Path $backup "download_export_runtime.py") -Force
    }

    Write-Host "[1/4] تنزيل ملف إصلاح التحميل فقط..." -ForegroundColor Cyan
    $runtimeUrl = "https://raw.githubusercontent.com/Agfsgsy/awesome-voice-ai-tools/85dc9ec1d9f1215908c5bc50a15b86a4c04380ce/backend/api/download_export_runtime.py"
    Invoke-WebRequest -UseBasicParsing -Uri $runtimeUrl -OutFile $tempFile -TimeoutSec 300
    if (-not (Test-Path -LiteralPath $tempFile)) { throw "لم يكتمل تنزيل ملف الإصلاح." }
    Copy-Item -LiteralPath $tempFile -Destination $runtimeFile -Force

    Write-Host "[2/4] ربط الإصلاح بالنسخة الحالية دون تغيير إصدارها..." -ForegroundColor Cyan
    $content = Get-Content -LiteralPath $mainFile -Raw -Encoding UTF8
    $importLine = "from backend.api.download_export_runtime import install_download_export_runtime"
    if (-not $content.Contains($importLine)) {
        $content = Add-LineBefore $content "from backend.core.config import" $importLine
    }
    $callLine = "install_download_export_runtime(app)"
    if (-not $content.Contains($callLine)) {
        if ($content.Contains("def _validate_api_contracts")) {
            $content = Add-LineBefore $content "def _validate_api_contracts" ("# إصلاح تحميل الصوت فقط: ينسخ الملف إلى سطح المكتب ثم يرسله للتحميل.`r`n" + $callLine + "`r`n")
        } elseif ($content.Contains("static_dir = FRONTEND_DIR")) {
            $content = Add-LineBefore $content "static_dir = FRONTEND_DIR" ($callLine + "`r`n")
        } else {
            throw "تعذر تحديد موضع تشغيل إصلاح التحميل داخل main.py."
        }
    }
    Set-Content -LiteralPath $mainFile -Value $content -Encoding UTF8

    Write-Host "[3/4] فحص الملفين ثم بناء نفس الإصدار..." -ForegroundColor Cyan
    py -3.11 -m py_compile $runtimeFile $mainFile
    if ($LASTEXITCODE -ne 0) { throw "فشل الفحص النحوي لملفات الإصلاح." }
    if (-not (Test-Path -LiteralPath $builder)) { throw "ملف بناء البرنامج غير موجود." }
    $buildCommand = 'echo.|call "' + $builder + '"'
    $build = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", $buildCommand) -WorkingDirectory $project -Wait -PassThru
    if ($build.ExitCode -ne 0) { throw "فشل بناء البرنامج. رمز الخروج: $($build.ExitCode)" }

    Write-Host "[4/4] تثبيت الإصلاح وتشغيل البرنامج..." -ForegroundColor Cyan
    $setup = Join-Path $project "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $setup)) { throw "لم يتم إنشاء ملف التثبيت." }
    $install = Start-Process -FilePath $setup -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/TASKS=desktopicon") -Wait -PassThru
    if ($install.ExitCode -ne 0) { throw "تعذر تثبيت الإصلاح. رمز الخروج: $($install.ExitCode)" }

    $exe = Join-Path $env:LOCALAPPDATA "Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
    if (Test-Path -LiteralPath $exe) { Start-Process -FilePath $exe }

    Write-Host "" 
    Write-Host "تم إصلاح تحميل الصوت مع بقاء رقم الإصدار نفسه." -ForegroundColor Green
    Write-Host "عند الضغط على تحميل، ستوجد نسخة مؤكدة هنا:" -ForegroundColor Green
    Write-Host "سطح المكتب\استوديو ابن الواقدي\اسم المحرك\اسم الأداة" -ForegroundColor Yellow
    Write-Host "تم حفظ نسخة احتياطية من main.py داخل: $backup" -ForegroundColor DarkGray
}
catch {
    Write-Host "" 
    Write-Host ("حدث خطأ: " + $_.Exception.Message) -ForegroundColor Red
    $savedMain = Join-Path $backup "main.py"
    if (Test-Path -LiteralPath $savedMain) {
        Copy-Item -LiteralPath $savedMain -Destination $mainFile -Force
        Write-Host "تمت إعادة main.py من النسخة الاحتياطية؛ لم تُمس بيانات المستخدم." -ForegroundColor Yellow
    }
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}
finally {
    Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
}
