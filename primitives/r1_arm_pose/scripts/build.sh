#!/usr/bin/env bash
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
rbnx codegen -p "$PKG" --mcp
PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  uv venv --python 3.10 "$PKG/.venv"
fi
PIP_ARGS=()
if [[ -n "${RBNX_OFFLINE_WHEELS:-}" ]]; then
  PIP_ARGS+=(--offline --find-links "$RBNX_OFFLINE_WHEELS")
fi
uv pip install --python "$PY" "${PIP_ARGS[@]}" -e "$(rbnx path robonix-api)" \
  ikpy==3.4.2 scipy==1.15.3 numpy==2.2.6
