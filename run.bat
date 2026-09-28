@echo off
setlocal
cd /d "%~dp0"
python -m app.desktop
if errorlevel 1 (
  echo.
  echo The application could not start. Make sure Python 3.11 or newer is installed.
  pause
)
