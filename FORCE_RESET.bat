@echo off
title NIS - Force Reset (kills app, purges queues)
color 0E
cls

echo  ============================================================
echo    NIS - Force Reset
echo    This will:
echo      1. KILL any running Python processes (closes the app)
echo      2. Purge the local sync queues
echo      3. Tell you to re-open the app
echo  ============================================================
echo.
echo  ONLY run this if the app is mis-syncing old deleted data.
echo.
echo  Press any key to begin, or close this window to cancel.
pause >nul
echo.

:: ------------------------------------------------------------
:: STEP 1 - Kill any running python.exe so the DB unlocks
:: ------------------------------------------------------------
echo  [1/3] Closing the billing app (killing python.exe)...
taskkill /F /IM python.exe   >nul 2>&1
taskkill /F /IM pythonw.exe  >nul 2>&1
taskkill /F /IM py.exe       >nul 2>&1
timeout /t 2 /nobreak >nul
echo        OK
echo.

:: ------------------------------------------------------------
:: STEP 2 - Find Python and run the purge script
:: ------------------------------------------------------------
echo  [2/3] Locating Python...
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
echo  [3/3] Purging sync queues...
cd /d "%~dp0"
"%PYTHON%" PURGE_QUEUES.py
if errorlevel 1 (
    echo.
    echo  ERROR: purge failed. See messages above.
    pause
    exit /b 1
)

echo.
echo  ============================================================
echo    Reset complete.
echo  ============================================================
echo.
echo    Now open the app by double-clicking the "NIS Billing"
echo    desktop icon (or START_SHOP_MODE.bat).
echo.
echo    On startup it will push the 79 customers fresh to Supabase
echo    with no old queue entries to interfere.
echo.
pause
