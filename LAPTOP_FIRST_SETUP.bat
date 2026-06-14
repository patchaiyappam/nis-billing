@echo off
title NIS Billing - Laptop First Time Setup
color 0A
echo ==============================================
echo  NIS BILLING - LAPTOP FIRST TIME GIT SETUP
echo ==============================================
echo.

echo Checking Git...
git --version >nul 2>&1
if errorlevel 1 (
    echo [!] Git not installed. Download from https://git-scm.com/download/win
    pause
    start https://git-scm.com/download/win
    exit /b 1
)
echo [OK] Git found.
echo.

cd /d "%~dp0"

echo Setting up Git identity...
set /p GIT_NAME=Enter your name: 
set /p GIT_EMAIL=Enter your email (same as GitHub): 
git config --global user.name "%GIT_NAME%"
git config --global user.email "%GIT_EMAIL%"
echo.

echo Connecting to GitHub repo...
git remote remove origin >nul 2>&1
git remote add origin https://github.com/patchaiyappam/nis-billing.git
git fetch origin
git branch -M main
git branch --set-upstream-to=origin/main main
echo.

echo Pulling latest code from GitHub...
git reset --hard origin/main

if errorlevel 1 (
    echo [!] Failed. Check internet connection.
    pause
    exit /b 1
)

echo.
echo ==============================================
echo  LAPTOP SETUP COMPLETE!
echo  Use PUSH_UPDATE.bat to send laptop changes.
echo  Use GET_UPDATE.bat to receive PC changes.
echo ==============================================
pause
