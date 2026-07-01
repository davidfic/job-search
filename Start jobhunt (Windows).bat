@echo off
title jobhunt
cd /d "%~dp0"

echo ===================================================
echo    jobhunt  -  local job search
echo ===================================================
echo.

REM 1) Is Python installed?
where python >nul 2>nul
if errorlevel 1 goto NOPYTHON

REM 2) Create a private environment the first time
if not exist ".venv\Scripts\python.exe" (
  echo   First-time setup - this takes about a minute, please wait...
  python -m venv .venv
  if errorlevel 1 goto NOPYTHON
)

REM 3) Install the two components we need (only if missing)
".venv\Scripts\python.exe" -c "import requests, feedparser" >nul 2>nul
if errorlevel 1 (
  echo   Installing components ^(this needs an internet connection^)...
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip >nul 2>nul
  ".venv\Scripts\python.exe" -m pip install --quiet requests feedparser
  if errorlevel 1 (
    echo   Could not download components - please check your internet connection.
    echo.
    pause
    exit /b 1
  )
)

REM 4) Let other devices on this network reach jobhunt (one-time firewall rule).
REM     Only adds the rule if it isn't already there. Windows will ask for
REM     permission the first time - click Yes. If you skip it, jobhunt still
REM     works on THIS computer, just not from phones/laptops on your Wi-Fi.
netsh advfirewall firewall show rule name="jobhunt" >nul 2>nul
if errorlevel 1 (
  echo   Allowing jobhunt through Windows Firewall so other devices can connect...
  powershell -NoProfile -Command "Start-Process netsh -Verb RunAs -ArgumentList 'advfirewall firewall add rule name=jobhunt dir=in action=allow protocol=TCP localport=8765'" >nul 2>nul
)

REM 5) Start it, listening on every network interface (--host 0.0.0.0) so other
REM     devices on the same Wi-Fi can reach it. The window prints the address.
echo.
echo   Starting...  your web browser will open in a few seconds.
echo   - Keep this window open while you use jobhunt.
echo   - To stop jobhunt, just close this window.
echo   - From another device, use the "http://192.168...." address shown below.
echo.
".venv\Scripts\python.exe" jobhunt.py serve --host 0.0.0.0
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
