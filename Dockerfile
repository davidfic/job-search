# jobhunt -- containerized for Linux.
#
# Data (db, config, secrets, resumes, exclude list) is written to /data, which
# the compose file bind-mounts to ./data on the host, so it survives image
# rebuilds. The in-app self-updater is disabled in the container
# (JOBHUNT_CONTAINER=1); update by rebuilding the image (see update-jobhunt-docker.sh).

FROM python:3.12-slim

WORKDIR /app

# Dependencies first, so code changes don't bust the pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (personal data + build cruft excluded via .dockerignore).
COPY . .

# Stamp the version the app reports. Passed from the build (git sha); harmless
# if empty (the UI just shows "unknown version").
ARG JOBHUNT_VERSION=""
RUN if [ -n "$JOBHUNT_VERSION" ]; then \
      printf '{"sha": "%s", "date": "%s"}\n' \
        "$JOBHUNT_VERSION" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > version.json; \
    fi

ENV JOBHUNT_DATA_DIR=/data \
    JOBHUNT_CONTAINER=1
EXPOSE 8765
VOLUME ["/data"]

# --host 0.0.0.0 so the published port is reachable; --no-open since there's no
# browser in the container. cmd_serve auto-creates config/data on first run.
CMD ["python", "jobhunt.py", "serve", "--host", "0.0.0.0", "--no-open"]
