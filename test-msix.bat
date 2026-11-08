@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\test-msix.ps1" %*
pause
