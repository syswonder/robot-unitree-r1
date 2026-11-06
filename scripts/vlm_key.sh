#!/usr/bin/env bash
# Store the selected API key for this deployment. The key is never printed,
# never passed on a command line, and is written only under $SECRETS.
#
# Usage:
#   vlm_key.sh set [deepseek|gateway]
#   vlm_key.sh use deepseek|gateway
#   vlm_key.sh status [deepseek|gateway]
#   vlm_key.sh clear [deepseek|gateway]
#
# gateway requires VLM_UPSTREAM, and optionally VLM_MODEL, in the environment.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"
source "$HERE/vlm_profile.sh"

KEY_DIR="$SECRETS"
cmd="${1:-status}"
provider="${2:-}"
if [[ "$cmd" == set && -z "$provider" && -t 0 ]]; then
  printf 'API: 1) DeepSeek  2) gateway (set VLM_UPSTREAM first)\n' >&2
  read -r -p 'Select [1/2, default 1]: ' provider
  case "$provider" in
    1|deepseek|'') provider=deepseek ;;
    2|gateway) provider=gateway ;;
    *) echo "invalid API selection" >&2; exit 2 ;;
  esac
fi
if [[ "$cmd" == use && -z "$provider" ]]; then
  echo "usage: $0 use deepseek|gateway" >&2
  exit 2
fi
load_vlm_profile "$provider"
KEY_FILE="$KEY_DIR/$VLM_KEY_NAME"

select_provider() {
  mkdir -p "$R1_ROOT/config"
  printf '%s\n' "$VLM_PROVIDER" > "$R1_ROOT/config/vlm_provider"
  echo "selected: $VLM_PROVIDER_LABEL ($VLM_UPSTREAM, model=$VLM_PROFILE_MODEL)"
}

set_key() {
  local key
  umask 077
  mkdir -p "$KEY_DIR"
  chmod 700 "$KEY_DIR"

  if [[ -t 0 ]]; then
    printf '%s API key (input hidden): ' "$VLM_PROVIDER_LABEL" >&2
    if ! IFS= read -r -s key; then
      printf '\n' >&2
      echo "no input; key not saved" >&2
      exit 1
    fi
    printf '\n' >&2
  else
    IFS= read -r key || true
  fi

  if [[ -z "$key" ]]; then
    echo "empty key; not saved" >&2
    exit 1
  fi
  if [[ "$key" =~ [[:space:]] ]]; then
    echo "key contains whitespace; not saved" >&2
    exit 1
  fi
  if [[ "$VLM_PROVIDER" == deepseek ]] && (( ${#key} < 20 )); then
    echo "key looks too short; not saved" >&2
    exit 1
  fi

  printf '%s' "$key" > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
  unset key
  select_provider
  echo "saved $KEY_FILE (mode 600)"
  echo "restart the proxy that reads this file, then restart the stack:"
  echo "  bash $HERE/02_start.sh"
}

show_status() {
  echo "API: $VLM_PROVIDER_LABEL"
  echo "Base URL: $VLM_UPSTREAM"
  echo "Model: $VLM_PROFILE_MODEL"
  if [[ -s "$KEY_FILE" ]]; then
    local mode size
    mode="$(stat -c '%a' "$KEY_FILE")"
    size="$(wc -c < "$KEY_FILE")"
    echo "configured: $KEY_FILE (mode $mode, $size bytes)"
    if [[ "$mode" != "600" ]]; then
      echo "warning: expected mode 600" >&2
      chmod 600 "$KEY_FILE"
      echo "fixed mode to 600" >&2
    fi
  else
    echo "not configured: run $0 set $VLM_PROVIDER" >&2
    exit 1
  fi
}

case "$cmd" in
  set) set_key ;;
  use)
    [[ -s "$KEY_FILE" ]] || { echo "configure the key first: $0 set $VLM_PROVIDER" >&2; exit 1; }
    select_provider
    ;;
  status) show_status ;;
  clear)
    rm -f "$KEY_FILE"
    echo "cleared $KEY_FILE"
    ;;
  *)
    echo "usage: $0 set|status|clear [deepseek|gateway] | use deepseek|gateway" >&2
    exit 2
    ;;
esac
