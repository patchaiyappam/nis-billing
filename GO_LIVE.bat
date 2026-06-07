@echo off
title NIS - Go Live (wipe test data + load 79 Khatabook customers)
color 0E
cls

echo  ============================================================
echo    NIS - Go Live with Real Khatabook Data
echo  ============================================================
echo.
echo  This wipes the test data on this PC and loads:
echo     - 79 real customers (with their Khatabook opening balances)
echo     - 197 real products
echo.
echo  A timestamped backup of your current DB is saved automatically
echo  so you can restore it if anything looks wrong.
echo.
echo  Press any key to begin, or close this window to cancel.
pause >nul
echo.

:: ------------------------------------------------------------
:: Kill any running python so the DB is unlocked
:: ------------------------------------------------------------
echo  [1/3] Closing the billing app...
taskkill /F /IM python.exe  >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM py.exe      >nul 2>&1
timeout /t 2 /nobreak >nul
echo        OK
echo.

:: ------------------------------------------------------------
:: Find Python
:: ------------------------------------------------------------
echo  [2/3] Finding Python...
set PYTHON=
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
) do ( if exist %%p ( set "PYTHON=%%~p" & goto :py_ok ) )
python --version >nul 2>&1 && (set "PYTHON=python" & goto :py_ok)
py --version >nul 2>&1 && (set "PYTHON=py" & goto :py_ok)
echo  ERROR: Python not found.
pause
exit /b 1

:py_ok
echo        Python: %PYTHON%
echo.

:: ------------------------------------------------------------
:: Run the reseed script
:: ------------------------------------------------------------
echo  [3/3] Wiping test data and loading the 79 real customers...
cd /d "%~dp0"
"%PYTHON%" WIPE_AND_RESEED.py
if errorlevel 1 (
    echo.
    echo  ERROR: reseed failed. See messages above.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    Done. You are now in REAL INVOICE mode.
echo  ============================================================
echo.
echo    Next:
echo      1. Open the app via the "NIS Billing" desktop shortcut
echo      2. Wait ~60 seconds for the customers to sync to cloud
echo      3. Generate a real bill against any real customer
echo.
pause
