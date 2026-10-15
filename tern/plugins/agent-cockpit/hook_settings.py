"""Plan additive provider lifecycle JSON settings; never write user files.

Codex follows herdr's integration/targets.rs contract: CODEX_HOME/hooks.json
contains hooks.SessionStart groups, enabled by config.toml [features] hooks=true.
The TOML plan changes only the hook feature, preserving other settings and comments.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shlex
import stat
import tomllib


CONFIG_LIMIT = 1024 * 1024
CLAUDE_MATCHER = "^(startup|resume|clear|compact|fork)$"
CLAUDE_EVENTS = {
    "SessionStart": CLAUDE_MATCHER,
    "UserPromptSubmit": None,
    "PreToolUse": None,
    "PostToolUse": None,
    "PostToolUseFailure": None,
    "PermissionRequest": None,
    "Notification": "^(permission_prompt|idle_prompt)$",
    "Stop": None,
    "SessionEnd": None,
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _invalid_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _contents(path: Path) -> bytes | None:
    try:
        info = path.stat()
    except FileNotFoundError:
        if path.is_symlink():
            raise ValueError(f"{path}: dangling configuration symlink")
        return None
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"{path}: configuration must be a regular file")
    if info.st_size > CONFIG_LIMIT:
        raise ValueError(f"{path}: configuration exceeds {CONFIG_LIMIT} bytes")
    with path.open("rb") as stream:
        data = stream.read(CONFIG_LIMIT + 1)
    if len(data) > CONFIG_LIMIT:
        raise ValueError(f"{path}: configuration exceeds {CONFIG_LIMIT} bytes")
    return data


def _config_dir(home: Path, environ: dict[str, str], key: str, default: str) -> Path:
    raw = environ.get(key) or str(home / default)
    if not isinstance(raw, str) or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError(f"{key}: expected an absolute configuration directory")
    if raw == "~" or raw.startswith("~/"):
        raw = str(home) + raw[1:]
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError(f"{key}: expected an absolute configuration directory")
    return path


def _locations(home: Path, environ: dict[str, str]) -> tuple[Path, Path]:
    if not home.is_absolute():
        raise ValueError("home must be absolute")
    return (_config_dir(home, environ, "CLAUDE_CONFIG_DIR", ".claude"),
            _config_dir(home, environ, "CODEX_HOME", ".codex"))


def _load(path: Path) -> dict:
    data = _contents(path)
    if data is None:
        return {}
    try:
        value = json.loads(data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError(f"{path}: invalid JSON configuration: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path}: configuration must be a JSON object")
    return value


def _event_groups(value: dict, path: Path, event: str) -> list[dict]:
    hooks = value.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{path}: hooks must be a JSON object")
    groups = hooks.setdefault(event, [])
    if not isinstance(groups, list):
        raise ValueError(f"{path}: hooks.{event} must be an array")
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            raise ValueError(f"{path}: {event} groups must contain a hooks array")
        if "matcher" in group and not isinstance(group["matcher"], str):
            raise ValueError(f"{path}: {event} matcher must be a string")
        for hook in group["hooks"]:
            if not isinstance(hook, dict):
                raise ValueError(f"{path}: {event} hook must be an object")
            if hook.get("type") == "command" and not isinstance(hook.get("command"), str):
                raise ValueError(f"{path}: {event} command must be a string")
    return groups


def plans(home: Path, recorder: Path, environ: dict[str, str]) -> list[tuple[Path, dict]]:
    """Return only changed JSON documents; validation completes before any writes.

    Existing groups, other events and unknown fields are preserved verbatim as
    JSON values. Only an exact command is considered ours, never a substring.
    """
    if not recorder.is_absolute() or any(ord(char) < 32 or ord(char) == 127 for char in str(recorder)):
        raise ValueError("recorder must be an absolute path")
    claude, codex = _locations(home, environ)
    result = []
    for provider, path in (("claude", claude / "settings.json"), ("codex", codex / "hooks.json")):
        value = _load(path)
        events = CLAUDE_EVENTS if provider == "claude" else {"SessionStart": None}
        command = f"python3 {shlex.quote(str(recorder))} {provider}"
        changed = False
        for event, matcher in events.items():
            groups = _event_groups(value, path, event)
            if any(hook.get("type") == "command" and hook.get("command") == command
                   for group in groups
                   if group.get("matcher") in (None, "", "*", matcher)
                   for hook in group["hooks"]):
                continue
            group = {"hooks": [{"type": "command", "command": command, "timeout": 5}]}
            if matcher is not None:
                group["matcher"] = matcher
            groups.append(group)
            changed = True
        if changed:
            result.append((path, value))
    return result


def codex_plan(home: Path, environ: dict[str, str]) -> tuple[Path, str] | None:
    """Enable the required feature without reserializing personal TOML."""
    _, codex = _locations(home, environ)
    path = codex / "config.toml"
    raw = _contents(path)
    text = raw.decode("utf-8") if raw is not None else ""
    config = tomllib.loads(text)
    features = config.get("features", {})
    if not isinstance(features, dict):
        raise ValueError(f"{path}: features must be a TOML table")
    if features.get("hooks") is True:
        return None
    expected = copy.deepcopy(config)
    expected.setdefault("features", {})["hooks"] = True
    lines = text.splitlines(keepends=True)
    section = next((i for i, line in enumerate(lines)
                    if re.fullmatch(r"\s*\[\s*features\s*\]\s*(?:#[^\r\n]*)?[\r\n]*", line)), None)
    newline = "\r\n" if "\r\n" in text else "\n"
    if section is None:
        if "features" in config:
            raise ValueError(f"{path}: cannot safely merge a nonstandard features table; enable features.hooks manually")
        updated = text.rstrip("\r\n") + newline + "[features]" + newline + "hooks = true" + newline
    else:
        end = next((i for i in range(section + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
        key = next((i for i in range(section + 1, end)
                    if re.match(r"""\s*(?:hooks|"hooks"|'hooks')\s*=""", lines[i])), None)
        if key is None:
            if not lines[section].endswith(("\n", "\r")):
                lines[section] += newline
            lines.insert(section + 1, "hooks = true" + newline)
        else:
            lines[key] = re.sub(r"(=\s*)(?:false|true)\b", r"\1true", lines[key], count=1)
        updated = "".join(lines)
    if tomllib.loads(updated) != expected:
        raise ValueError(f"{path}: refusing an ambiguous hook feature edit")
    return path, updated
