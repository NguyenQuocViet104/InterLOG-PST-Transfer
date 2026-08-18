@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0PST-TRANSFER-GUI.ps1"
if errorlevel 1 pause
