@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
color 0B

echo =============================================================
echo   Ibn Al-Waqadi Studio - Voice Clone Multi-Engine Pro 7.0
echo   Safe updater + XTTS + isolated full engine pack
echo =============================================================
echo.

cd /d "%~dp0"

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git غير مثبت.
  echo ثبّت Git for Windows ثم أعد تشغيل هذا الملف.
  start "" "https://git-scm.com/download/win"
  pause
  exit /b 1
)

where py >nul 2>nul
if errorlevel 1 goto install_python
py -3.11 -c "import sys; assert sys.version_info[:2] == (3,11)" >nul 2>nul
if errorlevel 1 goto install_python
goto python_ready

:install_python
echo [1/9] Python 3.11 غير موجود. محاولة تثبيته بواسطة winget...
where winget >nul 2>nul
if errorlevel 1 (
  echo [ERROR] winget غير متوفر. ثبّت Python 3.11 64-bit يدويًا.
  start "" "https://www.python.org/downloads/release/python-3119/"
  pause
  exit /b 1
)
winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
  echo [ERROR] فشل تثبيت Python 3.11.
  pause
  exit /b 1
)

:python_ready
echo [1/9] Python 3.11 جاهز.

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [2/9] FFmpeg غير موجود. محاولة تثبيته...
  where winget >nul 2>nul
  if not errorlevel 1 winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
) else (
  echo [2/9] FFmpeg جاهز.
)

for /f "delims=" %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set BACKUP_STAMP=%%D
for /f %%C in ('git status --porcelain ^| find /c /v ""') do set CHANGES=%%C
if not "!CHANGES!"=="0" (
  echo [3/9] حفظ تعديلاتك المحلية مؤقتًا بدون حذفها...
  git stash push -u -m "VoiceClonePro7-AutoBackup-!BACKUP_STAMP!"
) else (
  echo [3/9] لا توجد تعديلات محلية تحتاج نسخة احتياطية.
)

echo [4/9] تنزيل الإصدار Voice Clone Pro 7.0...
git fetch origin agent/voice-clone-pro-v7
if errorlevel 1 goto git_error
git show-ref --verify --quiet refs/heads/agent/voice-clone-pro-v7
if errorlevel 1 (
  git checkout -b agent/voice-clone-pro-v7 origin/agent/voice-clone-pro-v7
) else (
  git checkout agent/voice-clone-pro-v7
  git reset --hard origin/agent/voice-clone-pro-v7
)
if errorlevel 1 goto git_error

echo [5/9] إنشاء بيئة تشغيل الإصدار 7...
if not exist ".venv-v7\Scripts\python.exe" py -3.11 -m venv .venv-v7
if errorlevel 1 goto python_error
call .venv-v7\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto python_error

if exist requirements.txt (
  echo [6/9] تثبيت متطلبات الاستوديو الأساسية فقط...
  python -m pip install -r requirements.txt
  if errorlevel 1 goto python_error
)
python -m pip install "httpx>=0.27,<1" "python-multipart>=0.0.9" >nul

rem لا يتم تثبيت requirements-ai.txt هنا؛ لأن Torch وXTTS والمحركات الثقيلة
rem تُثبت في بيئات مستقلة لمنع تعارض الإصدارات داخل الاستوديو الرئيسي.

echo [7/9] تجهيز XTTS-v2 المحلي وكل المحركات في بيئات مستقلة...
python scripts\install_voice_clone_engine_pack.py --all --include-music --accept-licenses
if errorlevel 1 (
  echo.
  echo [WARNING] فشل محرك اختياري أو أكثر. سيبقى XTTS قابلًا للفحص بصورة مستقلة.
)

echo [8/9] التحقق من الإصدار والمسارات والمحرك المحلي...
python scripts\verify_voice_clone_v7.py
if errorlevel 1 (
  echo.
  echo [WARNING] التحقق لم يكتمل. راجع التقرير الظاهر أعلاه.
)

echo [9/9] تشغيل استوديو ابن الواقدي Voice Clone Pro 7.0...
echo افتح: http://127.0.0.1:8000/static/voice_clone.html
echo.
python main.py
exit /b %errorlevel%

:git_error
echo [ERROR] تعذر تنزيل أو تبديل فرع الإصدار 7.
echo تعديلاتك السابقة محفوظة في git stash إن وُجدت.
pause
exit /b 1

:python_error
echo [ERROR] فشل تجهيز بيئة Python.
pause
exit /b 1
