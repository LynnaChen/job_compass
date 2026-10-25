@echo off
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
  start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch.pyw"
) else (
  start "" pythonw.exe "%~dp0launch.pyw"
)
