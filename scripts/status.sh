#!/usr/bin/env bash
# Quick health check for the R1 native deployment.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"

echo "== web ui"
echo "R1 browser:   http://127.0.0.1:7860/"
echo "Remote browser: http://127.0.0.1:7860/ after forwarding port 7860 from the R1"

echo "== sensor links"
if timeout 2 bash -c '</dev/tcp/192.168.123.161/5000' 2>/dev/null; then
  echo "depth server 192.168.123.161:5000: open"
else
  echo "depth server 192.168.123.161:5000: CLOSED"
  echo "  -> enable Stereo patch PC1 in the Unitree App (keep video_hub off)"
fi
if [[ -e /dev/video-dep ]]; then
  echo "depth device: /dev/video-dep present"
else
  echo "depth device: /dev/video-dep MISSING"
fi
if pgrep -f '[/]watch_robot_reboot.py --interface eth10' >/dev/null 2>&1; then
  echo "robot reboot watch: running"
else
  echo "robot reboot watch: not running"
fi

echo "== providers"
rbnx caps 2>&1 | head -20 || true

echo "== perception"
curl -sS --max-time 5 "http://127.0.0.1:7860/api/perception/status?atlas=127.0.0.1:50051" 2>/dev/null || echo "web client not ready"

echo
echo "== map"
curl -sS --max-time 5 "http://127.0.0.1:50107/api/health" 2>/dev/null || echo "map service not ready"
echo
curl -sS --max-time 5 "http://127.0.0.1:50107/api/pose" 2>/dev/null || true

echo
echo "== logs"
tail -n 3 "$LOGS/stack.log" 2>/dev/null || true
tail -n 3 "$LOGS/depth-client.log" 2>/dev/null || true
tail -n 3 "$LOGS/map-service.log" 2>/dev/null || true
