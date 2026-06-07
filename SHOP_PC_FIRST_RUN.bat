@echo off
title NIS Shop PC - First Run Setup
cd /d "%~dp0"
echo ============================================================
echo  NEW INDIAN STEEL - Shop PC First Run
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from python.org
    pause & exit /b 1
)

REM Install requirements
echo Installing required libraries...
python -m pip install -r requirements.txt --quiet
echo Done.
echo.

REM Check if DB exists, create if not
set "DB=%USERPROFILE%\Documents\NEW_INDIAN_STEEL\billing.db"
if not exist "%USERPROFILE%\Documents\NEW_INDIAN_STEEL" mkdir "%USERPROFILE%\Documents\NEW_INDIAN_STEEL"

if exist "%DB%" (
    echo DB already exists - keeping existing data.
) else (
    echo Seeding DB from local copy...
    copy /Y "%~dp0billing.db" "%DB%" >nul
    echo Done.
)
echo.

REM Delete old pull state so we pull ALL data from Supabase fresh
set "STATE=%USERPROFILE%\Documents\NEW_INDIAN_STEEL\cloud_pull_state.json"
if exist "%STATE%" (
    echo Resetting sync state to force full pull from Supabase...
    del "%STATE%"
)
echo.

REM Run the app in shop mode
echo Starting app in Shop Mode...
echo The app will pull all customers and products from the cloud on startup.
echo.
set NIS_MODE=shop
python main.py

pause
