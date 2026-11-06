#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"
cd "$DEPLOY"
if [[ "${1:-}" == --background ]]; then
  if [[ -f "$RUN_DIR/sensors-stack.pid" ]] && kill -0 "$(cat "$RUN_DIR/sensors-stack.pid")" 2>/dev/null; then
    echo "the read-only sensor deployment is already running" >&2
    exit 1
  fi
  setsid nohup bash "$HERE/start_sensors.sh" > "$LOGS/sensors-stack.log" 2>&1 < /dev/null &
  echo $! > "$RUN_DIR/sensors-stack.pid"
  echo "started in the background, log: $LOGS/sensors-stack.log"
  exit 0
fi
if [[ $# -ne 0 ]]; then
  echo "usage: bash $0 [--background]" >&2
  exit 1
fi
exec rbnx boot -f robonix_manifest.r1-native-sensors.yaml --no-update-check -v
