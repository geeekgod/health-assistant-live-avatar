#!/usr/bin/env bash
# Wipe SQLite DB + recordings (shared Docker volumes). Stops blue AND green first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_DIR="$ROOT/docker"
ENV_FILE="$COMPOSE_DIR/.env"
STATE_FILE="$COMPOSE_DIR/.deploy-color"

log() { printf '[reset-db] %s\n' "$*"; }

LIVEKIT="${LIVEKIT:-cloud}"
case "$LIVEKIT" in
  local)  PROFILE="--profile self-hosted" ;;
  cloud)  PROFILE="--profile cloud" ;;
  off)    PROFILE="--profile core" ;;
  *) log "LIVEKIT must be local, cloud, or off"; exit 1 ;;
esac

compose_down() {
  local project="$1"
  COMPOSE_PROJECT_NAME="$project" \
    docker compose \
      -f "$COMPOSE_DIR/compose.yml" \
      -f "$COMPOSE_DIR/compose.deploy.yml" \
      $PROFILE \
      --env-file "$ENV_FILE" \
      down --remove-orphans 2>/dev/null || true
}

log "Stopping health-assistant-blue and health-assistant-green…"
compose_down health-assistant-blue
compose_down health-assistant-green

# Anything still using the volumes?
if docker ps -q --filter volume=health-assistant-app-data | grep -q .; then
  log "ERROR: containers still using health-assistant-app-data:"
  docker ps --filter volume=health-assistant-app-data
  log "Stop them first, then re-run this script."
  exit 1
fi

log "Removing volumes…"
docker volume rm health-assistant-app-data health-assistant-recordings 2>/dev/null || {
  log "WARN: could not remove one or both volumes (still in use?)."
  docker volume ls | grep health-assistant || true
  exit 1
}

log "Creating fresh volumes…"
docker volume create health-assistant-app-data
docker volume create health-assistant-recordings

if [[ "${1:-}" == "--no-deploy" ]]; then
  log "Done (volumes reset). Deploy with: LIVEKIT=${LIVEKIT} bash docker/scripts/deploy.sh"
  exit 0
fi

log "Redeploying…"
LIVEKIT="$LIVEKIT" bash "$ROOT/docker/scripts/deploy.sh"
log "Done. Database and recordings are empty."
