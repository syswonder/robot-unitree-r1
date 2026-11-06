#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"
PKG="$DEPLOY/primitives/r1_arm"
export PYTHONPATH="$(rbnx path robonix-api):$PKG:$PKG/rbnx-build/codegen/proto_gen:$PKG/rbnx-build/codegen/robonix_mcp_types:${PYTHONPATH:-}"
export ROBONIX_ATLAS=127.0.0.1:50051
exec "$PKG/.venv/bin/python" -m r1_arm.cli "$@"
