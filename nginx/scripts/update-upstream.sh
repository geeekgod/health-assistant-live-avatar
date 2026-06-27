#!/usr/bin/env bash
# Point nginx at blue or green Docker ports (called automatically after deploy).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
NGINX_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_FILE="$REPO_ROOT/docker/.deploy-color"

COLOR="${1:-}"
if [[ -z "$COLOR" && -f "$STATE_FILE" ]]; then
  COLOR="$(tr -d '[:space:]' < "$STATE_FILE")"
fi
COLOR="${COLOR:-blue}"

log() { printf '[nginx-upstream] %s\n' "$*"; }

case "$COLOR" in
  blue|green) ;;
  *)
    log "Unknown color: $COLOR (use blue or green)"
    exit 1
    ;;
esac

if [[ ! -f "$NGINX_ROOT/upstream/upstream-${COLOR}.conf" ]]; then
  log "Missing upstream template: upstream-${COLOR}.conf"
  exit 1
fi

if [[ ! -d /etc/nginx/mykare ]]; then
  log "nginx not installed — run: sudo bash nginx/scripts/install.sh"
  exit 0
fi

if [[ "$(id -u)" -ne 0 ]]; then
  sudo cp "$NGINX_ROOT/upstream/upstream-${COLOR}.conf" /etc/nginx/mykare/upstream-active.conf
  sudo nginx -t
  sudo systemctl reload nginx
else
  cp "$NGINX_ROOT/upstream/upstream-${COLOR}.conf" /etc/nginx/mykare/upstream-active.conf
  nginx -t
  systemctl reload nginx
fi

log "Active upstream: $COLOR"
