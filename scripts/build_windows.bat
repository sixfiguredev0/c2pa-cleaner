@echo off
setlocal enabledelayedexpansion
title Building C2PA Cleaner for Windows

echo ===================================================
echo   Building C2PA Cleaner Windows Portable Package
echo ===================================================

cd /d "%~dp0.."

echo [1/3] Checking PyInstaller...
py -m pip install pyinstaller pillow fastapi uvicorn python-multipart pydantic

echo [2/3] Running PyInstaller build...
py -m PyInstaller ^
    --name "C2PA Cleaner" ^
    --onedir ^
    --clean ^
    --add-data "app\frontend;app\frontend" ^
    --add-data "tools\c2patool;tools\c2patool" ^
    run.py

if %errorlevel% neq 0 (
    echo [ERROR] Build failed!
    pause
    exit /b %errorlevel%
)

echo [3/3] Creating launcher in dist...
copy scripts\launch_portable.bat "dist\C2PA Cleaner\Launch C2PA Cleaner.bat" >nul

echo ===================================================
echo   Build Successful!
echo   Output located in: dist\C2PA Cleaner\
echo ===================================================

endlocal
pause
