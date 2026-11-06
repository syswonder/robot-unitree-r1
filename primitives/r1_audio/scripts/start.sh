#!/usr/bin/env bash
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[r1_audio] missing $PY; run the package build first" >&2
  exit 1
fi
ROBONIX_API="$(rbnx path robonix-api)"
export PYTHONPATH="$ROBONIX_API:$PKG:$PKG/rbnx-build/codegen/proto_gen:${PYTHONPATH:-}"
export ROBONIX_ATLAS="${ROBONIX_ATLAS:-127.0.0.1:50051}"
export ROBONIX_PROVIDER_BIND_HOST="${ROBONIX_PROVIDER_BIND_HOST:-127.0.0.1}"
export ROBONIX_ADVERTISE_HOST="${ROBONIX_ADVERTISE_HOST:-127.0.0.1}"
echo "[r1_audio] starting read-only audio provider; atlas=$ROBONIX_ATLAS"
exec "$PY" -m r1_audio.main
