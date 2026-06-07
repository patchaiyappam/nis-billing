@echo off
:: ── SHOP MODE — For Dad (Simple: Bill + Payment only) ──
title NEW INDIAN STEEL - Shop Mode
cd /d "%~dp0"
set NIS_MODE=shop

:: Find Python
set PYTHON=
for %%p in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
) do ( if exist %%p ( set PYTHON=%%p & goto :run ) )
python --version >nul 2>&1 && set PYTHON=python & goto :run
py --version >nul 2>&1 && set PYTHON=py & goto :run
echo Python not found. Run INSTALL_WINDOWS10.bat first.
pause & exit /b 1

:run
%PYTHON% main.py
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong. Press any key to see error.
    pause
    %PYTHON% main.py
)
