#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
state_home="${XDG_STATE_HOME:-$HOME/.local/state}"
timestamp="$(date +%Y%m%dT%H%M%S)-$$"
backup_root="$state_home/dot-files/backups/input/$timestamp"

backup_file() {
  local target="$1"
  local backup="$backup_root/${target#/}"

  [[ -e "$target" || -L "$target" ]] || return
  mkdir -p -- "$(dirname -- "$backup")"
  cp -a -- "$target" "$backup"
  printf 'Backed up %s -> %s\n' "$target" "$backup"
}

omarchy pkg add keyd
keyd check "$repo_dir/keyd/default.conf"

backup_file "$config_home/hypr/input.lua"
install -Dm644 -- "$repo_dir/hypr/input.lua" "$config_home/hypr/input.lua"

sudo install -Dm644 -- "$repo_dir/keyd/default.conf" /etc/keyd/default.conf
sudo systemctl enable --now keyd

hyprctl reload
config_errors="$(hyprctl configerrors)"
if [[ -n "$config_errors" ]]; then
  printf '%s\n' "$config_errors" >&2
  exit 1
fi

printf 'Caps Lock is now Escape when tapped and Super when held.\n'
