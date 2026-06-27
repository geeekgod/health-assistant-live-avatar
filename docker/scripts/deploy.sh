#!/usr/bin/env bash
# Blue-green Docker deploy for production.
# Builds the inactive stack, health-checks it, tears down the old stack, flips color.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_DIR="$ROOT/docker"
COMPOSE_FILE="$COMPOSE_DIR/compose.yml"
COMPOSE_DEPLOY="$COMPOSE_DIR/compose.deploy.yml"
ENV_FILE="$COMPOSE_DIR/.env"
STATE_FILE="$COMPOSE_DIR/.deploy-color"

LIVEKIT="${LIVEKIT:-cloud}"
GIT_REF="${GIT_REF:-main}"
HEALTH_RETRIES="${HEALTH_RETRIES:-30}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-5}"

log() { printf '[deploy] %s\n' "$*"; }

ensure_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    log "ERROR: $ENV_FILE missing. Copy docker/.env.example and configure secrets on the server."
    exit 1
  fi
}

livekit_profile() {
  case "$LIVEKIT" in
    local)  echo "--profile self-hosted" ;;
    cloud)  echo "--profile cloud" ;;
    off)    echo "--profile core" ;;
    *) log "LIVEKIT must be local, cloud, or off"; exit 1 ;;
  esac
}

ports_for_color() {
  case "$1" in
    blue)  FRONTEND_PORT=3000; BACKEND_PORT=8000 ;;
    green) FRONTEND_PORT=3002; BACKEND_PORT=8002 ;;
    *) log "Unknown color: $1"; exit 1 ;;
  esac
  export FRONTEND_PORT BACKEND_PORT
}

compose_cmd() {
  local project="$1"
  shift
  # shellcheck disable=SC2046
  COMPOSE_PROJECT_NAME="$project" \
    docker compose \
      -f "$COMPOSE_FILE" \
      -f "$COMPOSE_DEPLOY" \
      $(livekit_profile) \
      --env-file "$ENV_FILE" \
      "$@"
}

wait_for_backend() {
  local port="$1"
  local i=1
  while [[ "$i" -le "$HEALTH_RETRIES" ]]; do
    if curl -fsS "http://127.0.0.1:${port}/health/ready" >/dev/null 2>&1; then
      log "Backend healthy on port ${port}"
      return 0
    fi
    log "Waiting for backend :${port} (${i}/${HEALTH_RETRIES})…"
    sleep "$HEALTH_INTERVAL"
    i=$((i + 1))
  done
  log "ERROR: Backend failed health check on port ${port}"
  return 1
}

reload_nginx_if_configured() {
  if command -v nginx >/dev/null 2>&1 && [[ -f /etc/nginx/nginx.conf ]]; then
    log "Reloading nginx…"
    if sudo nginx -t 2>/dev/null; then
      sudo systemctl reload nginx
      log "nginx reloaded"
    else
      log "WARN: nginx config test failed — skipping reload"
    fi
  else
    log "nginx not configured — skip reload (wire upstream when ready)"
  fi
}

current_color() {
  if [[ -f "$STATE_FILE" ]]; then
    tr -d '[:space:]' < "$STATE_FILE"
  else
    echo "blue"
  fi
}

next_color() {
  if [[ "$(current_color)" == "blue" ]]; then
    echo "green"
  else
    echo "blue"
  fi
}

main() {
  ensure_env

  local current next
  current="$(current_color)"
  next="$(next_color)"

  log "Active stack: ${current} → deploying: ${next} (LIVEKIT=${LIVEKIT})"

  docker volume create health-assistant-app-data >/dev/null 2>&1 || true
  docker volume create health-assistant-recordings >/dev/null 2>&1 || true

  ports_for_color "$next"
  local next_project="health-assistant-${next}"

  log "Building ${next_project}…"
  compose_cmd "$next_project" build

  log "Starting ${next_project} (frontend :${FRONTEND_PORT}, backend :${BACKEND_PORT})…"
  compose_cmd "$next_project" up -d --remove-orphans

  wait_for_backend "$BACKEND_PORT"

  if [[ "$current" != "$next" ]]; then
    local current_project="health-assistant-${current}"
    ports_for_color "$current"
    log "Stopping previous stack ${current_project}…"
    compose_cmd "$current_project" down --remove-orphans || true
  fi

  echo "$next" > "$STATE_FILE"
  log "Deploy complete. Active color: ${next}"

  bash "$ROOT/docker/scripts/autoheal.sh"
  reload_nginx_if_configured
}

main "$@"
