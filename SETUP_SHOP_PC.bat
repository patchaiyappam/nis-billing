@echo off
title NEW INDIAN STEEL - Shop PC Setup (One-Time)
color 0A
cls

echo  ============================================================
echo    NEW INDIAN STEEL - Shop PC Setup (One-Time)
echo    Sets up the app for Dad in Shop Mode.
echo  ============================================================
echo.
echo  This will:
echo    1. Seed the database with the 79 customers and 197 products
echo    2. Install the Python libraries the app needs
echo    3. Put a "NIS Billing" shortcut on the Desktop
echo    4. Open the app once so you can confirm it works
echo.
echo  Press any key to begin, or close this window to cancel.
pause >nul
echo.

cd /d "%~dp0"
set "SRC_DIR=%~dp0"
set "TARGET_DIR=%USERPROFILE%\Documents\NEW_INDIAN_STEEL"
set "TARGET_DB=%TARGET_DIR%\billing.db"
set "SEED_DB=%SRC_DIR%billing.db"

:: ============================================================
:: STEP 1 - Seed the database
:: ============================================================
echo  [1/4] Seeding the database...
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

if exist "%TARGET_DB%" (
    echo        Database already exists at:
    echo        %TARGET_DB%
    echo        Skipping seed to protect existing data.
) else (
    if exist "%SEED_DB%" (
        copy /Y "%SEED_DB%" "%TARGET_DB%" >nul
        if errorlevel 1 (
            echo        ERROR: could not copy seed DB. Check permissions.
            pause
            exit /b 1
        )
        echo        OK: seeded billing.db with 79 customers and 197 products.
    ) else (
        echo        WARN: no seed DB found at %SEED_DB%
        echo              The app will start with an empty database.
    )
)
echo.

:: ============================================================
:: STEP 2 - Find Python and install libraries
:: ============================================================
echo  [2/4] Finding Python and installing libraries...

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

echo.
echo  ERROR: Python is not installed on this PC.
echo.
echo  Download Python 3.11 or newer from:
echo     https://www.python.org/downloads/
echo.
echo  IMPORTANT during install: TICK the box that says
echo     "Add Python to PATH"
echo.
echo  After Python is installed, run this setup again.
echo.
pause
exit /b 1

:py_ok
echo        Python found: %PYTHON%
"%PYTHON%" --version
echo        Upgrading pip...
"%PYTHON%" -m pip install --upgrade pip --disable-pip-version-check
echo        Installing requirements (this can take 1-3 minutes)...
"%PYTHON%" -m pip install -r "%SRC_DIR%requirements.txt" --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  ERROR: pip install failed. Scroll up to see the actual error.
    echo  Most common causes:
    echo    - No internet connection
    echo    - Corporate proxy blocking pypi.org
    echo    - Out-of-date pip
    pause
    exit /b 1
)
echo        Verifying installed packages...
"%PYTHON%" -c "import reportlab, openpyxl, supabase; print('       OK: reportlab, openpyxl, supabase all importable')"
if errorlevel 1 (
    echo  WARN: one or more libraries failed to import. The app may still
    echo        work but cloud sync or PDFs may be disabled.
)
echo.

:: ============================================================
:: STEP 3 - Desktop shortcut to Shop Mode
:: ============================================================
echo  [3/4] Creating Desktop shortcut "NIS Billing"...

set "TARGET=%SRC_DIR%START_SHOP_MODE.bat"
set "ICON=%SRC_DIR%app_icon.ico"

:: Detect actual Desktop folder (handles OneDrive redirection)
set "DESKTOP_DIR="
for /f "usebackq tokens=*" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP_DIR=%%D"
if not defined DESKTOP_DIR (
    if exist "%USERPROFILE%\OneDrive\Desktop" set "DESKTOP_DIR=%USERPROFILE%\OneDrive\Desktop"
    if not defined DESKTOP_DIR if exist "%USERPROFILE%\Desktop" set "DESKTOP_DIR=%USERPROFILE%\Desktop"
)
if not defined DESKTOP_DIR (
    echo        WARN: could not find Desktop folder. Skipping shortcut.
    echo              You can launch by double-clicking START_SHOP_MODE.bat
    goto :after_shortcut
)
if not exist "%DESKTOP_DIR%" mkdir "%DESKTOP_DIR%"

set "SHORTCUT=%DESKTOP_DIR%\NIS Billing.lnk"
echo        Desktop folder: %DESKTOP_DIR%

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%SRC_DIR%'; $sc.IconLocation = '%ICON%'; $sc.Description = 'New Indian Steel Billing'; $sc.Save()"

if exist "%SHORTCUT%" (
    echo        OK: Desktop shortcut created.
) else (
    echo        WARN: could not create Desktop shortcut.
    echo              You can still launch by double-clicking START_SHOP_MODE.bat
)
:after_shortcut
echo.

:: ============================================================
:: STEP 4 - Launch Shop Mode for confirmation
:: ============================================================
echo  [4/4] Launching Shop Mode now to confirm everything works...
echo.
echo        If a window opens with the billing screen, you're done.
echo        Close it after you finish checking, then come back here.
echo.
pause

set NIS_MODE=shop
start "" "%PYTHON%" "%SRC_DIR%main.py"

echo.
echo  ============================================================
echo    Setup complete.
echo  ============================================================
echo.
echo    From now on, Dad can open the app by double-clicking
echo    the "NIS Billing" shortcut on the Desktop.
echo.
echo    If the shortcut is missing, the backup is:
echo       %SRC_DIR%START_SHOP_MODE.bat
echo.
pause
