@echo off
setlocal
cd /d "%~dp0"

echo 1/3 Pylint
python -m pylint app tests --score=n
if errorlevel 1 goto failed

echo 2/3 Ruff
python -m ruff check app tests
if errorlevel 1 goto failed

echo 3/3 Automated tests
python -m unittest discover -s tests -v
if errorlevel 1 goto failed

echo.
echo All quality checks passed.
pause
exit /b 0

:failed
echo.
echo One or more checks failed. Read the messages above.
pause
exit /b 1
