#!/bin/bash

# Workspace Session Namer for the Omarchy shell (and legacy Waybar).
# Renames workspaces based on tmux session names in terminal window titles.

# Quote a string for a double-quoted Lua literal. Workspace names originate in
# terminal titles, so they must not be interpolated into hyprctl eval as code.
lua_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    printf '"%s"' "$value"
}

update_all_workspaces() {
    local clients_json workspaces_json
    clients_json=$(hyprctl clients -j 2>/dev/null) || return
    workspaces_json=$(hyprctl workspaces -j 2>/dev/null) || return

    # Build every desired name in one jq pass, then ask Hyprland to rename only
    # workspaces whose names are stale. Session suffixes such as "-1" are
    # removed and the remaining name is capped at six characters.
    while IFS=$'\t' read -r workspace_id current_name desired_name; do
        [[ -z "$workspace_id" || "$current_name" == "$desired_name" ]] && continue

        local quoted_name
        quoted_name=$(lua_quote "$desired_name")
        hyprctl eval \
            "hl.dispatch(hl.dsp.workspace.rename({ workspace = $workspace_id, name = $quoted_name }))" \
            >/dev/null 2>&1
    done < <(jq -rn --argjson clients "$clients_json" --argjson workspaces "$workspaces_json" '
        $workspaces[]
        | select(.id > 0)
        | . as $workspace
        | (if .id == 10 then "0" else (.id | tostring) end) as $display
        | ([
            $clients[]
            | select(.workspace.id == $workspace.id)
            | .title
            | try capture("❐[[:space:]]+(?<session>[^●]+)[[:space:]]+●").session catch empty
            | sub("[[:space:]]+$"; "")
            | sub("-[0-9]+$"; "")
            | .[0:6]
          ] | (first // "")) as $session
        | (if $session == "" then $display else ($display + ":" + $session) end) as $desired
        | [$workspace.id, $workspace.name, $desired]
        | @tsv
    ')
}

# Polling avoids silent event-socket disconnects. Since renames happen only
# when a name changes, the steady-state loop is two reads and one jq pass.
while true; do
    update_all_workspaces
    sleep 1
done
