#!/usr/bin/env bash
# Build the read-only R1 health primitive: codegen + a local Python 3.10 venv.
set -euo pipefail

PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

FLAGS=()
[[ "${RBNX_BUILD_CLEAN:-}" == "1" ]] && FLAGS+=(--clean)
echo "[r1_health/build] rbnx codegen ${FLAGS[*]}"
rbnx codegen -p "$PKG" "${FLAGS[@]}"

PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[r1_health/build] creating Python 3.10 venv"
  uv venv --python 3.10 "$PKG/.venv"
fi

ROBONIX_API="$(rbnx path robonix-api)"
PIP_ARGS=()
WHEELS="${RBNX_OFFLINE_WHEELS:-}"
if [[ -n "$WHEELS" ]]; then
  echo "[r1_health/build] offline wheels: $WHEELS"
  PIP_ARGS+=(--offline --find-links "$WHEELS")
fi

echo "[r1_health/build] installing robonix-api from $ROBONIX_API"
uv pip install --python "$PY" "${PIP_ARGS[@]}" -e "$ROBONIX_API"

echo "[r1_health/build] installing build helpers"
uv pip install --python "$PY" "${PIP_ARGS[@]}" setuptools wheel

echo "[r1_health/build] installing cyclonedds Python bindings"
if [[ -n "$WHEELS" && -f "$WHEELS/cyclonedds-0.10.2.tar.gz" ]]; then
  # No aarch64 wheel exists on PyPI. Build against the R1's CycloneDDS
  # 0.10.2 install (/usr/local) with gcc, and hide the idl library that has
  # no matching headers so the optional idlpy extension is skipped.
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

echo "[r1_health/build] installing vendored unitree_sdk2py"
uv pip install --python "$PY" "${PIP_ARGS[@]}" --no-deps \
  -e "$PKG/../../third_party/unitree_sdk2_python"

echo "[r1_health/build] done"
