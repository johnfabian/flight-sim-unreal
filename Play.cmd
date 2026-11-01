@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scripts\Unreal.ps1" -Action Play
if errorlevel 1 pause
