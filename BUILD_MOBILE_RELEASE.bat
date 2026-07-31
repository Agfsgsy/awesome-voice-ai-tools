@echo off
setlocal
cd /d "%~dp0"
call SETUP_MOBILE_APP.bat || exit /b 1
python scripts\build_android_app.py --all || exit /b 1
echo APK وAAB والملفات الاختبارية موجودة في dist\mobile\android\
endlocal
