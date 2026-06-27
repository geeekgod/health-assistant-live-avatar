#!/usr/bin/env bash
# Diagnose nginx 502 — checks docker, ports, and upstream alignment.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STATE_FILE="$REPO_ROOT/docker/.deploy-color"

log() { printf '[doctor] %s\n' "$*"; }
ok() { printf '[doctor] OK  %s\n' "$*"; }
fail() { printf '[doctor] FAIL %s\n' "$*"; }

log "=== mykare nginx doctor ==="

# Active deploy color
if [[ -f "$STATE_FILE" ]]; then
  COLOR="$(tr -d '[:space:]' < "$STATE_FILE")"
  ok "deploy color: $COLOR"
else
  COLOR="blue"
  fail "no $STATE_FILE — assuming blue (ports 3000/8000)"
fi

case "$COLOR" in
  blue)  FE=3000; BE=8000 ;;
  green) FE=3002; BE=8002 ;;
  *) fail "unknown color: $COLOR"; FE=3000; BE=8000 ;;
esac

log "Expected ports — frontend:$FE backend:$BE livekit:7880"

# Upstream file
if [[ -f /etc/nginx/mykare/upstream-active.conf ]]; then
  log "upstream-active.conf:"
  sed 's/^/  /' /etc/nginx/mykare/upstream-active.conf
  if grep -q "127.0.0.1:$FE" /etc/nginx/mykare/upstream-active.conf 2>/dev/null; then
    ok "nginx upstream matches deploy color"
  else
    fail "nginx upstream does NOT match deploy color — run: bash nginx/scripts/update-upstream.sh $COLOR"
  fi
else
  fail "missing /etc/nginx/mykare/upstream-active.conf — run: sudo bash nginx/scripts/install.sh"
fi

# Port checks
check_port() {
  local port="$1" name="$2"
  if curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${port}/" 2>/dev/null \
     || curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${port}/health" 2>/dev/null \
     || curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${port}/health/ready" 2>/dev/null; then
    ok "$name responds on :$port"
  else
    fail "$name not responding on :$port — is docker running?"
  fi
}

check_port "$FE" "frontend"
check_port "$BE" "backend"
check_port "7880" "livekit"

log ""
log "Docker containers (health-assistant):"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | grep -E 'health-assistant|NAMES' || fail "no health-assistant containers running"

if [[ -f "$REPO_ROOT/docker/.env" ]]; then
  LIVEKIT_MODE="$(grep -E '^LIVEKIT_URL=' "$REPO_ROOT/docker/.env" | head -1 || true)"
  log "env: $LIVEKIT_MODE"
  if grep -q 'livekit.cloud' "$REPO_ROOT/docker/.env" 2>/dev/null; then
    log "NOTE: LiveKit Cloud in use — mykare.livekit.geeekgod.in will 502 unless LIVEKIT=local"
    log "      Fix: sudo rm /etc/nginx/sites-enabled/mykare-livekit && sudo nginx -t && sudo systemctl reload nginx"
  fi
fi

log ""
log "Quick fixes:"
log "  1. Start stack:  cd $REPO_ROOT && LIVEKIT=cloud bash docker/scripts/deploy.sh"
log "  2. Sync upstream: bash nginx/scripts/update-upstream.sh $COLOR"
log "  3. Reload nginx: sudo bash nginx/scripts/reload.sh"
