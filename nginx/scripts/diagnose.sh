#!/usr/bin/env bash
# Full stack diagnosis — nginx, SSL, docker, connectivity.
# Run on server: bash nginx/scripts/diagnose.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

STATE_FILE="$REPO_ROOT/docker/.deploy-color"
LIVEKIT_MODE="$(nginx_detect_livekit_mode)"
ISSUES=0

log()  { printf '[diagnose] %s\n' "$*"; }
ok()   { printf '[diagnose] OK   %s\n' "$*"; }
fail() { printf '[diagnose] FAIL %s\n' "$*"; ISSUES=$((ISSUES + 1)); }
warn() { printf '[diagnose] WARN %s\n' "$*"; }

section() {
  echo ""
  log "======== $1 ========"
}

run() {
  # Print command, run it (failures don't stop the script)
  printf '[diagnose] $ %s\n' "$*"
  "$@" 2>&1 | sed 's/^/[diagnose]   /' || true
}

sudo_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    warn "need root for: $*"
    return 1
  fi
}

check_tcp() {
  local port="$1" label="$2"
  if ss -tln 2>/dev/null | grep -q ":${port} " \
     || ss -tln 2>/dev/null | grep -q ":${port}\s"; then
    ok "${label} listening on :${port}"
    return 0
  fi
  fail "${label} NOT listening on :${port}"
  return 1
}

curl_head() {
  local url="$1" label="$2"
  local out code
  out="$(curl -sI -m 8 "$url" 2>&1)" || true
  code="$(printf '%s' "$out" | head -1)"
  if [[ "$code" =~ ^HTTP/[0-9.]+[[:space:]][23] ]]; then
    ok "${label}: ${code}"
    return 0
  fi
  if [[ "$code" =~ Connection\ refused|Failed\ to\ connect|Could\ not\ resolve ]]; then
    fail "${label}: ${code:-connection failed}"
  else
    warn "${label}: ${code:-no response}"
  fi
  return 1
}

# --- main ---

log "mykare full diagnosis — $(date -Is 2>/dev/null || date)"
log "repo: ${REPO_ROOT}  LIVEKIT=${LIVEKIT_MODE}"

# Deploy color / ports
section "Deploy color"
if [[ -f "$STATE_FILE" ]]; then
  COLOR="$(tr -d '[:space:]' < "$STATE_FILE")"
  ok "active color: ${COLOR}"
else
  COLOR="blue"
  fail "missing ${STATE_FILE} — assuming blue"
fi
case "$COLOR" in
  blue)  FE=3000; BE=8000 ;;
  green) FE=3002; BE=8002 ;;
  *)     FE=3000; BE=8000; fail "unknown color: ${COLOR}" ;;
esac
log "expected docker ports — frontend:${FE} backend:${BE}"

# Nginx service
section "Nginx service"
if systemctl is-active --quiet nginx 2>/dev/null; then
  ok "nginx service active"
else
  fail "nginx service NOT running — fix: sudo systemctl start nginx"
  run systemctl status nginx --no-pager -l
fi

if sudo_cmd nginx -t; then
  ok "nginx -t passed"
else
  fail "nginx config invalid — fix: sudo nginx -t && check /etc/nginx/sites-enabled/"
fi

section "Listening ports"
check_tcp 80 "nginx HTTP"
check_tcp 443 "nginx HTTPS"
check_tcp "$FE" "docker frontend"
check_tcp "$BE" "docker backend"

section "Nginx site configs"
if [[ -d /etc/nginx/sites-enabled ]]; then
  run ls -la /etc/nginx/sites-enabled/
else
  fail "/etc/nginx/sites-enabled missing"
fi

if nginx_site_configs_ok; then
  ok "server_name blocks present for frontend + backend"
else
  fail "site configs empty or missing server_name — fix: sudo bash nginx/scripts/install.sh"
  for f in mykare-frontend mykare-backend; do
    if [[ -e "/etc/nginx/sites-enabled/$f" ]]; then
      local_size="$(wc -c <"/etc/nginx/sites-enabled/$f" 2>/dev/null || echo 0)"
      if [[ "$local_size" -lt 20 ]]; then
        fail "/etc/nginx/sites-enabled/$f is empty (${local_size} bytes)"
      fi
    else
      fail "/etc/nginx/sites-enabled/$f missing"
    fi
  done
fi

log "server_name / listen / ssl:"
grep -rh 'server_name\|listen\|ssl_certificate' /etc/nginx/sites-enabled/ 2>/dev/null \
  | sed 's/^[[:space:]]*/[diagnose]   /' || fail "no server blocks in sites-enabled"

