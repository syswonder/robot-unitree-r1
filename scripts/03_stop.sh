#!/usr/bin/env bash
# Section 6 one-shot stop: web client, map service, Robonix stack, depth client.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"

stop_pidfile() {
  local name="$1" pidfile="$2"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "[stop] $name (pid $pid)"
    fi
    rm -f "$pidfile"
  fi
}

stop_pidfile "robot reboot watcher" "$RUN_DIR/robot-reboot-watch.pid"
stop_pidfile "web client" "$RUN_DIR/web-client.pid"
pids="$(pgrep -f '^/.*/robonix-client/.venv/bin/python .*robonix-client --robot-host 127.0.0.1' || true)"
[[ -n "$pids" ]] && kill $pids 2>/dev/null || true

stop_pidfile "map service" "$RUN_DIR/map-service.pid"
pids="$(pgrep -f 'map_service\.py --config' || true)"
[[ -n "$pids" ]] && kill $pids 2>/dev/null || true

if command -v rbnx >/dev/null 2>&1; then
  (
    cd "$DEPLOY"
    rbnx shutdown -f robonix_manifest.r1-native.yaml >/dev/null 2>&1 || true
  )
  echo "[stop] Robonix stack"
fi
stop_pidfile "stack" "$RUN_DIR/stack.pid"

stop_pidfile "depth client" "$RUN_DIR/depth-client.pid"
pids="$(pgrep -f 'depth_client/client 192.168.123.161' || true)"
[[ -n "$pids" ]] && kill $pids 2>/dev/null || true

echo "[stop] done"
