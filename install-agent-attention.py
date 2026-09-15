#!/usr/bin/env python3
"""Install workspace-attention lifecycle hooks without replacing existing hooks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any


EVENTS = {
    "codex": ["SessionStart", "UserPromptSubmit", "PermissionRequest", "Stop", "SessionEnd"],
    "claude": ["SessionStart", "UserPromptSubmit", "Notification", "StopFailure", "SessionEnd"],
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def is_ours(group: Any) -> bool:
    if not isinstance(group, dict):
        return False
    handlers = group.get("hooks", [])
    return any(
        isinstance(handler, dict) and "nfragakis.workspaces/agent-status.py' hook" in str(handler.get("command", ""))
        for handler in handlers
    )


def add_hooks(config: dict[str, Any], provider: str, command: str) -> dict[str, Any]:
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("the existing hooks value must be a JSON object")
    for event in EVENTS[provider]:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError(f"the existing hooks.{event} value must be a JSON array")
        hooks[event] = [group for group in groups if not is_ours(group)] + [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 5,
                    }
                ]
            }
        ]
    return config


def write_json(path: Path, value: dict[str, Any], backup_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main() -> int:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    plugin_script = config_home / "omarchy/plugins/nfragakis.workspaces/agent-status.py"
    if not plugin_script.exists():
        print("Run ./install-omarchy.sh first so the workspace plugin is installed.", file=sys.stderr)
        return 1
    command_base = f"python3 '{plugin_script}' hook"
    codex_path = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "hooks.json"
    claude_path = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "settings.json"
    backup_dir = state_home / "dot-files/backups/agent-attention" / time.strftime("%Y%m%dT%H%M%S")
    try:
        codex_config = add_hooks(read_json(codex_path), "codex", command_base + " codex")
        claude_config = add_hooks(read_json(claude_path), "claude", command_base + " claude")
        write_json(codex_path, codex_config, backup_dir)
        write_json(claude_path, claude_config, backup_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Could not install agent hooks: {error}", file=sys.stderr)
        return 1
    attention_path = state_home / "omarchy/agent-attention.json"
    if not attention_path.exists():
        attention_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        attention_path.write_text('{"sessions":{},"version":1}\n')
        os.chmod(attention_path, 0o600)
    print(f"Installed Codex hooks in {codex_path}")
    print(f"Installed Claude Code hooks in {claude_path}")
    print(f"Backups: {backup_dir}")
    print("In Codex, run /hooks once and trust the new workspace-attention hooks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
