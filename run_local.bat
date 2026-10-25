@echo off
setlocal
title C2PA Cleaner

echo ===================================================
echo   Launching C2PA Cleaner...
echo ===================================================

cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel% equ 0 (
    py run.py
    goto end
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    python run.py
    goto end
)

echo [ERROR] Neither 'py' nor 'python' was found on your system PATH.
echo Please install Python 3.11+ from https://www.python.org/
pause

:end
endlocal
