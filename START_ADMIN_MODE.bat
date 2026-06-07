@echo off
:: ── ADMIN MODE — For Patchaiyappan (Full access) ──
title NEW INDIAN STEEL - Admin Mode
cd /d "%~dp0"
set NIS_MODE=admin

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
:: Auto-install pymupdf if missing (needed for WhatsApp JPG image sending)
%PYTHON% -c "import fitz" >nul 2>&1 || (
    echo Installing pymupdf for WhatsApp image sharing...
    %PYTHON% -m pip install pymupdf --quiet
)
%PYTHON% main.py
if %errorlevel% neq 0 (
    echo.
    echo Something went wrong. Press any key to see error.
    pause
    %PYTHON% main.py
)
