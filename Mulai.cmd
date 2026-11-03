@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Jalankan Setup.ps1 terlebih dahulu. Baca PANDUAN.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" run.py
pause
