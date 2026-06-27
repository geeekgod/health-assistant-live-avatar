#!/bin/sh
set -e

if [ "$(id -u)" = "0" ]; then
  mkdir -p /data/recordings
  chown -R appuser:appuser /data
  exec gosu appuser "$@"
fi

exec "$@"
