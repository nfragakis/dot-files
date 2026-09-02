#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
state_dir="${WHISPER_STT_STATE_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/whisper-stt}"
pid_file="$state_dir/recording.pid"
audio_file="$state_dir/recording.wav"
device_config="$state_dir/audio_device"

notify() {
  command -v notify-send >/dev/null 2>&1 || return 0
  notify-send -a "Whisper STT" "$1" "${2:-}" >/dev/null 2>&1 &
}

recording_pid() {
  [[ -f "$pid_file" ]] || return 1

  local pid command_name
  read -r pid < "$pid_file" || return 1
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  read -r command_name < "/proc/$pid/comm" 2>/dev/null || return 1
  [[ "$command_name" == "pw-record" ]] || return 1
  printf '%s\n' "$pid"
}

status() {
  if recording_pid >/dev/null; then
    printf 'recording\n'
  else
    rm -f -- "$pid_file"
    printf 'idle\n'
  fi
}

start_recording() {
  if recording_pid >/dev/null; then
    return 0
  fi

  rm -f -- "$pid_file" "$audio_file"
  mkdir -p -- "$state_dir"

  if ! command -v pw-record >/dev/null 2>&1; then
    notify "Recording failed" "pw-record is not installed"
    return 1
  fi

  # Warm the local model while the user is speaking.
  systemctl --user start whisper-stt-local.service >/dev/null 2>&1 &

  local record_args=(--channels=1 --rate=16000 --format=s16)
  if [[ -f "$device_config" ]]; then
    local device
    device="$(tr -d '[:space:]' < "$device_config")"
    if [[ -n "$device" ]]; then
      record_args+=(--target "$device")
    fi
  fi
  record_args+=("$audio_file")

  pw-record "${record_args[@]}" >/dev/null 2>&1 &
  local pid=$!
  printf '%s\n' "$pid" > "$pid_file"

  # Catch an invalid source or another immediate PipeWire startup failure.
  sleep 0.08
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f -- "$pid_file" "$audio_file"
    notify "Recording failed" "PipeWire could not open the microphone"
    return 1
  fi
}

stop_recording() {
  if ! recording_pid >/dev/null; then
    rm -f -- "$pid_file"
    notify "Recording failed" "No recording is in progress"
    return 1
  fi

  /usr/bin/python3 "$script_dir/transcribe.py"
}

action="${1:-toggle}"
case "$action" in
  start)
    start_recording
    ;;
  stop)
    stop_recording
    ;;
  toggle)
    if recording_pid >/dev/null; then
      stop_recording
    else
      start_recording
    fi
    ;;
  status)
    status
    ;;
  *)
    printf 'usage: %s {start|stop|toggle|status}\n' "${0##*/}" >&2
    exit 2
    ;;
esac
