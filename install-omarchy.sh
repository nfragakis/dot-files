#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_root="$repo_dir/omarchy"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
state_home="${XDG_STATE_HOME:-$HOME/.local/state}"
target_root="$config_home/omarchy"
backup_root="$state_home/dot-files/backups/omarchy/$(date +%Y%m%dT%H%M%S)-$$"
backup_created=false

backup_target() {
  local target="$1"
  local relative_path="${target#"$target_root"/}"
  local backup="$backup_root/$relative_path"

  mkdir -p -- "$(dirname -- "$backup")"
  mv -- "$target" "$backup"
  backup_created=true
  printf 'Backed up %s -> %s\n' "$target" "$backup"
}

link_path() {
  local source="$1"
  local target="$2"

  if [[ ! -e "$source" ]]; then
    printf 'Missing source path: %s\n' "$source" >&2
    return 1
  fi

  mkdir -p -- "$(dirname -- "$target")"

  if [[ -L "$target" ]] && [[ "$(readlink -f -- "$target")" == "$(readlink -f -- "$source")" ]]; then
    printf 'Already linked %s\n' "$target"
    return
  fi

  if [[ -e "$target" || -L "$target" ]]; then
    backup_target "$target"
  fi

  ln -s -- "$source" "$target"
  printf 'Linked %s -> %s\n' "$target" "$source"
}

for plugin_path in "$source_root"/plugins/*; do
  [[ -d "$plugin_path" ]] || continue
  plugin="$(basename -- "$plugin_path")"
  link_path "$plugin_path" "$target_root/plugins/$plugin"
done

link_path "$source_root/shell.json" "$target_root/shell.json"
link_path "$source_root/shell.toml" "$target_root/shell.toml"

if command -v omarchy-shell >/dev/null 2>&1; then
  omarchy-shell -q shell rescanPlugins || true
fi

if [[ "$backup_created" == true ]]; then
  printf 'Previous files remain recoverable under %s\n' "$backup_root"
fi
