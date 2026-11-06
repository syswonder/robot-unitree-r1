#!/usr/bin/env bash
# R1 deployment environment. Source this from scripts in this repository. It exports ROBONIX_DEPLOY_DIR before boot.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export R1_ROOT="${R1_ROOT:-$HOME/r1-robonix}"
export ROBONIX_DEPLOY_DIR="$(cd "$_script_dir/.." && pwd)"
export DEPLOY="$ROBONIX_DEPLOY_DIR"
export BOOTSTRAP="$R1_ROOT/bootstrap"
export TOOLCHAINS="$R1_ROOT/toolchains"
export LOGS="$R1_ROOT/logs"
export RUN_DIR="$R1_ROOT/run"
export SECRETS="$R1_ROOT/secrets"

export PATH="$TOOLCHAINS/cargo/bin:$TOOLCHAINS/rust-1.99/bin:$R1_ROOT/bin:$TOOLCHAINS/python-3.10.22/bin:$PATH"
export CARGO_HOME="$TOOLCHAINS/cargo"
export RUSTUP_HOME="${RUSTUP_HOME:-$TOOLCHAINS/rustup}"
export UV_PYTHON="$TOOLCHAINS/python-3.10.22/bin/python3.10"
export RBNX_OFFLINE_WHEELS="$BOOTSTRAP/wheels"
export RBNX_CODEGEN_PYTHON="$TOOLCHAINS/robonix-home/codegen-venv/bin/python"

mkdir -p "$LOGS" "$RUN_DIR" "$ROBONIX_DEPLOY_DIR/logs"
