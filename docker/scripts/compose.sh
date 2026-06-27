#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_DIR="$ROOT/docker"
COMPOSE_FILE="$COMPOSE_DIR/compose.yml"
ENV_FILE="$COMPOSE_DIR/.env"

LIVEKIT="${LIVEKIT:-local}"
DETACH="${DETACH:-}"

case "$LIVEKIT" in
  local)  PROFILES="--profile self-hosted" ;;
  cloud)  PROFILES="--profile cloud" ;;
  off)    PROFILES="--profile core" ;;
  *)
    echo "LIVEKIT must be local, cloud, or off (got: $LIVEKIT)" >&2
    exit 1
    ;;
esac

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$COMPOSE_DIR/.env.example" "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example"
fi

compose() {
  docker compose -f "$COMPOSE_FILE" $PROFILES --env-file "$ENV_FILE" "$@"
}

case "${1:-}" in
  build)
    compose build "${@:2}"
    ;;
  up)
    if [[ "$DETACH" == "1" ]]; then
      compose up -d "${@:2}"
    else
      compose up "${@:2}"
    fi
    ;;
  down)
    compose down "${@:2}"
    ;;
  logs)
    compose logs -f "${@:2}"
    ;;
  ps)
    compose ps "${@:2}"
    ;;
  *)
    echo "Usage: LIVEKIT=local|cloud|off DETACH=0|1 $0 {build|up|down|logs|ps}" >&2
    exit 1
    ;;
esac
