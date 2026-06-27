#!/usr/bin/env bash
# Start a singleton autoheal container that restarts unhealthy labelled services.
set -euo pipefail

CONTAINER_NAME="${AUTOHEAL_CONTAINER_NAME:-health-assistant-autoheal}"
IMAGE="${AUTOHEAL_IMAGE:-willfarrell/autoheal:1.2.0}"

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "[autoheal] $CONTAINER_NAME already running"
  exit 0
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "[autoheal] starting existing $CONTAINER_NAME"
  docker start "$CONTAINER_NAME"
  exit 0
fi

echo "[autoheal] creating $CONTAINER_NAME"
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart=always \
  -e AUTOHEAL_CONTAINER_LABEL=autoheal \
  -e AUTOHEAL_INTERVAL=10 \
  -e AUTOHEAL_START_PERIOD=60 \
  -e AUTOHEAL_DEFAULT_STOP_TIMEOUT=10 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  "$IMAGE"
