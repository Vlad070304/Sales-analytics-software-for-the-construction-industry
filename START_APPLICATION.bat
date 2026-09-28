@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -m app.desktop
) else (
  python -m app.desktop
)

if errorlevel 1 (
  echo.
  echo The application could not start.
  echo Install Python 3.11 or newer from https://www.python.org/downloads/
  echo During installation, select "Add Python to PATH".
  pause
)
