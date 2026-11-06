#!/usr/bin/env bash
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
mkdir -p rbnx-build/tmp rbnx-build/uv-cache
export TMPDIR="$PKG/rbnx-build/tmp"
export UV_CACHE_DIR="$PKG/rbnx-build/uv-cache"
rbnx codegen -p "$PKG" --mcp
if [[ ! -x "$PKG/.venv/bin/python" ]]; then
  uv venv --python 3.10 "$PKG/.venv"
fi
PIP_ARGS=()
if [[ -n "${RBNX_OFFLINE_WHEELS:-}" ]]; then
  PIP_ARGS+=(--offline --find-links "$RBNX_OFFLINE_WHEELS")
fi
uv pip install --python "$PKG/.venv/bin/python" "${PIP_ARGS[@]}" -e "$PKG" -e "$(rbnx path robonix-api)"
