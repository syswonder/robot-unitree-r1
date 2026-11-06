#!/usr/bin/env bash
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ROOT="$(cd "$PKG/../../.." && pwd)"
source "$ROOT/env.sh"
CORE="$R1_ROOT/robonix/services/speech"
PY="$PKG/rbnx-build/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  uv venv --python "$UV_PYTHON" "$PKG/rbnx-build/venv"
fi
uv pip install --python "$PY" --offline --find-links "$BOOTSTRAP/wheels" \
  --no-sources -e "$R1_ROOT/robonix/pylib/robonix-api" -r "$CORE/pyproject.toml" \
  sherpa-onnx==1.13.4 sherpa-onnx-bin==1.13.4 sherpa-onnx-core==1.13.4
rbnx codegen --mcp -p "$PKG"
mkdir -p "$PKG/rbnx-build/models"
for model in sherpa-onnx-streaming-zipformer-ctc-zh-int8-2025-06-30 \
             vits-melo-tts-zh_en sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20; do
  if [[ ! -d "$PKG/rbnx-build/models/$model" ]]; then
    tar -xjf "$BOOTSTRAP/speech-models/$model.tar.bz2" -C "$PKG/rbnx-build/models"
  fi
done
