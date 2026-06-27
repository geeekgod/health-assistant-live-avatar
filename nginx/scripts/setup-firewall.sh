#!/usr/bin/env bash
# Open ports required for nginx + certbot + SSH.
set -euo pipefail

log() { printf '[firewall] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  log "Run with sudo"
  exit 1
fi

if ! command -v ufw >/dev/null 2>&1; then
  log "ufw not installed — configure your cloud provider firewall for ports 22, 80, 443"
  exit 0
fi

ufw allow OpenSSH
ufw allow 'Nginx Full'
# LiveKit self-hosted (optional — only if LIVEKIT=local)
ufw allow 7880/tcp comment 'LiveKit HTTP/WS' || true
ufw allow 7881/tcp comment 'LiveKit RTC TCP' || true
ufw allow 50000:60000/udp comment 'LiveKit WebRTC UDP' || true

if ufw status | grep -q 'Status: inactive'; then
  log "Enabling ufw…"
  ufw --force enable
fi

ufw status verbose

log "Done. Also check your cloud provider firewall (DigitalOcean → Networking → Firewalls)"
log "  Allow inbound: TCP 22, 80, 443 from 0.0.0.0/0"
log "Test from your laptop: curl -I http://mykare.backend.geeekgod.in/health"
