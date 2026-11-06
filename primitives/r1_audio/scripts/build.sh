#!/usr/bin/env bash
# Build the R1 audio primitive: codegen + local Python 3.10 venv.
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
FLAGS=()
rbnx codegen -p "$PKG" "${FLAGS[@]}"
PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[r1_audio/build] creating Python 3.10 venv"
  uv venv --python 3.10 "$PKG/.venv"
fi
ROBONIX_API="$(rbnx path robonix-api)"
WHEELS="${RBNX_OFFLINE_WHEELS:-}"
PIP_ARGS=()
if [[ -n "$WHEELS" ]]; then
  PIP_ARGS+=(--offline --find-links "$WHEELS")
fi
uv pip install --python "$PY" "${PIP_ARGS[@]}" -e "$ROBONIX_API"
uv pip install --python "$PY" "${PIP_ARGS[@]}" setuptools wheel
uv pip install --python "$PY" "${PIP_ARGS[@]}" --no-deps -e "$PKG/../../third_party/unitree_sdk2_python"

echo "[r1_audio/build] installing cyclonedds Python bindings"
if [[ -n "$WHEELS" && -f "$WHEELS/cyclonedds-0.10.2.tar.gz" ]]; then
  CDDS_PREFIX="$PKG/.cyclonedds-prefix"
  mkdir -p "$CDDS_PREFIX/bin" "$CDDS_PREFIX/lib"
  ln -sfn /usr/local/include "$CDDS_PREFIX/include"
  ln -sf /usr/local/lib/libddsc.so "$CDDS_PREFIX/lib/libddsc.so"
  ln -sf /usr/local/lib/libddsc.so.0 "$CDDS_PREFIX/lib/libddsc.so.0"
  CC="${CC:-gcc}" CXX="${CXX:-g++}" \
    CYCLONEDDS_HOME="$CDDS_PREFIX" \
    uv pip install --python "$PY" --no-build-isolation "${PIP_ARGS[@]}" \
      "$WHEELS/cyclonedds-0.10.2.tar.gz"
else
  uv pip install --python "$PY" "${PIP_ARGS[@]}" "cyclonedds==0.10.2"
fi
echo "[r1_audio/build] done"
