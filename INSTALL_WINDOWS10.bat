@echo off
title NEW INDIAN STEEL - One-Time Setup
color 0A
cls

echo  ================================================
echo    NEW INDIAN STEEL - Billing System
echo    One-Time Setup (Windows 10 / Windows 11)
echo  ================================================
echo.
echo  This installs the Python libraries the app needs.
echo  Run this ONCE. After that, use:
echo     - START_SHOP_MODE.bat   (for Dad)
echo     - START_ADMIN_MODE.bat  (for Patchaiyappan)
echo.

cd /d "%~dp0"

:: ── Find Python ────────────────────────────────────
set PYTHON=
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
) do ( if exist %%p ( set PYTHON=%%p & goto :found ) )

python --version >nul 2>&1 && set PYTHON=python & goto :found
py --version >nul 2>&1 && set PYTHON=py & goto :found

echo.
echo  ERROR: Python is not installed.
echo.
echo  Please install Python 3.10 or newer from:
echo     https://www.python.org/downloads/
echo.
echo  IMPORTANT: During install, tick the box that says
echo  "Add Python to PATH".
echo.
pause
exit /b 1

:found
echo  Python found: %PYTHON%
echo.

echo  Installing required libraries...
%PYTHON% -m pip install --upgrade pip --quiet --disable-pip-version-check
%PYTHON% -m pip install -r requirements.txt --quiet --disable-pip-version-check

if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Library install failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo  ================================================
echo    Setup complete!
echo  ================================================
echo.
echo   To open the app:
echo     - Double-click  START_SHOP_MODE.bat   (Dad - simple mode)
echo     - Double-click  START_ADMIN_MODE.bat  (Patchaiyappan - full mode)
echo.
pause
