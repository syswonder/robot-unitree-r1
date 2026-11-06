#!/usr/bin/env bash
# Build the read-only R1 depth snapshot primitive.
set -euo pipefail

PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

FLAGS=(--mcp)
[[ "${RBNX_BUILD_CLEAN:-}" == "1" ]] && FLAGS+=(--clean)
echo "[r1_depth/build] rbnx codegen ${FLAGS[*]}"
rbnx codegen -p "$PKG" "${FLAGS[@]}"

PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[r1_depth/build] creating Python 3.10 venv"
  uv venv --python 3.10 "$PKG/.venv"
fi

ROBONIX_API="$(rbnx path robonix-api)"
PIP_ARGS=()
WHEELS="${RBNX_OFFLINE_WHEELS:-}"
if [[ -n "$WHEELS" ]]; then
  echo "[r1_depth/build] offline wheels: $WHEELS"
  PIP_ARGS+=(--offline --find-links "$WHEELS")
fi

echo "[r1_depth/build] installing robonix-api from $ROBONIX_API"
uv pip install --python "$PY" "${PIP_ARGS[@]}" -e "$ROBONIX_API"

echo "[r1_depth/build] installing build helpers and numpy"
uv pip install --python "$PY" "${PIP_ARGS[@]}" setuptools wheel numpy
uv pip install --python "$PY" "${PIP_ARGS[@]}" pillow==11.3.0
uv pip install --python "$PY" "${PIP_ARGS[@]}" -e "$PKG/../../common/r1_sensor_geometry"

echo "[r1_depth/build] done"