section "Upstream"
if [[ -f /etc/nginx/mykare/upstream-active.conf ]]; then
  sed 's/^/[diagnose]   /' /etc/nginx/mykare/upstream-active.conf
  if grep -q "127.0.0.1:${FE}" /etc/nginx/mykare/upstream-active.conf 2>/dev/null; then
    ok "upstream matches deploy color (${COLOR})"
  else
    fail "upstream port mismatch — fix: bash nginx/scripts/update-upstream.sh ${COLOR}"
  fi
else
  fail "missing /etc/nginx/mykare/upstream-active.conf — fix: sudo bash nginx/scripts/install.sh"
fi

section "SSL / certificates"
if nginx_ssl_configured; then
  ok "nginx has HTTPS (:443 + ssl_certificate)"
elif nginx_cert_exists; then
  fail "cert on disk but nginx has no HTTPS — fix: sudo bash nginx/scripts/enable-ssl.sh"
else
  warn "no SSL configured — fix: sudo bash nginx/scripts/enable-ssl.sh"
fi

if command -v certbot >/dev/null 2>&1; then
  run certbot certificates
else
  warn "certbot not installed"
fi

section "Docker"
if command -v docker >/dev/null 2>&1; then
  run docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' \
    | grep -E 'health-assistant|NAMES' || fail "no health-assistant containers"
else
  fail "docker not found"
fi

section "App health (localhost)"
curl_head "http://127.0.0.1:${FE}/api/health" "frontend :${FE}"
curl_head "http://127.0.0.1:${BE}/health/ready" "backend :${BE}"

section "Public URLs"
curl_head "http://${DOMAIN_FRONTEND}/" "HTTP  ${DOMAIN_FRONTEND}"
curl_head "https://${DOMAIN_FRONTEND}/" "HTTPS ${DOMAIN_FRONTEND}"
curl_head "http://${DOMAIN_BACKEND}/health/ready" "HTTP  ${DOMAIN_BACKEND}"
curl_head "https://${DOMAIN_BACKEND}/health/ready" "HTTPS ${DOMAIN_BACKEND}"

section "DNS"
SERVER_IP="$(curl -4 -s --max-time 5 ifconfig.me 2>/dev/null || true)"
log "server public IP: ${SERVER_IP:-unknown}"
for d in "$DOMAIN_FRONTEND" "$DOMAIN_BACKEND"; do
  resolved="$(dig +short "$d" 2>/dev/null | tail -1 || true)"
  if [[ -n "$resolved" && -n "$SERVER_IP" && "$resolved" == "$SERVER_IP" ]]; then
    ok "DNS ${d} → ${resolved}"
  elif [[ -n "$resolved" ]]; then
    warn "DNS ${d} → ${resolved} (server IP: ${SERVER_IP})"
  else
    fail "DNS ${d} not resolving"
  fi
done

section "Firewall (UFW)"
if command -v ufw >/dev/null 2>&1; then
  run ufw status verbose
else
  warn "ufw not installed — check cloud firewall for TCP 80/443"
fi

section "docker/.env API URLs"
if [[ -f "$REPO_ROOT/docker/.env" ]]; then
  grep -E '^NEXT_PUBLIC_API_URL=|^BACKEND_URL=' "$REPO_ROOT/docker/.env" \
    | sed 's/^/[diagnose]   /' || true
  if nginx_ssl_configured && nginx_env_uses_http; then
    fail ".env still http:// but SSL enabled — fix: sudo bash nginx/scripts/enable-ssl.sh && redeploy"
  fi
else
  fail "docker/.env missing"
fi

section "Recent nginx errors"
if [[ -f /var/log/nginx/error.log ]]; then
  run tail -15 /var/log/nginx/error.log
else
  warn "no /var/log/nginx/error.log"
fi
run journalctl -u nginx -n 15 --no-pager

# Summary
section "Summary"
if [[ "$ISSUES" -eq 0 ]]; then
  ok "no critical issues found (${ISSUES} failures)"
else
  fail "${ISSUES} issue(s) found — see FAIL lines above"
  log ""
  log "Common recovery (run on server):"
  log "  sudo systemctl start nginx"
  log "  sudo bash nginx/scripts/install.sh"
  log "  sudo bash nginx/scripts/enable-ssl.sh"
  log "  LIVEKIT=${LIVEKIT_MODE} bash docker/scripts/deploy.sh"
  log "  bash nginx/scripts/update-upstream.sh"
fi

exit "$([[ "$ISSUES" -eq 0 ]] && echo 0 || echo 1)"
