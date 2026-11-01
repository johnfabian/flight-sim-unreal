@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scripts\KeyWestDetail.ps1" -Action Play -Preset Quality
if errorlevel 1 pause
