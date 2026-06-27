#!/usr/bin/env bash
# Obtain Let's Encrypt certs and enable HTTPS (run after install.sh + HTTP works).
set -euo pipefail

DOMAINS=(
  mykare.geeekgod.in
  mykare.backend.geeekgod.in
  mykare.livekit.geeekgod.in
)

log() { printf '[nginx-ssl] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  log "Run with sudo"
  exit 1
fi

if ! command -v certbot >/dev/null 2>&1; then
  log "Installing certbot…"
  apt-get update
  apt-get install -y certbot python3-certbot-nginx
fi

log "Ensure ports 80/443 are open: sudo bash nginx/scripts/setup-firewall.sh"
log "DigitalOcean: Networking → Firewalls → allow TCP 80, 443 inbound"

ARGS=()
for d in "${DOMAINS[@]}"; do
  ARGS+=(-d "$d")
done

log "Requesting certificates for: ${DOMAINS[*]}"
certbot --nginx "${ARGS[@]}"

nginx -t
systemctl reload nginx
log "SSL enabled. Update docker/.env:"
log "  NEXT_PUBLIC_API_URL=https://mykare.backend.geeekgod.in"
log "  BACKEND_URL=https://mykare.backend.geeekgod.in"
log "Then redeploy to rebuild frontend with HTTPS API URL."
