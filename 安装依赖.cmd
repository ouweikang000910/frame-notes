@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python scripts\bootstrap.py install
) else (
  py -3 scripts\bootstrap.py install
)
pause
