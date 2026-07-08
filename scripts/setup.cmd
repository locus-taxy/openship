@echo off
REM Windows convenience wrapper — double-click, or run: scripts\setup.cmd
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
