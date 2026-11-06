#!/usr/bin/env bash
# Start the read-only R1 depth snapshot primitive. The depth frames must be
# produced by the Unitree depth client into /dev/video-dep first.
set -euo pipefail

PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[r1_depth] missing $PY; run the package build first" >&2
  exit 1
fi

ROBONIX_API="$(rbnx path robonix-api)"
export PYTHONPATH="$ROBONIX_API:$PKG:$PKG/rbnx-build/codegen/proto_gen:$PKG/rbnx-build/codegen/robonix_mcp_types:${PYTHONPATH:-}"
export ROBONIX_ATLAS="${ROBONIX_ATLAS:-127.0.0.1:50051}"
export ROBONIX_PROVIDER_BIND_HOST="${ROBONIX_PROVIDER_BIND_HOST:-127.0.0.1}"
export ROBONIX_ADVERTISE_HOST="${ROBONIX_ADVERTISE_HOST:-127.0.0.1}"

echo "[r1_depth] starting read-only depth provider; atlas=$ROBONIX_ATLAS"
exec "$PY" -m r1_depth.main
