#!/usr/bin/env bash
# Obtain Let's Encrypt certs and enable HTTPS (run after install.sh + HTTP works).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

log() { printf '[nginx-ssl] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  log "Run with sudo"
  exit 1
fi

LIVEKIT_MODE="$(nginx_detect_livekit_mode)"
DOMAINS=("$DOMAIN_FRONTEND" "$DOMAIN_BACKEND")
if nginx_livekit_site_enabled; then
  DOMAINS+=("$DOMAIN_LIVEKIT")
fi

log "LiveKit mode: ${LIVEKIT_MODE} — cert domains: ${DOMAINS[*]}"

log "Opening firewall (UFW)…"
bash "$SCRIPT_DIR/setup-firewall.sh"

if ! command -v certbot >/dev/null 2>&1; then
  log "Installing certbot…"
  apt-get update
  apt-get install -y certbot python3-certbot-nginx
fi

log "DigitalOcean: Networking → Firewalls → allow TCP 80, 443 inbound"

ARGS=()
for d in "${DOMAINS[@]}"; do
  ARGS+=(-d "$d")
done

log "Requesting certificates…"
if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
  certbot --nginx --non-interactive --agree-tos --redirect \
    -m "$CERTBOT_EMAIL" "${ARGS[@]}"
else
  log "Tip: set CERTBOT_EMAIL=you@example.com for non-interactive certbot"
  certbot --nginx "${ARGS[@]}"
fi

nginx -t
systemctl reload nginx

if nginx_patch_env_https; then
  log "Updated docker/.env with HTTPS API URLs"
else
  log "WARN: docker/.env not found — set manually:"
  log "  NEXT_PUBLIC_API_URL=${HTTPS_API_URL}"
  log "  BACKEND_URL=${HTTPS_API_URL}"
fi

log "SSL enabled. Redeploy to rebuild frontend with HTTPS API URL:"
log "  cd ${REPO_ROOT} && LIVEKIT=${LIVEKIT_MODE} bash docker/scripts/deploy.sh"
