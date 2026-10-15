#!/usr/bin/env python3
"""Link the native Tern agent cockpit and preserve existing personal settings."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib


SHORTCUT = "ctrl+s>a"
ACTION = "plugin.agent-cockpit.open"


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate settings key: {key}")
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def source_plugin(repo: Path, plugin_id: str) -> Path:
    source = repo / "tern/plugins" / plugin_id
    with (source / "plugin.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    if manifest.get("id") != plugin_id:
        raise ValueError(f"{source}: expected plugin id {plugin_id}")
    if not manifest.get("window"):
        raise ValueError(f"{source}: missing window entrypoint")
    for field in ("window", "host"):
        entry = manifest.get(field)
        if entry is not None and (not isinstance(entry, str) or not (source / entry).is_file()):
            raise ValueError(f"{source}: missing {field} entrypoint {entry!r}")
    for style in manifest.get("styles", []):
        if not isinstance(style, str) or not (source / style).is_file():
            raise ValueError(f"{source}: missing stylesheet {style!r}")
    return source.resolve()


def main() -> int:
    repo = Path(__file__).resolve().parent
    config = Path(os.environ.get("TERN_CONFIG_DIR") or (
        Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "tern"
    ))
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    argparse.ArgumentParser(description=__doc__).parse_args()
    backups = state / "dot-files/backups/tern-cockpit" / (
        f"{time.strftime('%Y%m%dT%H%M%S')}.{time.time_ns() % 1_000_000_000:09d}-{os.getpid()}"
    )

    def backup(target: Path, relative: str) -> None:
        saved = backups / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            saved.symlink_to(os.readlink(target), target_is_directory=target.is_dir())
        elif target.is_dir():
            shutil.copytree(target, saved, symlinks=True)
        else:
            shutil.copy2(target, saved)
        print(f"Backed up {target} -> {saved}")

    def replace_config(path: Path, content: str, relative: str) -> None:
        destination = path.resolve() if path.is_symlink() else path
        if destination.exists():
            backup(destination, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                             prefix=".cockpit-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            if destination.exists():
                temporary.chmod(stat.S_IMODE(destination.stat().st_mode))
            temporary.replace(destination)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    try:
        # Complete input validation before creating backups, removing plugins or writing settings.
        sources = [source_plugin(repo, plugin_id) for plugin_id in ("agent-cockpit", "hostkeys")]
        settings = config / "settings.json"
        if settings.is_symlink() and not settings.is_file():
            raise ValueError(f"{settings}: dangling or non-file settings link")
        existed = settings.exists()
        original = settings.read_text(encoding="utf-8") if existed else ""
        data = json.loads(original, object_pairs_hook=unique_object, parse_constant=invalid_constant) if existed else {}
        if not isinstance(data, dict):
            raise ValueError(f"{settings}: settings must be a JSON object")
        if "keybinds" in data and not isinstance(data["keybinds"], dict):
            raise ValueError(f"{settings}: keybinds must be a JSON object")
        keybinds = data.setdefault("keybinds", {})
        changed = keybinds.get(SHORTCUT) != ACTION
        keybinds[SHORTCUT] = ACTION
        updated = json.dumps(data, indent=2) + "\n" if changed else original
        sys.path.insert(0, str(sources[0]))
        import hook_settings
        recorder = sources[0] / "hook_record.py"
        if not recorder.is_file():
            raise ValueError(f"Missing metadata hook recorder: {recorder}")
        hook_plans = [(path, json.dumps(value, indent=2) + "\n")
                      for path, value in hook_settings.plans(Path.home(), recorder, dict(os.environ))]
        codex_plan = hook_settings.codex_plan(Path.home(), dict(os.environ))
        if codex_plan:
            hook_plans.append(codex_plan)

        found = subprocess.run(["tern", "plugin", "dir"], check=True, capture_output=True, text=True).stdout.strip()
        if not found or not Path(found).is_absolute():
            raise ValueError(f"tern plugin dir returned an invalid directory: {found!r}")
        plugins = Path(found)
        if plugins.exists() and not plugins.is_dir():
            raise ValueError(f"{plugins}: plugin location is not a directory")
        plans: list[tuple[Path, list[Path]]] = []
        for source in sources:
            copied = plugins / source.name
            pointer = plugins / f"{source.name}.path"
            conflicts = [path for path in (copied, pointer) if path.exists() or path.is_symlink()]
            if copied in conflicts and not copied.is_dir() and not copied.is_symlink():
                raise ValueError(f"{copied}: installed plugin is not a directory")
            if pointer in conflicts and not pointer.is_file():
                raise ValueError(f"{pointer}: plugin link is not a readable file")
            if copied not in conflicts and pointer in conflicts:
                linked = pointer.read_text(encoding="utf-8").strip()
                if Path(linked).expanduser().resolve() == source:
                    continue
            plans.append((source, conflicts))

        for source, conflicts in plans:
            for conflict in conflicts:
                backup(conflict, f"plugins/{conflict.name}")
            if any(path.name == source.name + ".path" for path in conflicts):
                subprocess.run(["tern", "plugin", "unlink", source.name], check=True)
            if any(path.name == source.name for path in conflicts):
                subprocess.run(["tern", "plugin", "remove", source.name], check=True)
            subprocess.run(["tern", "plugin", "link", str(source)], check=True)
            print(f"Linked {source.name} -> {source}")

        if changed:
            replace_config(settings, updated, "settings.json")
            print(f"Enabled Ctrl+S then A in {settings}")
        else:
            print(f"Ctrl+S then A already enabled in {settings}")
        for index, (path, content) in enumerate(hook_plans):
            replace_config(path, content, f"provider-hooks/{index}-{path.name}")
            print(f"Enabled session metadata hooks in {path}")
        # Linking reloads before the settings merge; apply that merge too.
        # Explicit reload also picks up source updates when links already match.
        reloaded = subprocess.run(["tern", "plugin", "reload"], capture_output=True, text=True)
        if reloaded.returncode and "no daemon running" not in reloaded.stderr:
            raise ValueError(reloaded.stderr.strip() or reloaded.stdout.strip() or "Tern plugin reload failed")
        print(reloaded.stdout.strip() or "No daemon running; changes apply at next start.")
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Could not install Tern cockpit: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
