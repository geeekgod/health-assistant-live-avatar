#!/usr/bin/env bash
# Alias for diagnose.sh (kept for backwards compatibility).
exec "$(cd "$(dirname "$0")" && pwd)/diagnose.sh" "$@"
