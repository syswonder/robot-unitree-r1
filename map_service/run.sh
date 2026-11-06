#!/usr/bin/env bash
# Run the R1 local depth map + RGB-D odometry service.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec /usr/bin/python3 "$HERE/map_service.py" \
  --config "$HERE/../config/camera_calibration.json" \
  --listen 127.0.0.1 --port 50107
