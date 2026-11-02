#!/usr/bin/env python3
"""Link the repo-managed Diff plugin; --host skips the desktop shortcut override."""
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

CHORD = "ctrl+shift+d"
ACTION = "plugin.diff.open"


def install() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", action="store_true", help="Link the host implementation without changing keyboard settings.")
    args = parser.parse_args()
    tern = shutil.which("tern")
    if not tern:
        raise RuntimeError("Tern is not on PATH.")
    root = Path(__file__).resolve().parent / "tern" / "plugins" / "diff"
    if args.host:
        subprocess.run([tern, "plugin", "link", str(root)], check=True)
        print("Host installed; desktop settings left unchanged.")
        return
    result = subprocess.run([tern, "plugin", "dir"], check=True, capture_output=True, text=True)
    plugins = Path(result.stdout.strip()).expanduser()
    if not plugins.is_absolute():
        raise RuntimeError(f"Tern returned an unexpected plugin directory: {result.stdout!r}")
    # Resolve an existing dotfiles symlink rather than replacing the symlink itself.
    settings = (plugins.parent / "settings.json").resolve()
    original = settings.read_bytes() if settings.exists() else None
    config = json.loads(original) if original is not None else {}
    if not isinstance(config, dict) or not isinstance(config.get("keybinds", {}), dict):
        raise RuntimeError("settings.json must contain a JSON object and an object-valued keybinds field.")
    bindings = config.setdefault("keybinds", {})
    previous = bindings.get(CHORD)
    bindings[CHORD] = ACTION
    mode = stat.S_IMODE(settings.stat().st_mode) if settings.exists() else 0o600

    # Validate/load the package before changing the user's keyboard preferences.
    subprocess.run([tern, "plugin", "link", str(root)], check=True)
    if previous != ACTION:
        settings.parent.mkdir(parents=True, exist_ok=True)
        if original is not None:
            backup = settings.with_name(settings.name + ".before-tern-diff")
            try:
                with backup.open("xb") as output:
                    os.chmod(backup, mode)
                    output.write(original)
                print(f"Settings backup: {backup}")
            except FileExistsError:
                print(f"Existing settings backup retained: {backup}")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=settings.parent, delete=False) as output:
                temporary = Path(output.name)
                os.chmod(temporary, mode)
                json.dump(config, output, indent=2, ensure_ascii=False)
                output.write("\n")
            # Refuse to overwrite a concurrent preferences edit by another Tern window.
            current = settings.read_bytes() if settings.exists() else None
            if current != original:
                raise RuntimeError("Tern settings changed during installation. Run the installer again.")
            os.replace(temporary, settings)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(f"{CHORD}: {previous if previous is not None else 'built-in defaults'} → {ACTION}")
    else:
        print(f"{CHORD} already opens Diff; other settings left unchanged.")
    print("Installed. Restart the Tern window to load the new user keymap.")
    print("Then choose 'Open diff viewer' in the palette, or press Ctrl+Shift+D.")
    print("This chord replaces its previous editor/Markdown/split actions.")


if __name__ == "__main__":
    try:
        install()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Diff installation failed: {error}", file=sys.stderr)
        sys.exit(1)
