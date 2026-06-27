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
  local src="$NGINX_ROOT/sites-available/$site"
  local dst="/etc/nginx/sites-available/$site"

  if [[ ! -s "$src" ]]; then
    log "ERROR: repo config empty or missing: $src"
    log "Run: cd $REPO_ROOT && git pull"
    exit 1
  fi

  cp "$src" "$dst"
  ln -sf "$dst" "/etc/nginx/sites-enabled/$site"

  if [[ ! -s "$dst" ]]; then
    log "ERROR: $dst is still empty after copy"
    exit 1
  fi
  log "Installed $site ($(wc -c <"$dst") bytes)"
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

if ! nginx_reload_or_restart; then
  log "ERROR: nginx not listening on :80 or :443 after restart"
  journalctl -u nginx -n 20 --no-pager
  exit 1
fi

log "Done. nginx listening:"
ss -tlnp | grep -E ':80|:443' || true
log "Test: curl -I http://${DOMAIN_BACKEND}/health/ready"
log "Then SSL: sudo bash nginx/scripts/enable-ssl.sh"
