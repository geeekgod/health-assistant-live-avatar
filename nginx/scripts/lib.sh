# Shared helpers for nginx scripts. Source only — do not execute.
# shellcheck shell=bash

nginx_repo_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

# cloud | local | off — from LIVEKIT env or docker/.env heuristics
nginx_detect_livekit_mode() {
  local root env_file
  root="$(nginx_repo_root)"
  env_file="$root/docker/.env"

  if [[ -n "${LIVEKIT:-}" ]]; then
    echo "$LIVEKIT"
    return
  fi

  if [[ -f "$env_file" ]]; then
    if grep -qE '^LIVEKIT_INTERNAL_URL=ws://livekit:' "$env_file" 2>/dev/null; then
      echo "local"
      return
    fi
    if grep -qE '^LIVEKIT_URL=.*livekit\.cloud' "$env_file" 2>/dev/null; then
      echo "cloud"
      return
    fi
    if grep -qE '^LIVEKIT_URL=wss://' "$env_file" 2>/dev/null; then
      echo "cloud"
      return
    fi
  fi

  echo "cloud"
}

nginx_livekit_site_enabled() {
  [[ "$(nginx_detect_livekit_mode)" == "local" ]]
}

DOMAIN_FRONTEND="mykare.geeekgod.in"
DOMAIN_BACKEND="mykare.backend.geeekgod.in"
DOMAIN_LIVEKIT="mykare.livekit.geeekgod.in"
HTTPS_API_URL="https://${DOMAIN_BACKEND}"

nginx_patch_env_https() {
  local root env_file
  root="$(nginx_repo_root)"
  env_file="$root/docker/.env"

  if [[ ! -f "$env_file" ]]; then
    return 1
  fi

  if grep -q '^NEXT_PUBLIC_API_URL=' "$env_file"; then
    sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=${HTTPS_API_URL}|" "$env_file"
  else
    echo "NEXT_PUBLIC_API_URL=${HTTPS_API_URL}" >>"$env_file"
  fi

  if grep -q '^BACKEND_URL=' "$env_file"; then
    sed -i "s|^BACKEND_URL=.*|BACKEND_URL=${HTTPS_API_URL}|" "$env_file"
  else
    echo "BACKEND_URL=${HTTPS_API_URL}" >>"$env_file"
  fi
}

nginx_ssl_configured() {
  grep -rq 'listen .*443' /etc/nginx/sites-enabled/ 2>/dev/null \
    && grep -rq 'ssl_certificate' /etc/nginx/sites-enabled/ 2>/dev/null
}

nginx_cert_exists() {
  [[ -d "/etc/letsencrypt/live/${DOMAIN_FRONTEND}" ]] \
    || certbot certificates 2>/dev/null | grep -q "Certificate Name: ${DOMAIN_FRONTEND}"
}

nginx_site_configs_ok() {
  grep -rq "server_name ${DOMAIN_FRONTEND}" /etc/nginx/sites-enabled/ 2>/dev/null \
    && grep -rq "server_name ${DOMAIN_BACKEND}" /etc/nginx/sites-enabled/ 2>/dev/null
}

nginx_env_uses_http() {
  local root env_file
  root="$(nginx_repo_root)"
  env_file="$root/docker/.env"
  [[ -f "$env_file" ]] && grep -qE '^NEXT_PUBLIC_API_URL=http://' "$env_file"
}

nginx_port_listening() {
  local port="$1"
  ss -tln 2>/dev/null | grep -qE ":${port}[[:space:]]"
}

nginx_reload_or_restart() {
  nginx -t
  if nginx_port_listening 80 || nginx_port_listening 443; then
    systemctl reload nginx
  else
    systemctl restart nginx
  fi
  if ! nginx_port_listening 80 && ! nginx_port_listening 443; then
    return 1
  fi
}
