#!/usr/bin/env bash
# Build the read-only R1 state primitive: codegen + a local Python 3.10 venv.
set -euo pipefail

PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

FLAGS=(--mcp)
[[ "${RBNX_BUILD_CLEAN:-}" == "1" ]] && FLAGS+=(--clean)
echo "[r1_state/build] rbnx codegen ${FLAGS[*]}"
rbnx codegen -p "$PKG" "${FLAGS[@]}"

PY="$PKG/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[r1_state/build] creating Python 3.10 venv"
  uv venv --python 3.10 "$PKG/.venv"
fi

ROBONIX_API="$(rbnx path robonix-api)"
PIP_ARGS=()
WHEELS="${RBNX_OFFLINE_WHEELS:-}"
if [[ -n "$WHEELS" ]]; then
  echo "[r1_state/build] offline wheels: $WHEELS"
  PIP_ARGS+=(--offline --find-links "$WHEELS")
fi

echo "[r1_state/build] installing robonix-api from $ROBONIX_API"
uv pip install --python "$PY" "${PIP_ARGS[@]}" -e "$ROBONIX_API"

echo "[r1_state/build] installing build helpers and numpy"
uv pip install --python "$PY" "${PIP_ARGS[@]}" setuptools wheel numpy

echo "[r1_state/build] installing cyclonedds Python bindings"
if [[ -n "$WHEELS" && -f "$WHEELS/cyclonedds-0.10.2.tar.gz" ]]; then
  # No aarch64 wheel exists on PyPI. Build the binding against the
  # existing CycloneDDS 0.10.2 install on the R1 (/usr/local).
  # The standalone CPython on the R1 defaults to clang, which is not
  # installed there. Build the binding with the system gcc instead.
  #
  # /usr/local has libcycloneddsidl.so but not the idl/ headers, which makes
  # the binding try (and fail) to build its optional idlpy extension. Use a
  # local prefix that exposes the ddsc library and headers only.
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

echo "[r1_state/build] installing vendored unitree_sdk2py"
uv pip install --python "$PY" "${PIP_ARGS[@]}" --no-deps \
  -e "$PKG/../../third_party/unitree_sdk2_python"

echo "[r1_state/build] done"
