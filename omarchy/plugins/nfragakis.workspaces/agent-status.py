#!/usr/bin/env python3
"""Bridge coding-agent lifecycle hooks to the Omarchy workspace widget."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any


STATE_VERSION = 1
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60


def state_path() -> Path:
    override = os.environ.get("AGENT_ATTENTION_STATE")
    if override:
        return Path(override)
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return state_home / "omarchy/agent-attention.json"


def empty_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "sessions": {}}


def load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return empty_state()
    if not isinstance(value, dict) or not isinstance(value.get("sessions"), dict):
        return empty_state()
    return {"version": STATE_VERSION, "sessions": value["sessions"]}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as temporary:
            json.dump(state, temporary, separators=(",", ":"), sort_keys=True)
            temporary.write("\n")
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def update_state(change: Any) -> None:
    path = state_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(path)
        now = int(time.time())
        state["sessions"] = {
            key: value
            for key, value in state["sessions"].items()
            if isinstance(value, dict)
            and now - int(value.get("updatedAt", 0)) < STALE_AFTER_SECONDS
        }
        change(state, now)
        save_state(path, state)


def focused_workspace() -> int | None:
    override = os.environ.get("AGENT_ATTENTION_WORKSPACE")
    if override:
        try:
            workspace = int(override)
            return workspace if workspace > 0 else None
        except ValueError:
            return None
    try:
        result = subprocess.run(
            ["hyprctl", "activeworkspace", "-j"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        workspace = int(json.loads(result.stdout).get("id", 0))
        return workspace if workspace > 0 else None
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None


def event_state(provider: str, event: dict[str, Any]) -> str | None:
    name = str(event.get("hook_event_name", ""))
    if name in {"SessionStart", "UserPromptSubmit", "SessionEnd"}:
        return ""
    if provider == "codex":
        if name == "PermissionRequest":
            return "attention"
        if name == "Stop":
            return "complete"
    if provider == "claude":
        if name == "StopFailure":
            return "attention"
        if name == "Notification":
            notification_type = str(event.get("notification_type", ""))
            if notification_type in {"permission_prompt", "elicitation_dialog"}:
                return "attention"
            if notification_type == "idle_prompt":
                return "complete"
    return None


def handle_hook(provider: str, event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id", ""))
    if not session_id:
        return
    name = str(event.get("hook_event_name", ""))
    new_state = event_state(provider, event)
    if new_state is None:
        return
    current_workspace = focused_workspace()

    def change(state: dict[str, Any], now: int) -> None:
        sessions = state["sessions"]
        if name == "SessionEnd":
            sessions.pop(session_id, None)
            return
        previous = sessions.get(session_id, {})
        workspace = current_workspace if name in {"SessionStart", "UserPromptSubmit"} else previous.get("workspace")
        if workspace is None:
            workspace = current_workspace
        if workspace is None:
            return
        if new_state == "":
            sessions[session_id] = {
                "provider": provider,
                "workspace": workspace,
                "state": "",
                "updatedAt": now,
            }
        else:
            sessions[session_id] = {
                "provider": provider,
                "workspace": workspace,
                "state": new_state,
                "updatedAt": now,
            }

    update_state(change)


def clear_workspace(workspace: int) -> None:
    def change(state: dict[str, Any], now: int) -> None:
        for value in state["sessions"].values():
            if int(value.get("workspace", 0)) == workspace:
                value["state"] = ""
                value["updatedAt"] = now

    update_state(change)


def read_event() -> dict[str, Any]:
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: agent-status.py hook <codex|claude> | clear <workspace> | show", file=sys.stderr)
        return 2
    command = sys.argv[1]
    if command == "hook" and len(sys.argv) == 3 and sys.argv[2] in {"codex", "claude"}:
        event = read_event()
        handle_hook(sys.argv[2], event)
        if sys.argv[2] == "codex" and event.get("hook_event_name") == "Stop":
            print("{}")
        return 0
    if command == "clear" and len(sys.argv) == 3:
        try:
            workspace = int(sys.argv[2])
        except ValueError:
            return 2
        if workspace > 0:
            clear_workspace(workspace)
        return 0
    if command == "show" and len(sys.argv) == 2:
        print(json.dumps(load_state(state_path()), indent=2, sort_keys=True))
        return 0
    print("invalid arguments", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
