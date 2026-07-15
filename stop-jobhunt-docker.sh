#!/bin/bash
# Stop jobhunt. Your data in ./data is left untouched.
set -e
cd "$(dirname "$0")"
if docker compose version >/dev/null 2>&1; then DC="docker compose"
else DC="docker-compose"; fi
$DC down
echo "jobhunt stopped. Data kept in ./data. Start again with ./start-jobhunt-docker.sh"
