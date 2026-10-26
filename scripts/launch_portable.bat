@echo off
setlocal
title C2PA Cleaner V2
cd /d "%~dp0"

if exist "C2PA Cleaner.exe" (
    echo Launching C2PA Cleaner V2...
    start "" "C2PA Cleaner.exe"
    exit /b 0
)

echo [ERROR] 'C2PA Cleaner.exe' not found in this directory.
pause
endlocal
