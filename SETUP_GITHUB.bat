@echo off
title NIS Billing - One-Time GitHub Setup
color 0A
echo ==============================================
echo  NIS BILLING APP - GITHUB SETUP (Run Once)
echo ==============================================
echo.
echo This sets up Git so you can push updates to
echo your laptop with one click.
echo.
echo STEP 1: Checking if Git is installed...
git --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!] Git is NOT installed.
    echo  [!] Please download and install Git from:
    echo      https://git-scm.com/download/win
    echo.
    echo  After installing, run this file again.
    pause
    start https://git-scm.com/download/win
    exit /b 1
)
echo  [OK] Git is installed.
echo.

echo STEP 2: Setting up Git identity...
set /p GIT_NAME=Enter your name (e.g. Patchai): 
set /p GIT_EMAIL=Enter your email (same as GitHub): 
git config --global user.name "%GIT_NAME%"
git config --global user.email "%GIT_EMAIL%"
echo  [OK] Identity saved.
echo.

echo STEP 3: Initialising Git in this folder...
cd /d "%~dp0"
git init
git add -A
git commit -m "Initial commit - NIS Billing App"
echo  [OK] Local repo created.
echo.

echo STEP 4: Connect to GitHub...
echo.
echo  Please do these steps in your browser:
echo  1. Go to https://github.com/new
echo  2. Create a NEW PRIVATE repo called:  nis-billing
echo  3. Do NOT add README or .gitignore
echo  4. Copy the repo URL (looks like https://github.com/YOURNAME/nis-billing.git)
echo.
set /p REPO_URL=Paste your GitHub repo URL here: 
git remote add origin %REPO_URL%
git branch -M main
git push -u origin main
echo.
if errorlevel 1 (
    echo  [!] Push failed. You may need to login to GitHub.
    echo      Run: git credential-manager configure
    pause
    exit /b 1
)
echo  [OK] Code uploaded to GitHub successfully!
echo.
echo ==============================================
echo  SETUP COMPLETE!
echo  Now use PUSH_UPDATE.bat whenever you make changes.
echo  On your laptop, run GET_UPDATE.bat to download changes.
echo ==============================================
pause
