#!/usr/bin/env bash
# Install mykare nginx configs (HTTP first — run enable-ssl.sh after).
set -euo pipefail

NGINX_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COLOR="${1:-blue}"

log() { printf '[nginx-install] %s\n' "$*"; }

if [[ "$COLOR" != "blue" && "$COLOR" != "green" ]]; then
  log "Usage: sudo bash nginx/scripts/install.sh [blue|green]"
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  log "Run with sudo"
  exit 1
fi

log "Installing snippets and upstream ($COLOR)…"
mkdir -p /etc/nginx/mykare
cp "$NGINX_ROOT/snippets/mykare-websocket.conf" /etc/nginx/conf.d/mykare-websocket.conf
cp "$NGINX_ROOT/upstream/upstream-${COLOR}.conf" /etc/nginx/mykare/upstream-active.conf

log "Installing sites-available…"
for site in mykare-frontend mykare-backend mykare-livekit; do
  cp "$NGINX_ROOT/sites-available/$site" "/etc/nginx/sites-available/$site"
  ln -sf "/etc/nginx/sites-available/$site" "/etc/nginx/sites-enabled/$site"
done

rm -f /etc/nginx/sites-enabled/default

if ! grep -q 'mykare/upstream-active.conf' /etc/nginx/nginx.conf 2>/dev/null; then
  if grep -q 'include /etc/nginx/conf.d/\*\.conf;' /etc/nginx/nginx.conf; then
  log "Upstream loaded via /etc/nginx/mykare/upstream-active.conf"
  log "Add this line inside http {} in /etc/nginx/nginx.conf if upstreams fail:"
  log "    include /etc/nginx/mykare/upstream-active.conf;"
  else
    log "WARN: Add inside http {} in /etc/nginx/nginx.conf:"
    log "    include /etc/nginx/mykare/upstream-active.conf;"
  fi
fi

# Ensure upstream include exists (idempotent drop-in)
cat > /etc/nginx/conf.d/mykare-upstream.conf <<'EOF'
include /etc/nginx/mykare/upstream-active.conf;
EOF

nginx -t
systemctl reload nginx
log "Done. Test: curl -I http://mykare.backend.geeekgod.in/health"
log "Then SSL: sudo bash nginx/scripts/enable-ssl.sh"
