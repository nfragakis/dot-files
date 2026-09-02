#!/usr/bin/env bash

set -euo pipefail

plugin_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
unit_dir="$config_home/systemd/user"
unit_target="$unit_dir/whisper-stt-local.service"

mkdir -p -- "$config_home/whisper-stt" "$unit_dir"

if [[ -e "$unit_target" || -L "$unit_target" ]]; then
  if [[ -L "$unit_target" ]] \
    && [[ "$(readlink -f -- "$unit_target")" == "$plugin_dir/whisper-stt-local.service" ]]; then
    printf 'Already linked %s\n' "$unit_target"
  else
    backup="$unit_target.backup.$(date +%Y%m%dT%H%M%S)"
    mv -- "$unit_target" "$backup"
    printf 'Backed up %s -> %s\n' "$unit_target" "$backup"
    ln -s -- "$plugin_dir/whisper-stt-local.service" "$unit_target"
    printf 'Linked %s\n' "$unit_target"
  fi
else
  ln -s -- "$plugin_dir/whisper-stt-local.service" "$unit_target"
  printf 'Linked %s\n' "$unit_target"
fi

systemctl --user daemon-reload
printf 'Whisper service installed. Model/runtime setup remains in %s\n' "$config_home/whisper-stt"
