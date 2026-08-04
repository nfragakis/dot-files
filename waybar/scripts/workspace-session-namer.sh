#!/bin/bash

# Workspace Session Namer for Waybar
# Listens for Hyprland events and renames workspaces based on tmux session names
# from terminal window titles.

# Function to extract tmux session name from window title
# Terminal titles follow pattern: hostname ❐ SESSION_NAME ● N window_name
get_session_from_title() {
    local title="$1"
    # Extract text between ❐ and ●
    if [[ "$title" =~ ❐[[:space:]]([^●]+)[[:space:]]● ]]; then
        echo "${BASH_REMATCH[1]}" | xargs  # trim whitespace
    else
        echo ""
    fi
}

# Function to update workspace name based on its windows
update_workspace_name() {
    local workspace_id="$1"
    local max_len=6  # Max characters for session name

    # Get all windows in this workspace
    local windows
    windows=$(hyprctl clients -j | jq -r ".[] | select(.workspace.id == $workspace_id) | .title" 2>/dev/null)

    local session_name=""

    # Look for a tmux session name in any window title
    while IFS= read -r title; do
        [[ -z "$title" ]] && continue
        session_name=$(get_session_from_title "$title")
        if [[ -n "$session_name" ]]; then
            # Remove trailing numbers/dashes (e.g., "nimbus-0" -> "nimbus")
            session_name=$(echo "$session_name" | sed 's/-[0-9]*$//')
            # Truncate to max length
            session_name="${session_name:0:$max_len}"
            break
        fi
    done <<< "$windows"

    # Display number (workspace 10 shows as 0)
    local display_num
    if [[ "$workspace_id" -eq 10 ]]; then
        display_num="0"
    else
        display_num="$workspace_id"
    fi

    # Format: "N:session" or just "N" if no session
    local new_name
    if [[ -n "$session_name" ]]; then
        new_name="${display_num}:${session_name}"
    else
        new_name="$display_num"
    fi

    # Rename the workspace
    hyprctl dispatch renameworkspace "$workspace_id" "$new_name" >/dev/null 2>&1
}

# Function to update all workspaces
update_all_workspaces() {
    local workspaces
    workspaces=$(hyprctl workspaces -j | jq -r '.[].id' 2>/dev/null)

    while IFS= read -r ws_id; do
        [[ -z "$ws_id" ]] && continue
        update_workspace_name "$ws_id"
    done <<< "$workspaces"
}

# Initial update of all workspaces
update_all_workspaces

# Listen for Hyprland events
nc -U "$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock" | while IFS= read -r event; do
    case "$event" in
        workspace\>*|focusedmon\>*)
            # Workspace changed - update all
            update_all_workspaces
            ;;
        openwindow\>*|closewindow\>*|movewindow\>*|windowtitle\>*)
            # Window event - update all workspaces
            update_all_workspaces
            ;;
    esac
done
