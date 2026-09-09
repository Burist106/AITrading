@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Aurum Worker is not installed. Run pnpm worker:install:mt5 first.
  pause
  exit /b 2
)
start "Aurum Local Demo Profile" ".venv\Scripts\pythonw.exe" -m aurum_worker.mt5_profile_cli gui
