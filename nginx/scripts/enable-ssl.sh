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

log "Ensuring nginx site configs from repo…"
bash "$SCRIPT_DIR/install.sh"

if ! nginx_site_configs_ok; then
  log "ERROR: nginx sites missing server_name blocks."
  log "Check: ls -la /etc/nginx/sites-enabled/ && cat /etc/nginx/sites-enabled/mykare-frontend"
  exit 1
fi
log "nginx site configs OK"

log "Opening firewall (UFW)…"
bash "$SCRIPT_DIR/setup-firewall.sh"

if ! command -v certbot >/dev/null 2>&1; then
  log "Installing certbot…"
  apt-get update
  apt-get install -y certbot python3-certbot-nginx
fi

log "DigitalOcean: Networking → Firewalls → allow TCP 80, 443 inbound"

CERTBOT_COMMON=(--nginx --redirect)
if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
  CERTBOT_COMMON+=(--non-interactive --agree-tos -m "$CERTBOT_EMAIL")
fi

ARGS=()
for d in "${DOMAINS[@]}"; do
  ARGS+=(-d "$d")
done

if nginx_ssl_configured; then
  log "HTTPS already configured in nginx"
elif nginx_cert_exists; then
  log "Certificate on disk — installing into nginx…"
  certbot install --cert-name "$DOMAIN_FRONTEND" "${CERTBOT_COMMON[@]}"
else
  log "Requesting certificates…"
  if [[ -n "${CERTBOT_EMAIL:-}" ]]; then
    certbot --nginx --non-interactive --agree-tos --redirect \
      -m "$CERTBOT_EMAIL" "${ARGS[@]}"
  else
    log "Tip: set CERTBOT_EMAIL=you@example.com for non-interactive certbot"
    certbot --nginx "${ARGS[@]}"
  fi
fi

if ! nginx_ssl_configured; then
  log "WARN: cert may exist but nginx still has no :443 — retrying install…"
  certbot install --cert-name "$DOMAIN_FRONTEND" "${CERTBOT_COMMON[@]}" || true
fi

if ! nginx_ssl_configured; then
  log "ERROR: SSL install failed. After fixing nginx configs, run:"
  log "  sudo certbot install --cert-name ${DOMAIN_FRONTEND} --nginx --redirect"
  exit 1
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

log "SSL enabled. Verify:"
log "  curl -I https://${DOMAIN_FRONTEND}/"
log "  curl -I https://${DOMAIN_BACKEND}/health/ready"
log "Redeploy to rebuild frontend:"
log "  cd ${REPO_ROOT} && LIVEKIT=${LIVEKIT_MODE} bash docker/scripts/deploy.sh"
