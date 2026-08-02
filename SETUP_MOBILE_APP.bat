@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python غير موجود في PATH.& exit /b 2)
where flutter >nul 2>nul || (echo Flutter غير موجود في PATH.& exit /b 2)
where java >nul 2>nul || (echo Java JDK 17 غير موجود في PATH.& exit /b 2)
if "%ANDROID_SDK_ROOT%"=="" if "%ANDROID_HOME%"=="" (echo اضبط ANDROID_SDK_ROOT إلى مجلد Android SDK.& exit /b 2)
python scripts\setup_mobile_backend.py || exit /b 1
flutter doctor -v || exit /b 1
pushd mobile_app
flutter pub get || (popd & exit /b 1)
popd
echo اكتمل إعداد تطبيق الجوال.
endlocal
