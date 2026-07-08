@echo off
REM Windows convenience wrapper - double-click, or run: scripts\dev.cmd
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dev.ps1" %*
