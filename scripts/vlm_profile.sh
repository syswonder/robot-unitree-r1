#!/usr/bin/env bash
# 选择 Pilot 使用的模型。密钥和上游地址来自环境或本机配置，不写进仓库。

load_vlm_profile() {
  local selected="${1:-}"
  local profile_path="${R1_ROOT:-$HOME/r1-robonix}/config/vlm_provider"
  if [[ -z "$selected" && -f "$profile_path" ]]; then
    IFS= read -r selected < "$profile_path" || true
  fi
  VLM_PROVIDER="${selected:-deepseek}"
  case "$VLM_PROVIDER" in
    deepseek)
      VLM_PROVIDER_LABEL="DeepSeek"
      VLM_UPSTREAM="${VLM_UPSTREAM:-https://api.deepseek.com/v1}"
      VLM_PROFILE_MODEL="${VLM_MODEL:-deepseek-flash}"
      VLM_KEY_NAME="deepseek_api_key"
      ;;
    gateway)
      VLM_PROVIDER_LABEL="Gateway"
      if [[ -z "${VLM_UPSTREAM:-}" ]]; then
        echo "gateway provider requires VLM_UPSTREAM in the environment" >&2
        return 2
      fi
      VLM_PROFILE_MODEL="${VLM_MODEL:-llm-default}"
      VLM_KEY_NAME="gateway_api_key"
      ;;
    *) echo "unknown VLM provider: $VLM_PROVIDER (expected deepseek or gateway)" >&2; return 2 ;;
  esac
}
