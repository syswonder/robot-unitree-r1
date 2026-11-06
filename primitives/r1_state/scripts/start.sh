#!/usr/bin/env bash
# Start the read-only R1 state primitive. The deployment manifest supplies
# the DDS interface: enp131s0 on the PC, eth10 on the R1 itself.
set -euo pipefail

PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[r1_state] missing $PY; run the package build first" >&2
  exit 1
fi

ROBONIX_API="$(rbnx path robonix-api)"
export PYTHONPATH="$ROBONIX_API:$PKG:$PKG/rbnx-build/codegen/proto_gen:$PKG/rbnx-build/codegen/robonix_mcp_types:${PYTHONPATH:-}"
export ROBONIX_ATLAS="${ROBONIX_ATLAS:-127.0.0.1:50051}"
# Keep the provider control plane local to this host.
export ROBONIX_PROVIDER_BIND_HOST="${ROBONIX_PROVIDER_BIND_HOST:-127.0.0.1}"
export ROBONIX_ADVERTISE_HOST="${ROBONIX_ADVERTISE_HOST:-127.0.0.1}"

echo "[r1_state] starting read-only provider; atlas=$ROBONIX_ATLAS"
exec "$PY" -m r1_state.main
