#!/bin/bash
# Start jobhunt AND the Cloudflare tunnel (needs a token in .env).
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "No .env found. Copy .env.example to .env and paste your Cloudflare TUNNEL_TOKEN:"
  echo "    cp .env.example .env   &&   \$EDITOR .env"
  exit 1
fi
# shellcheck disable=SC1091
set -a; . ./.env; set +a
if [ -z "${TUNNEL_TOKEN:-}" ]; then
  echo "TUNNEL_TOKEN is empty in .env. Paste your Cloudflare tunnel token, then rerun."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
else echo "Docker Compose not found."; exit 1
fi

mkdir -p data
export JOBHUNT_VERSION="$(git rev-parse --short HEAD 2>/dev/null || echo '')"
export JOBHUNT_UID="$(id -u)"
export JOBHUNT_GID="$(id -g)"

echo "Building and starting jobhunt + Cloudflare tunnel..."
$DC --profile tunnel up -d --build

echo
echo "  jobhunt is running behind your Cloudflare tunnel."
echo "  Reach it at the public hostname you set in the Cloudflare dashboard"
echo "  (that hostname should point to the service URL  http://jobhunt:8765 )."
echo "  On this computer it's also at  http://127.0.0.1:8765"
echo
echo "  Tunnel logs:  docker logs -f jobhunt-tunnel"
echo "  Stop:         ./stop-jobhunt-docker.sh   (stops the tunnel too)"
