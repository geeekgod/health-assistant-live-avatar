#!/usr/bin/env bash
# One-shot recovery when site is down: restore nginx configs, SSL, restart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

log() { printf '[repair] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  log "Run with sudo"
  exit 1
fi

LIVEKIT_MODE="$(nginx_detect_livekit_mode)"
log "Repairing mykare nginx (LIVEKIT=${LIVEKIT_MODE})…"

cd "$REPO_ROOT"

log "Step 1/3: restore nginx site configs + upstream"
bash "$SCRIPT_DIR/install.sh"

log "Step 2/3: install SSL certificate into nginx"
if nginx_ssl_configured; then
  log "HTTPS already in nginx config"
elif nginx_cert_exists; then
  CERTBOT_ARGS=(install --cert-name "$DOMAIN_FRONTEND" --nginx --redirect)
  if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
    CERTBOT_ARGS+=(--non-interactive)
  fi
  certbot "${CERTBOT_ARGS[@]}"
else
  bash "$SCRIPT_DIR/enable-ssl.sh"
fi

nginx_patch_env_https || true

log "Step 3/3: restart nginx"
nginx -t
systemctl restart nginx

if ! nginx_port_listening 80 && ! nginx_port_listening 443; then
  log "ERROR: nginx still not listening"
  journalctl -u nginx -n 30 --no-pager
  exit 1
fi

log "Verify:"
curl -sI "http://${DOMAIN_FRONTEND}/" | head -1 || true
curl -sI "https://${DOMAIN_FRONTEND}/" | head -1 || true
curl -sI "https://${DOMAIN_BACKEND}/health/ready" | head -1 || true

log "Done. If apps 502, run: LIVEKIT=${LIVEKIT_MODE} bash docker/scripts/deploy.sh"
