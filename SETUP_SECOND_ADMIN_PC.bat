@echo off
title NIS - Second Admin PC Setup
cd /d "%~dp0"
color 0A
cls

echo ============================================================
echo  NEW INDIAN STEEL - Second Admin PC Setup
echo  Both PCs will have FULL access to everything.
echo ============================================================
echo.

REM ── Find Python ──────────────────────────────────────────
set PYTHON=
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
) do ( if exist %%p ( set PYTHON=%%p & goto :py_ok ) )
python --version >nul 2>&1 && (set PYTHON=python & goto :py_ok)
py     --version >nul 2>&1 && (set PYTHON=py     & goto :py_ok)
echo ERROR: Python not found. Install Python 3.11+ from python.org
pause & exit /b 1

:py_ok
echo [1/4] Python found: %PYTHON%
echo.

REM ── Install libraries ─────────────────────────────────────
echo [2/4] Installing libraries (takes 1-3 mins first time)...
%PYTHON% -m pip install -r requirements.txt --quiet
echo       Done.
echo.

REM ── Seed database ─────────────────────────────────────────
echo [3/4] Setting up database...
set "DIR=%USERPROFILE%\Documents\NEW_INDIAN_STEEL"
set "DB=%DIR%\billing.db"
if not exist "%DIR%" mkdir "%DIR%"

if exist "%DB%" (
    echo       DB already exists - keeping your data.
) else (
    if exist "%~dp0billing.db" (
        copy /Y "%~dp0billing.db" "%DB%" >nul
        echo       DB seeded with products and customers.
    ) else (
        echo       No seed DB found - app will pull from cloud on first run.
    )
)

REM ── IMPORTANT: Reset sync state to pull ALL data fresh ────
set "STATE=%DIR%\cloud_pull_state.json"
if exist "%STATE%" del "%STATE%"
echo       Sync state reset - will pull ALL data from Supabase on first run.
echo.

REM ── Create Desktop shortcut ───────────────────────────────
echo [4/4] Creating Desktop shortcut...
for /f "usebackq tokens=*" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set DESKTOP=%%D
if not defined DESKTOP set DESKTOP=%USERPROFILE%\Desktop

set "LNK=%DESKTOP%\NIS Admin.lnk"
set "TARGET=%~dp0START_ADMIN_MODE.bat"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=$([Runtime.InteropServices.Marshal]::GetActiveObject('WScript.Shell') 2>$null); if(!$ws){$ws=New-Object -ComObject WScript.Shell}; $sc=$ws.CreateShortcut('%LNK%'); $sc.TargetPath='%TARGET%'; $sc.WorkingDirectory='%~dp0'; $sc.Description='NIS Admin'; $sc.Save()"

if exist "%LNK%" (
    echo       Desktop shortcut "NIS Admin" created.
) else (
    echo       Could not create shortcut - use START_ADMIN_MODE.bat directly.
)
echo.

echo ============================================================
echo  Setup complete!
echo.
echo  First launch will pull ALL data from Supabase:
echo    - All 80 customers
echo    - All 262 products
echo    - All invoices and payments
echo.
echo  IMPORTANT: Make sure your admin PC (laptop) has clicked
echo  "Sync to Cloud" first so all data is in Supabase.
echo ============================================================
echo.
echo Press any key to launch Admin Mode now...
pause >nul

set NIS_MODE=admin
%PYTHON% main.py
pause
