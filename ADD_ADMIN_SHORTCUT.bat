@echo off
:: ============================================================
:: ADD_ADMIN_SHORTCUT.bat
:: Run this ONCE on the shop PC to add an "NIS Admin" shortcut
:: to the Desktop. After that, Dad keeps "NIS Billing" (shop mode)
:: and you get "NIS Admin" for full access on the same PC.
:: ============================================================
title NIS - Add Admin Shortcut
color 0B
cls

echo  ============================================================
echo    NEW INDIAN STEEL - Add Admin Mode Shortcut
echo  ============================================================
echo.

cd /d "%~dp0"
set "SRC_DIR=%~dp0"
set "TARGET=%SRC_DIR%START_ADMIN_MODE.bat"
set "ICON=%SRC_DIR%app_icon.ico"
set "SHORTCUT_NAME=NIS Admin.lnk"

:: Detect Desktop folder
set "DESKTOP_DIR="
for /f "usebackq tokens=*" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP_DIR=%%D"

if not defined DESKTOP_DIR (
    if exist "%USERPROFILE%\OneDrive\Desktop" set "DESKTOP_DIR=%USERPROFILE%\OneDrive\Desktop"
    if not defined DESKTOP_DIR if exist "%USERPROFILE%\Desktop" set "DESKTOP_DIR=%USERPROFILE%\Desktop"
)

if not defined DESKTOP_DIR (
    echo  ERROR: Could not find Desktop folder.
    echo         Manually create a shortcut to START_ADMIN_MODE.bat
    pause & exit /b 1
)

set "SHORTCUT=%DESKTOP_DIR%\%SHORTCUT_NAME%"

echo  Creating "NIS Admin" shortcut on Desktop...
echo  Location: %SHORTCUT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%SRC_DIR%'; $sc.IconLocation = '%ICON%'; $sc.Description = 'New Indian Steel - Admin Mode (Full Access)'; $sc.Save()"

if exist "%SHORTCUT%" (
    echo  ============================================================
    echo   SUCCESS!
    echo   "NIS Admin" shortcut added to Desktop.
    echo.
    echo   PIN to unlock Admin mode from Shop mode: 1216
    echo.
    echo   Desktop now has:
    echo     "NIS Billing" = Shop Mode  (for Dad)
    echo     "NIS Admin"   = Admin Mode (full access, for you)
    echo  ============================================================
) else (
    echo  ERROR: Could not create shortcut automatically.
    echo         Right-click START_ADMIN_MODE.bat ^> Send to ^> Desktop.
)

echo.
pause
