#!/usr/bin/env bash
# Run in a PC desktop session to provide the PC microphone and speaker to the R1.
set -euo pipefail
PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
R1_HOST="${R1_HOST:-unitree@192.168.123.164}"
AUDIO_DIR="$PROJECT_ROOT/.work/pc-audio"
PY="$PROJECT_ROOT/robonix-client/.venv/bin/python"
mkdir -p "$AUDIO_DIR"
export TMPDIR="$AUDIO_DIR"
export LD_LIBRARY_PATH="$AUDIO_DIR/portaudio/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

start_one() {
  local name="$1"
  shift
  if [[ -f "$AUDIO_DIR/$name.pid" ]] && kill -0 "$(cat "$AUDIO_DIR/$name.pid")" 2>/dev/null; then
    echo "[pc-audio] $name already running"
    return
  fi
  setsid nohup "$@" > "$AUDIO_DIR/$name.log" 2>&1 < /dev/null &
  echo $! > "$AUDIO_DIR/$name.pid"
}

stop_one() {
  local name="$1"
  if [[ -f "$AUDIO_DIR/$name.pid" ]]; then
    local pid
    pid="$(cat "$AUDIO_DIR/$name.pid")"
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid"
    fi
    rm "$AUDIO_DIR/$name.pid"
  fi
}

case "${1:-status}" in
  start)
    "$PY" -c 'import sounddevice; sounddevice.check_input_settings(samplerate=16000, channels=1, dtype="int16")'
    start_one server "$PROJECT_ROOT/robonix-client/.venv/bin/robonix-client-audio-server" \
      --host 127.0.0.1 --port 60000 --ui-host 127.0.0.1
    start_one tunnel ssh -F /dev/null -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
      -R 127.0.0.1:60000:127.0.0.1:60000 "$R1_HOST"
    sleep 1
    for name in server tunnel; do
      kill -0 "$(cat "$AUDIO_DIR/$name.pid")"
    done
    echo "[pc-audio] PC audio and R1 tunnel started"
    ;;
  stop)
    stop_one tunnel
    stop_one server
    ;;
  status)
    for name in server tunnel; do
      if [[ -f "$AUDIO_DIR/$name.pid" ]] && kill -0 "$(cat "$AUDIO_DIR/$name.pid")" 2>/dev/null; then
        echo "[pc-audio] $name running"
      else
        echo "[pc-audio] $name stopped"
      fi
    done
    ;;
  *)
    echo "usage: $0 start|stop|status" >&2
    exit 2
    ;;
esac
