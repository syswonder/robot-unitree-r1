#!/usr/bin/env bash
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
rbnx codegen -p "$PKG"
PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  uv venv --python 3.10 "$PKG/.venv"
fi
PIP_ARGS=()
WHEELS="${RBNX_OFFLINE_WHEELS:-}"
if [[ -n "$WHEELS" ]]; then
  PIP_ARGS+=(--offline --find-links "$WHEELS")
fi
uv pip install --python "$PY" "${PIP_ARGS[@]}" -e "$(rbnx path robonix-api)" setuptools wheel
if [[ -n "$WHEELS" ]]; then
  CDDS_PREFIX="$PKG/.cyclonedds-prefix"
  mkdir -p "$CDDS_PREFIX/bin" "$CDDS_PREFIX/lib"
  ln -sfn /usr/local/include "$CDDS_PREFIX/include"
  ln -sf /usr/local/lib/libddsc.so "$CDDS_PREFIX/lib/libddsc.so"
  ln -sf /usr/local/lib/libddsc.so.0 "$CDDS_PREFIX/lib/libddsc.so.0"
  CC=gcc CXX=g++ CYCLONEDDS_HOME="$CDDS_PREFIX" \
    uv pip install --python "$PY" "${PIP_ARGS[@]}" --no-build-isolation "$WHEELS/cyclonedds-0.10.2.tar.gz"
else
  uv pip install --python "$PY" cyclonedds==0.10.2
fi
uv pip install --python "$PY" "${PIP_ARGS[@]}" --no-deps -e "$PKG/../../third_party/unitree_sdk2_python"
