#!/usr/bin/env bash
# Section 4/5 one-shot build: offline Rust toolchain + Robonix + providers.
# Run on the R1. This is idempotent; Cargo and uv reuse existing artifacts.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"

if [[ ! -d "$R1_ROOT/robonix" ]]; then
  echo "missing $R1_ROOT/robonix" >&2
  exit 1
fi
if [[ ! -d "$R1_ROOT/bootstrap/wheels" ]]; then
  echo "missing $R1_ROOT/bootstrap/wheels" >&2
  exit 1
fi
if [[ ! -d "$R1_ROOT/vendor" ]]; then
  echo "missing $R1_ROOT/vendor" >&2
  exit 1
fi

mkdir -p "$R1_ROOT/bin"
cat > "$R1_ROOT/bin/gcc-memcmp-safe" <<'EOF'
#!/bin/sh
exec /usr/bin/gcc -fno-builtin-memcmp "$@"
EOF
cat > "$R1_ROOT/bin/g++-memcmp-safe" <<'EOF'
#!/bin/sh
exec /usr/bin/g++ -fno-builtin-memcmp "$@"
EOF
chmod 0755 "$R1_ROOT/bin/gcc-memcmp-safe" "$R1_ROOT/bin/g++-memcmp-safe"

echo "[build] core Rust components"
(
  cd "$R1_ROOT/robonix"
  CARGO_NET_OFFLINE=true cargo build --release --offline \
    -p robonix-atlas -p robonix-soma -p robonix-codegen -p robonix-cli
)

echo "[build] full stack (Pilot/Executor/Liaison/Vitals)"
(
  cd "$R1_ROOT/robonix"
  export CC="$R1_ROOT/bin/gcc-memcmp-safe"
  export CXX="$R1_ROOT/bin/g++-memcmp-safe"
  CARGO_NET_OFFLINE=true cargo build --release --offline \
    -p robonix-pilot -p robonix-executor -p robonix-liaison -p robonix-vitals
)

echo "[build] install binaries to $CARGO_HOME/bin"
for binary in rbnx robonix-atlas robonix-codegen robonix-soma \
              robonix-pilot robonix-executor robonix-liaison robonix-vitals; do
  install -m0755 "$R1_ROOT/robonix/target/release/$binary" "$CARGO_HOME/bin/$binary"
done

echo "[build] register Robonix source tree"
rbnx setup "$R1_ROOT/robonix"

echo "[build] providers"
cd "$DEPLOY"
for package in r1_state r1_health r1_camera r1_depth r1_audio r1_arm r1_imu r1_arm_pose r1_chassis; do
  rbnx build -p "primitives/$package" --no-update-check
done
rbnx build -p services/r1_speech --no-update-check
rbnx build -p services/visual_action_decider --no-update-check
UV_OFFLINE=true UV_FIND_LINKS="$BOOTSTRAP/wheels" AUDIO_CLIENT_BRIDGE_PYTHON="$UV_PYTHON" \
  rbnx build -p primitives/audio_client_bridge --no-update-check

echo "[build] web client venv (Python 3.12)"
if [[ ! -d "$R1_ROOT/robonix-client" ]]; then
  echo "missing $R1_ROOT/robonix-client" >&2
  exit 1
fi
cd "$R1_ROOT/robonix-client"
if [[ ! -x ".venv/bin/python" ]]; then
  uv venv --python "$TOOLCHAINS/python-3.12.15/bin/python3.12" .venv
  uv pip install --python .venv/bin/python --offline \
    --find-links "$BOOTSTRAP/py312-wheels" setuptools wheel packaging
fi
# Reinstall the editable package on every build so client source changes
# take effect without deleting the venv.
uv pip install --python .venv/bin/python --offline \
  --find-links "$BOOTSTRAP/py312-wheels" --no-build-isolation -e .

echo "[build] done"
echo "  source $R1_ROOT/env.sh"
echo "  $R1_ROOT/scripts/02_start.sh"
