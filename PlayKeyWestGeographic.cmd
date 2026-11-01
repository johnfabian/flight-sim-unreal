@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scripts\KeyWest.ps1" -Action Play -Preset Quality
if errorlevel 1 pause
