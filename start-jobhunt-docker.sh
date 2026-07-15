#!/bin/bash
# Build and start jobhunt in Docker. Data persists in ./data next to this file.
set -e
cd "$(dirname "$0")"

# Pick docker compose (v2 plugin) or docker-compose (v1).
if docker compose version >/dev/null 2>&1; then DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
else echo "Docker Compose not found. Install Docker Desktop or the compose plugin."; exit 1
fi

# Own ./data as the current user so the container (run as this user) can write it.
mkdir -p data

# Stamp the version the app shows, and run the container as this user.
export JOBHUNT_VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo '')"
export JOBHUNT_UID="$(id -u)"
export JOBHUNT_GID="$(id -g)"

echo "Building and starting jobhunt..."
$DC up -d --build

ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "  jobhunt is running."
echo "  On this computer:  http://127.0.0.1:8765"
[ -n "$ip" ] && echo "  On your network:   http://$ip:8765   (no password -- trusted Wi-Fi only)"
echo
echo "  Logs:    ./logs-jobhunt-docker.sh    Stop:  ./stop-jobhunt-docker.sh"
