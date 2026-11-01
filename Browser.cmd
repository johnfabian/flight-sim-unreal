@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scripts\Unreal.ps1" -Action Stream
if errorlevel 1 pause
