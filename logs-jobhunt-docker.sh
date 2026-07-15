#!/bin/bash
# Follow jobhunt's logs (Ctrl-C to stop watching; the app keeps running).
cd "$(dirname "$0")"
if docker compose version >/dev/null 2>&1; then DC="docker compose"
else DC="docker-compose"; fi
exec $DC logs -f
