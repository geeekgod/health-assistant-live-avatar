#!/usr/bin/env bash
# Diagnose nginx 502 / SSL / upstream issues.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

STATE_FILE="$REPO_ROOT/docker/.deploy-color"
LIVEKIT_MODE="$(nginx_detect_livekit_mode)"

log() { printf '[doctor] %s\n' "$*"; }
ok() { printf '[doctor] OK  %s\n' "$*"; }
fail() { printf '[doctor] FAIL %s\n' "$*"; }
warn() { printf '[doctor] WARN %s\n' "$*"; }

log "=== mykare nginx doctor (LIVEKIT=${LIVEKIT_MODE}) ==="

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

log "Expected ports — frontend:$FE backend:$BE"

if [[ -f /etc/nginx/mykare/upstream-active.conf ]]; then
  log "upstream-active.conf:"
  sed 's/^/  /' /etc/nginx/mykare/upstream-active.conf
  if grep -q "127.0.0.1:$FE" /etc/nginx/mykare/upstream-active.conf 2>/dev/null; then
    ok "nginx upstream matches deploy color"
  else
    fail "nginx upstream mismatch — run: bash nginx/scripts/update-upstream.sh $COLOR"
  fi
else
  fail "missing /etc/nginx/mykare/upstream-active.conf — run: sudo bash nginx/scripts/install.sh"
fi

check_port() {
  local port="$1" name="$2"
  if curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${port}/" 2>/dev/null \
     || curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${port}/health" 2>/dev/null \
     || curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${port}/health/ready" 2>/dev/null \
     || curl -fsS -o /dev/null -m 3 "http://127.0.0.1:${port}/api/health" 2>/dev/null; then
    ok "$name responds on :$port"
  else
    fail "$name not responding on :$port — run: LIVEKIT=${LIVEKIT_MODE} bash docker/scripts/deploy.sh"
  fi
}

check_port "$FE" "frontend"
check_port "$BE" "backend"

if nginx_livekit_site_enabled; then
  log "Expected livekit port: 7880"
  check_port "7880" "livekit"
elif [[ -L /etc/nginx/sites-enabled/mykare-livekit ]]; then
  warn "mykare-livekit site enabled but LIVEKIT=${LIVEKIT_MODE} — will 502 on :7880"
  warn "Fix: sudo bash nginx/scripts/install.sh"
else
  ok "mykare-livekit site disabled (LiveKit Cloud/off)"
fi

log ""
log "Docker containers:"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null \
  | grep -E 'health-assistant|NAMES' || fail "no health-assistant containers running"

log ""
if nginx_ssl_configured; then
  ok "SSL certificates configured"
  if nginx_env_uses_http; then
    warn "docker/.env still uses http:// API URL"
    warn "Fix: sudo bash nginx/scripts/enable-ssl.sh  # patches .env, then redeploy"
  else
    ok "docker/.env uses HTTPS API URL"
  fi
else
  warn "SSL not configured — HTTP only"
  warn "Fix: sudo bash nginx/scripts/enable-ssl.sh"
fi

log ""
log "Quick fixes:"
log "  1. Deploy:   LIVEKIT=${LIVEKIT_MODE} bash docker/scripts/deploy.sh"
log "  2. Upstream: bash nginx/scripts/update-upstream.sh $COLOR"
log "  3. SSL:      sudo bash nginx/scripts/enable-ssl.sh"
