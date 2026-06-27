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

REM 4) Start it
echo.
echo   Starting...  your web browser will open in a few seconds.
echo   - Keep this window open while you use jobhunt.
echo   - To stop jobhunt, just close this window.
echo.
".venv\Scripts\python.exe" jobhunt.py serve
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
