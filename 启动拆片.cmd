@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe scripts\bootstrap.py start
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    python scripts\bootstrap.py start
  ) else (
    py -3 scripts\bootstrap.py start
  )
)
if errorlevel 1 pause
