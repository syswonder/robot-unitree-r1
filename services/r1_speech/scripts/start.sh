#!/usr/bin/env bash
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOT="$(cd "$PKG/../../.." && pwd)"
CORE="$ROOT/robonix/services/speech"
cd "$PKG"
export PYTHONPATH="$PKG:$CORE:$PKG/rbnx-build/codegen/proto_gen:$PKG/rbnx-build/codegen/robonix_mcp_types:${PYTHONPATH:-}"
export SPEECH_BACKEND=custom
export ROBONIX_PROVIDER_BIND_HOST=127.0.0.1
export ROBONIX_ADVERTISE_HOST=127.0.0.1
exec "$PKG/rbnx-build/venv/bin/python" -m speech_service.service
