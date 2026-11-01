@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Scripts\Unreal.ps1" -Action Stream -Map /Game/Showcase/CoastalShowcase
if errorlevel 1 pause
