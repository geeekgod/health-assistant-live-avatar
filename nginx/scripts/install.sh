#!/usr/bin/env bash
# Install mykare nginx configs (HTTP first — run enable-ssl.sh after HTTP works).
set -euo pipefail

NGINX_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

COLOR="${1:-}"
if [[ -z "$COLOR" && -f "$REPO_ROOT/docker/.deploy-color" ]]; then
  COLOR="$(tr -d '[:space:]' < "$REPO_ROOT/docker/.deploy-color")"
fi
COLOR="${COLOR:-blue}"

LIVEKIT_MODE="$(nginx_detect_livekit_mode)"

log() { printf '[nginx-install] %s\n' "$*"; }

if [[ "$COLOR" != "blue" && "$COLOR" != "green" ]]; then
  log "Usage: sudo bash nginx/scripts/install.sh [blue|green]"
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  log "Run with sudo"
  exit 1
fi

install_site() {
  local site="$1"
  cp "$NGINX_ROOT/sites-available/$site" "/etc/nginx/sites-available/$site"
  ln -sf "/etc/nginx/sites-available/$site" "/etc/nginx/sites-enabled/$site"
}

log "Installing snippets and upstream ($COLOR)…"
mkdir -p /etc/nginx/mykare
cp "$NGINX_ROOT/snippets/mykare-websocket.conf" /etc/nginx/conf.d/mykare-websocket.conf
cp "$NGINX_ROOT/upstream/upstream-${COLOR}.conf" /etc/nginx/mykare/upstream-active.conf

log "Installing sites (LIVEKIT=${LIVEKIT_MODE})…"
for site in mykare-frontend mykare-backend; do
  install_site "$site"
done

if nginx_livekit_site_enabled; then
  install_site mykare-livekit
  log "Enabled mykare-livekit (self-hosted LiveKit on :7880)"
else
  rm -f /etc/nginx/sites-enabled/mykare-livekit
  log "Skipped mykare-livekit (LIVEKIT=${LIVEKIT_MODE} — no local :7880)"
fi

rm -f /etc/nginx/sites-enabled/default

cat > /etc/nginx/conf.d/mykare-upstream.conf <<'EOF'
include /etc/nginx/mykare/upstream-active.conf;
EOF

nginx -t
systemctl reload nginx
log "Done. Test: curl -I http://${DOMAIN_BACKEND}/health/ready"
log "Then SSL: sudo bash nginx/scripts/enable-ssl.sh"
