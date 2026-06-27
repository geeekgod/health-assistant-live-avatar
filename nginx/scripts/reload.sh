#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  sudo nginx -t
  sudo systemctl reload nginx
else
  nginx -t
  systemctl reload nginx
fi

echo "[nginx] reloaded"
