# استوديو ابن الواقدي — محدث موحد لكل ملفات المشروع
# يقوم بتنزيل الفرع الكامل، مزامنته، التحقق منه، بناء المثبت وتثبيته.
# لا يحذف بيانات المستخدم أو المفاتيح أو المخرجات الموجودة في LocalAppData.

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {}

function Title([string]$Text) {
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
        (Join-Path $env:USERPROFILE "Downloads\awesome-voice-ai-tools-agent-professional-tts-engine"),
        $PSScriptRoot
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath (Join-Path $candidate "BUILD_WINDOWS_INSTALLER.bat"))) {
            return [string](Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ""
}

function Copy-CompleteSource([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $excludeDirs = @(".git", ".venv", "build", "dist", "dist-installer", "__pycache__")
    $args = @($Source, $Destination, "/E", "/R:2", "/W:2", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD") + $excludeDirs
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "فشلت مزامنة ملفات المشروع. رمز Robocopy: $LASTEXITCODE"
    }
}

$tempRoot = Join-Path $env:TEMP ("IbnWaqadiUnified-" + [guid]::NewGuid().ToString("N"))
$archive = Join-Path $tempRoot "studio.zip"
$extract = Join-Path $tempRoot "source"
$project = ""

try {
    Title "استوديو ابن الواقدي — التحديث الموحد الكامل"
    Stop-Process -Name "VoiceAIStudioArabic" -Force -ErrorAction SilentlyContinue

    $project = Find-ProjectRoot
    if (-not $project) {
        $project = Join-Path ([Environment]::GetFolderPath("Desktop")) "VoiceAIStudio-Pro-Latest"
        Write-Host "لم يوجد مجلد المشروع القديم؛ سيتم إنشاؤه على سطح المكتب." -ForegroundColor Yellow
    }
    Write-Host "مجلد المشروع: $project" -ForegroundColor Green

    New-Item -ItemType Directory -Force -Path $tempRoot, $extract | Out-Null
    Write-Host "[1/5] تنزيل جميع ملفات الإصدار الموحد من GitHub..." -ForegroundColor Cyan
    $sourceRefs = @("codex/ultimate-voice-studio-6", "agent/professional-tts-engine")
    $downloadedRef = ""
    foreach ($sourceRef in $sourceRefs) {
        $url = "https://github.com/Agfsgsy/awesome-voice-ai-tools/archive/refs/heads/$sourceRef.zip"
        try {
            Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive -TimeoutSec 600
            if ((Test-Path -LiteralPath $archive) -and ((Get-Item -LiteralPath $archive).Length -gt 10000)) {
                $downloadedRef = $sourceRef
                break
            }
        } catch {
            Write-Host "لم يتوفر المصدر $sourceRef؛ سأجرب المصدر المستقر التالي." -ForegroundColor Yellow
        }
    }
    if (-not $downloadedRef) { throw "لم يكتمل تنزيل المشروع من أي مصدر موثوق." }
    Write-Host "تم اختيار مصدر الإصدار: $downloadedRef" -ForegroundColor Green

    Write-Host "[2/5] فك الضغط ومزامنة المشروع كاملًا..." -ForegroundColor Cyan
    Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force
    $sourceDir = Get-ChildItem -LiteralPath $extract -Directory | Select-Object -First 1
    if (-not $sourceDir) { throw "لم يتم العثور على ملفات المشروع داخل الحزمة." }
    Copy-CompleteSource -Source $sourceDir.FullName -Destination $project

    # هذه مجلدات بناء مولدة فقط؛ بيانات المستخدم والمفاتيح والمخرجات موجودة في LocalAppData ولا تمس.
    Remove-Item -LiteralPath (Join-Path $project "build"), (Join-Path $project "dist"), (Join-Path $project "dist-installer") -Recurse -Force -ErrorAction SilentlyContinue

    $builder = Join-Path $project "BUILD_WINDOWS_INSTALLER.bat"
    if (-not (Test-Path -LiteralPath $builder)) { throw "ملف البناء الموحد غير موجود بعد المزامنة." }

    Write-Host "[3/5] فحص جميع العقود والسياسات ثم بناء التطبيق..." -ForegroundColor Cyan
    $buildCommand = 'echo.|call "' + $builder + '"'
    $build = Start-Process -FilePath "cmd.exe" -ArgumentList @("/d", "/c", $buildCommand) -WorkingDirectory $project -Wait -PassThru
    if ($build.ExitCode -ne 0) { throw "فشل فحص أو بناء الإصدار الموحد. رمز الخروج: $($build.ExitCode)" }

    $setup = Join-Path $project "dist-installer\VoiceAIStudioSetup.exe"
    if (-not (Test-Path -LiteralPath $setup)) { throw "لم يتم إنشاء VoiceAIStudioSetup.exe." }

    Write-Host "[4/5] تثبيت الإصدار الموحد فوق النسخة الحالية..." -ForegroundColor Cyan
    $install = Start-Process -FilePath $setup -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/TASKS=desktopicon") -Wait -PassThru
    if ($install.ExitCode -ne 0) { throw "تعذر تثبيت البرنامج. رمز الخروج: $($install.ExitCode)" }

    Write-Host "[5/5] تشغيل استوديو ابن الواقدي..." -ForegroundColor Cyan
    $exe = Join-Path $env:LOCALAPPDATA "Programs\Voice AI Studio Arabic Pro\VoiceAIStudioArabic.exe"
    if (-not (Test-Path -LiteralPath $exe)) { throw "اكتمل التثبيت لكن ملف التشغيل غير موجود في المسار المتوقع." }

    $shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "استوديو ابن الواقدي.lnk"
    if (-not (Test-Path -LiteralPath $shortcut)) {
        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($shortcut)
        $link.TargetPath = $exe
        $link.WorkingDirectory = Split-Path $exe
        $link.IconLocation = $exe
        $link.Save()
    }

    Start-Process -FilePath $exe
    Title "تم تثبيت استوديو ابن الواقدي 6.0 — Ultimate Voice"
    Write-Host "تم تحديث المشروع كاملًا من مصدر واحد، وليس ملفات متفرقة." -ForegroundColor Green
    Write-Host "تم الحفاظ على المفاتيح والجلسات والمخرجات وملفات المستخدم." -ForegroundColor Green
}
catch {
    Write-Host ""
    Write-Host ("حدث خطأ: " + $_.Exception.Message) -ForegroundColor Red
    Write-Host "لم تُحذف بيانات المستخدم. يمكنك إعادة تشغيل المحدث بعد معالجة الرسالة." -ForegroundColor Yellow
    Read-Host "اضغط Enter للإغلاق"
    exit 1
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
