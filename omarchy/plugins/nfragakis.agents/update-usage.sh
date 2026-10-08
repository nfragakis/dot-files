#!/usr/bin/env bash
# Local counterpart of omarchy-agent-usage-update; same flags and record contract.

usage_dir="${XDG_STATE_HOME:-$HOME/.local/state}/omarchy/agents/usage"
plugin_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
packaged_root="${OMARCHY_PATH:-/usr/share/omarchy}"
mkdir -p "$usage_dir" || exit 1

flags=()
only=()
declare -A excluded
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force | --limits-only) flags+=("$1") ;;
    --except) excluded[$2]=1; shift ;;
    *) only+=("$1") ;;
  esac
  shift
done

wanted() {
  local agent="$1" candidate
  [[ -n ${excluded[$agent]} ]] && return 1
  (( ${#only[@]} == 0 )) && return 0
  for candidate in "${only[@]}"; do
    [[ $candidate == "$agent" ]] && return 0
  done
  return 1
}

collect() {
  local collector="$1" agent="$2" record tmp
  local command=("$collector")
  case "$agent" in
    claude | codex) command=(/usr/bin/python3 "$plugin_dir/collect-native.py" "$agent") ;;
  esac
  if ! record=$("${command[@]}" "${flags[@]}") || [[ -z $record ]] || ! jq -e . >/dev/null 2>&1 <<<"$record"; then
    echo "agents: $agent collector failed" >&2
    return 1
  fi
  tmp=$(mktemp "$usage_dir/.$agent.XXXXXX") || return 1
  printf '%s\n' "$record" >"$tmp"
  mv "$tmp" "$usage_dir/$agent.json"
}

pids=()
for collector in "$packaged_root"/bin/omarchy-agent-usage-*; do
  [[ -x $collector ]] || continue
  agent="${collector##*/omarchy-agent-usage-}"
  [[ $agent == update ]] && continue
  wanted "$agent" || continue
  collect "$collector" "$agent" &
  pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
  wait "$pid" || status=1
done
exit "$status"
