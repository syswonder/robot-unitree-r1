#!/usr/bin/env bash
# Section 6 one-shot start: depth client, map service, Robonix stack, web client.
# Run on the R1. VLM proxy/reverse tunnel are started on the PC (pc_tunnels.sh).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env.sh"
source "$HERE/vlm_profile.sh"
load_vlm_profile

export VLM_BASE_URL="${VLM_BASE_URL:-http://127.0.0.1:16667/v1}"
export VLM_API_KEY="${VLM_API_KEY:-local-proxy}"
export VLM_MODEL="${VLM_MODEL:-$VLM_PROFILE_MODEL}"

KEY_FILE="$SECRETS/$VLM_KEY_NAME"
if [[ ! -s "$KEY_FILE" ]]; then
  if [[ -t 0 && -x "$HERE/vlm_key.sh" ]]; then
    echo "[start] $VLM_PROVIDER_LABEL API key is not configured."
    "$HERE/vlm_key.sh" set "$VLM_PROVIDER" || true
  else
    echo "[start] WARN: $VLM_PROVIDER_LABEL API key missing; chat will be unavailable." >&2
    echo "        On R1 run: $HERE/vlm_key.sh set $VLM_PROVIDER" >&2
  fi
fi

started=()

start_depth_client() {
  if pgrep -f 'depth_client/client 192.168.123.161' >/dev/null 2>&1; then
    echo "[start] depth client already running"
    return
  fi
  local client=/unitree/module/system_patch_pc4/depth_client/client
  if [[ ! -x "$client" ]]; then
    echo "[start] WARN: $client not found; depth/map will be empty" >&2
    return
  fi
  (
    cd /unitree/module/system_patch_pc4/depth_client
    setsid nohup "$client" 192.168.123.161 5000 /dev/video-dep \
      >> "$LOGS/depth-client.log" 2>&1 < /dev/null &
    echo $! > "$RUN_DIR/depth-client.pid"
  )
  echo "[start] depth client"
  started+=("depth client")
}

start_map() {
  if curl -sf --max-time 2 http://127.0.0.1:50107/api/health >/dev/null 2>&1; then
    echo "[start] map service already running"
    return
  fi
  setsid nohup "$DEPLOY/map_service/run.sh" \
    >> "$LOGS/map-service.log" 2>&1 < /dev/null &
  echo $! > "$RUN_DIR/map-service.pid"
  echo "[start] map service :50107"
  started+=("map service")
}

start_robot_reboot_watch() {
  if pgrep -f '[/]watch_robot_reboot.py --interface eth10' >/dev/null 2>&1; then
    echo "[start] robot reboot watch is already running"
    return
  fi
  local python="$DEPLOY/primitives/r1_state/.venv/bin/python"
  if [[ ! -x "$python" ]]; then
    echo "[start] robot reboot watch is missing the r1_state Python environment" >&2
    exit 1
  fi
  setsid nohup "$python" "$HERE/watch_robot_reboot.py" --interface eth10 \
    --run-dir "$RUN_DIR" --log-dir "$LOGS" \
    >> "$LOGS/robot-reboot-watch.log" 2>&1 < /dev/null &
  echo $! > "$RUN_DIR/robot-reboot-watch.pid"
  echo "[start] robot reboot watch"
}

start_stack() {
  if pgrep -f 'rbnx boot.*robonix_manifest.r1-native.yaml' >/dev/null 2>&1; then
    echo "[start] Robonix stack already running"
    return
  fi
  (
    cd "$DEPLOY"
    setsid nohup rbnx boot -f robonix_manifest.r1-native.yaml \
      --no-update-check -v >> "$LOGS/stack.log" 2>&1 < /dev/null &
    echo $! > "$RUN_DIR/stack.pid"
  )
  echo "[start] Robonix stack"
  started+=("Robonix stack")
}

start_web() {
  if pgrep -f 'robonix-client --robot-host 127.0.0.1 --port 7860' >/dev/null 2>&1; then
    echo "[start] web client already running"
    return
  fi
  (
    cd "$R1_ROOT/robonix-client"
    export ROBONIX_CLIENT_REVERSE_AUDIO=0
    setsid nohup .venv/bin/robonix-client --robot-host 127.0.0.1 --port 7860 \
      --mic-node-id audio_client_bridge --speaker-node-id r1_audio --tts-node-id speech \
      >> "$LOGS/web-client.log" 2>&1 < /dev/null &
    echo $! > "$RUN_DIR/web-client.pid"
  )
  echo "[start] web client :7860"
  started+=("web client")
}

start_depth_client
start_robot_reboot_watch
start_map
start_stack
start_web

if ! curl -sf --max-time 3 http://127.0.0.1:16667/health >/dev/null 2>&1; then
  echo "[start] WARN: VLM proxy/tunnel is not reachable on 127.0.0.1:16667" >&2
  echo "        run scripts/pc_tunnels.sh start on the PC for chat" >&2
fi

if ! timeout 2 bash -c '</dev/tcp/192.168.123.161/5000' 2>/dev/null; then
  echo "[start] WARN: depth server 192.168.123.161:5000 is CLOSED" >&2
  echo "        enable Stereo patch PC1 in the Unitree App (keep video_hub off);" >&2
  echo "        the depth receiver restarts automatically when the robot comes back" >&2
fi

echo "[start] waiting for stack and providers..."
ready=false
for _ in $(seq 1 90); do
  perception="$(curl -sf --max-time 2 \
    'http://127.0.0.1:7860/api/perception/status?atlas=127.0.0.1:50051' 2>/dev/null || true)"
  capabilities="$(rbnx caps 2>/dev/null || true)"
  provider_count="$(grep -cE '\[(ACTIVE|REGISTERED)\]' <<<"$capabilities" || true)"
  if [[ "${provider_count:-0}" -ge 18 ]] && \
     grep -qF 'audio_client_bridge [ACTIVE]' <<<"$capabilities" && \
     grep -qF 'speech [ACTIVE]' <<<"$capabilities" && \
     grep -qF 'visual_action_decider [ACTIVE]' <<<"$capabilities" && \
     grep -qF 'r1_arm [ACTIVE]' <<<"$capabilities" && \
     grep -qF 'r1_left_arm [ACTIVE]' <<<"$capabilities" && \
     grep -qF 'r1_right_arm [ACTIVE]' <<<"$capabilities" && \
     grep -qF 'r1_imu [ACTIVE]' <<<"$capabilities" && \
     grep -qF 'r1_chassis [ACTIVE]' <<<"$capabilities" && \
     grep -q '"camera":true' <<<"$perception" && \
     grep -q '"depth":true' <<<"$perception" && \
     curl -sf --max-time 2 http://127.0.0.1:50107/api/health >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "[start] ERROR: providers or perception did not become ready" >&2
  exit 1
fi

echo "[start] status:"
"$HERE/status.sh" || true
