@echo off
title NIS Billing - Desktop Shortcut Creator
color 0A
cls

echo  ============================================================
echo    NIS Billing - Desktop Shortcut Creator
echo  ============================================================
echo.

cd /d "%~dp0"
set "SRC_DIR=%~dp0"
set "TARGET=%SRC_DIR%START_SHOP_MODE.bat"
set "ICON=%SRC_DIR%app_icon.ico"
set "SHORTCUT_NAME=NIS Billing.lnk"

:: ============================================================
:: Detect where the real Desktop folder is.
:: On many Windows installs OneDrive redirects %USERPROFILE%\Desktop
:: to %OneDrive%\Desktop, so the old path no longer exists.
:: ============================================================

set "DESKTOP_DIR="

:: 1. Ask the shell directly (most reliable)
for /f "usebackq tokens=*" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP_DIR=%%D"

if defined DESKTOP_DIR (
    echo  Detected Desktop folder via Windows API:
    echo     %DESKTOP_DIR%
) else (
    echo  PowerShell detection failed, trying common locations...
    if exist "%USERPROFILE%\OneDrive\Desktop" set "DESKTOP_DIR=%USERPROFILE%\OneDrive\Desktop"
    if not defined DESKTOP_DIR if exist "%USERPROFILE%\Desktop" set "DESKTOP_DIR=%USERPROFILE%\Desktop"
    if not defined DESKTOP_DIR if exist "%OneDrive%\Desktop" set "DESKTOP_DIR=%OneDrive%\Desktop"
)

if not defined DESKTOP_DIR (
    echo  ERROR: could not locate your Desktop folder.
    echo         Please create one manually and re-run.
    pause
    exit /b 1
)

if not exist "%DESKTOP_DIR%" (
    echo  Desktop folder does not exist yet, creating it...
    mkdir "%DESKTOP_DIR%"
)

set "SHORTCUT=%DESKTOP_DIR%\%SHORTCUT_NAME%"
echo.
echo  Creating shortcut at:
echo     %SHORTCUT%
echo  Pointing to:
echo     %TARGET%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%SRC_DIR%'; $sc.IconLocation = '%ICON%'; $sc.Description = 'New Indian Steel Billing'; $sc.Save()"

if exist "%SHORTCUT%" (
    echo  OK: Desktop shortcut created.
    echo      Dad can now double-click "NIS Billing" on the Desktop.
) else (
    echo  ERROR: shortcut creation failed.
    echo         Try right-clicking START_SHOP_MODE.bat and choosing
    echo         "Send to ^> Desktop (create shortcut)" as a fallback.
)

echo.
pause
