#!/bin/bash
# jobhunt launcher (Mac / Linux)
# Sets up a small private Python environment the first time, then starts the
# app via _boot.py, which installs components and handles in-app updates.
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

# 3) Start it (the supervisor installs components when needed)
echo
echo "  Starting…  your web browser will open in a few seconds."
echo "  ▸ Keep this window open while you use jobhunt."
echo "  ▸ To stop jobhunt, just close this window."
echo
".venv/bin/python" _boot.py serve
