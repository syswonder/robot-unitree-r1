#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"
cd "$DEPLOY"
rbnx shutdown -f robonix_manifest.r1-native-sensors.yaml
if [[ -f "$RUN_DIR/sensors-stack.pid" ]]; then
  pid="$(cat "$RUN_DIR/sensors-stack.pid")"
  if ps -p "$pid" -o args= | grep -qF 'rbnx boot -f robonix_manifest.r1-native-sensors.yaml'; then
    kill "$pid"
  fi
  rm -f "$RUN_DIR/sensors-stack.pid"
fi
