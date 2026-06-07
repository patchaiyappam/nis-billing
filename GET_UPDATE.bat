@echo off
title NIS Billing - Get Latest Update
color 0A
echo ==============================================
echo  NIS BILLING - GET LATEST UPDATE
echo  (Run this on your LAPTOP to get new changes)
echo ==============================================
echo.
cd /d "%~dp0"

REM First time on this laptop - clone the repo
if not exist ".git" (
    echo  [!] Git not set up on this laptop yet.
    echo.
    echo  Please follow these steps:
    echo  1. Install Git from https://git-scm.com/download/win
    echo  2. Open Command Prompt in this folder
    echo  3. Run: git init
    echo  4. Run: git remote add origin YOUR_GITHUB_URL
    echo  5. Run: git pull origin main
    echo  6. Then use GET_UPDATE.bat normally.
    echo.
    pause
    exit /b 1
)

echo Closing the app if it is running...
taskkill /f /im pythonw.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo.
echo Downloading latest changes from GitHub...
git fetch origin main
git reset --hard origin/main

if errorlevel 1 (
    echo.
    echo  [!] Update failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo  UPDATE COMPLETE!
echo ==============================================
echo.
echo Changes downloaded:
git log --oneline -5
echo.

set /p RESTART=Restart the NIS Billing app now? (Y/N): 
if /i "%RESTART%"=="Y" (
    echo Starting app...
    start pythonw main.py
)
echo.
pause
