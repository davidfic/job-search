#!/bin/bash
# jobhunt launcher (Mac / Linux)
# First run: sets up a small private Python environment and downloads the two
# components it needs. After that it just starts the app and opens your browser.
# You never have to type anything — just double-click this file.

cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "   jobhunt  —  local job search"
echo "==================================================="
echo

# 1) Find a usable Python (3.9 or newer)
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys; exit(0 if sys.version_info[:2] >= (3, 9) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "  Python is not installed (or is too old)."
  echo
  echo "  1. Go to:   https://www.python.org/downloads/"
  echo "  2. Download and install Python (3.9 or newer)."
  echo "  3. Double-click this file again."
  echo
  read -r -p "  Press Enter to close this window. " _
  exit 1
fi

# 2) Create a private environment the first time
if [ ! -d ".venv" ]; then
  echo "  First-time setup — this takes about a minute, please wait..."
  "$PY" -m venv .venv || { echo "  Setup failed."; read -r -p "  Press Enter to close. " _; exit 1; }
fi
VPY=".venv/bin/python"

# 3) Install the two components we need (only if they're missing)
if ! "$VPY" -c 'import requests, feedparser' >/dev/null 2>&1; then
  echo "  Installing components (this needs an internet connection)..."
  "$VPY" -m pip install --quiet --upgrade pip >/dev/null 2>&1
  if ! "$VPY" -m pip install --quiet requests feedparser; then
    echo "  Could not download components — please check your internet connection."
    read -r -p "  Press Enter to close. " _
    exit 1
  fi
fi

# 4) Start it
echo
echo "  Starting…  your web browser will open in a few seconds."
echo "  ▸ Keep this window open while you use jobhunt."
echo "  ▸ To stop jobhunt, just close this window."
echo
"$VPY" jobhunt.py serve
