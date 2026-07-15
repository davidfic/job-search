#!/bin/bash
# Update jobhunt: pull the latest code (if this is a git clone) and rebuild.
# Your data in ./data is never touched.
set -e
cd "$(dirname "$0")"
if docker compose version >/dev/null 2>&1; then DC="docker compose"
else DC="docker-compose"; fi

if [ -d .git ]; then
  echo "Pulling latest code..."
  git pull --ff-only || echo "  (couldn't fast-forward -- resolve git state, then rerun)"
fi

export JOBHUNT_VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo '')"
export JOBHUNT_UID="$(id -u)"
export JOBHUNT_GID="$(id -g)"

echo "Rebuilding and restarting..."
$DC up -d --build
echo "Updated. jobhunt is running at http://127.0.0.1:8765"
