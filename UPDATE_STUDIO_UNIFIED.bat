@echo off
chcp 65001 >nul
title استوديو ابن الواقدي - التحديث الموحد
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0UPDATE_STUDIO_UNIFIED.ps1"
