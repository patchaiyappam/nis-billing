@echo off
title NIS Billing - Push Update to Laptop
color 0B
echo ==============================================
echo  NIS BILLING - PUSH UPDATE
echo  (Run this on your DEV PC after making changes)
echo ==============================================
echo.
cd /d "%~dp0"

echo Checking for changes...
git diff --quiet HEAD >nul 2>&1
git status --short > "%TEMP%\gitstatus.txt" 2>&1
for %%A in ("%TEMP%\gitstatus.txt") do set SIZE=%%~zA
if %SIZE%==0 (
    echo.
    echo  [INFO] No changes to push - everything is up to date.
    pause
    exit /b 0
)

echo.
echo Files changed:
git status --short
echo.

set /p MSG=Enter a short note about what you changed (or press Enter to skip): 
if "%MSG%"=="" set MSG=App update %date% %time%

git add -A
git commit -m "%MSG%"
git push origin main

if errorlevel 1 (
    echo.
    echo  [!] Push failed. Check your internet connection.
    echo      If this is the first time, run SETUP_GITHUB.bat first.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo  SUCCESS! Update pushed to GitHub.
echo  Now go to your laptop and run GET_UPDATE.bat
echo ==============================================
pause
