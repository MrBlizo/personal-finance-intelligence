@echo off
rem Builds Personal Finance Intelligence and creates dist\PFI-Setup-<version>.exe
rem Options: -SkipTests  -SkipInstaller  -DebugBuild
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build.ps1" %*
echo.
pause
