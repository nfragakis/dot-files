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

# Third-party plugins that shell.json places but this repository does not
# carry. `omarchy plugin add` clones each one into the plugin directory as a
# git-managed plugin (update with `omarchy plugin update <id>`). The bar
# placement already lives in the repo's shell.json, so --enable is deliberately
# not passed: enabling rewrites shell.json by rename, which would detach the
# link made below.
git_plugins=(
  "io.github.aryan-techie.todoist https://github.com/aryan-techie/omarchy-todoist.git"
)

for entry in "${git_plugins[@]}"; do
  plugin="${entry%% *}"
  url="${entry#* }"
  if [[ -e "$target_root/plugins/$plugin" ]]; then
    printf 'Already installed %s\n' "$target_root/plugins/$plugin"
  elif command -v omarchy-plugin-add >/dev/null 2>&1; then
    # Non-fatal: a clone that fails (no network, shell not running) must not
    # stop the config links below.
    omarchy-plugin-add "$url" --yes \
      || printf 'Could not add %s; run later: omarchy plugin add %s --yes\n' "$plugin" "$url" >&2
  else
    printf 'Skipping %s: omarchy-plugin-add is not on PATH\n' "$plugin" >&2
  fi
done

link_path "$source_root/shell.json" "$target_root/shell.json"
link_path "$source_root/shell.toml" "$target_root/shell.toml"

if command -v omarchy-shell >/dev/null 2>&1; then
  omarchy-shell -q shell rescanPlugins || true
fi

if [[ "$backup_created" == true ]]; then
  printf 'Previous files remain recoverable under %s\n' "$backup_root"
fi
