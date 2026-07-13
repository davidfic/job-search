@echo off
title jobhunt
cd /d "%~dp0"

echo ===================================================
echo    jobhunt  -  local job search
echo ===================================================
echo.

REM This file stays deliberately tiny: everything that may change between
REM versions (installing components, restarting after in-app updates) lives
REM in _boot.py, which updates can replace safely.

REM 1) Is Python installed?
where python >nul 2>nul
if errorlevel 1 goto NOPYTHON

REM 2) Create a private environment the first time
if not exist ".venv\Scripts\python.exe" (
  echo   First-time setup - this takes about a minute, please wait...
  python -m venv .venv
  if errorlevel 1 goto NOPYTHON
)

REM 3) Let other devices on this network reach jobhunt (one-time firewall rule).
REM     Windows asks for permission the first time - click Yes. If you skip it,
REM     jobhunt still works on THIS computer, just not from phones on your Wi-Fi.
netsh advfirewall firewall show rule name="jobhunt" >nul 2>nul
if errorlevel 1 (
  echo   Allowing jobhunt through Windows Firewall so other devices can connect...
  powershell -NoProfile -Command "Start-Process netsh -Verb RunAs -ArgumentList 'advfirewall firewall add rule name=jobhunt dir=in action=allow protocol=TCP localport=8765'" >nul 2>nul
)

REM 4) Start it via the supervisor. --host 0.0.0.0 lets phones on your Wi-Fi in.
echo.
echo   Starting...  your web browser will open in a few seconds.
echo   - Keep this window open while you use jobhunt.
echo   - To stop jobhunt, just close this window.
echo   - From another device, use the "http://192.168...." address shown below.
echo.
".venv\Scripts\python.exe" _boot.py serve --host 0.0.0.0
pause
exit /b 0

:NOPYTHON
echo.
echo   Python is not installed.
echo.
echo   1. Go to:   https://www.python.org/downloads/
echo   2. Run the installer. On the FIRST screen, CHECK the box that says
echo      "Add Python to PATH", then click Install Now.
echo   3. Double-click this file again.
echo.
pause
exit /b 1
