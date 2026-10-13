#!/usr/bin/env python3
"""Link Tern clipboard fixes without replacing unrelated Hyprland or omp config."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


REQUIRE = 'require("hypr.tern-clipboard")'
LOCAL_RULE = 'o.window("so\\\\.stencil\\\\.tern", { tag = "+terminal" })'
LOCAL_COMMENT = "-- Route universal clipboard shortcuts through Tern's local paste action."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    roles = parser.add_mutually_exclusive_group()
    roles.add_argument("--client", action="store_true", help="install only the Omarchy Super+V rule")
    roles.add_argument("--host", action="store_true", help="install only the omp image-paste extension")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR", Path.home() / ".omp/agent"))
    backups = state / "dot-files/backups/tern-clipboard" / f"{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}"
    bindings = config / "hypr/bindings.lua"
    install_client = not args.host
    install_host = not args.client

    def backup(target: Path, relative: str, *, move: bool) -> None:
        saved = backups / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        if move:
            shutil.move(str(target), saved)
        else:
            shutil.copy2(target, saved)
        print(f"Backed up {target} -> {saved}")

    def link(source: Path, target: Path, relative: str) -> None:
        if target.is_symlink() and target.resolve() == source:
            print(f"Already linked {target}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            backup(target, relative, move=True)
        target.symlink_to(source)
        print(f"Linked {target} -> {source}")

    try:
        # Read before changing anything: client installation requires Omarchy's Lua config.
        original = bindings.read_text() if install_client else ""
        if install_client:
            link(repo / "hypr/tern-clipboard.lua", config / "hypr/tern-clipboard.lua", "hypr/tern-clipboard.lua")
            lines = original.splitlines(keepends=True)
            # Migrate only the exact machine-local fix from the original repair.
            lines = [line for line in lines if line.strip() not in (LOCAL_RULE, LOCAL_COMMENT)]
            updated = "".join(lines)
            if not any(line.strip() == REQUIRE for line in lines):
                updated = updated.rstrip("\n") + "\n\n" + REQUIRE + "\n"
            if updated != original:
                backup(bindings, "hypr/bindings.lua", move=False)
                bindings.write_text(updated)
                print(f"Enabled Tern clipboard rule in {bindings}")
        if install_host:
            link(repo / "omp/extensions/tern-enhanced-paste.ts", agent / "extensions/tern-enhanced-paste.ts", "omp/tern-enhanced-paste.ts")
        if install_client and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
            subprocess.run(["hyprctl", "reload"], check=True)
            errors = subprocess.check_output(["hyprctl", "configerrors"], text=True).strip()
            if errors:
                raise ValueError(errors)
        elif install_client:
            print("Hyprland is not connected; the rule loads on next login (or run hyprctl reload).")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Could not install Tern clipboard fixes: {error}", file=sys.stderr)
        return 1
    if install_host:
        print("omp extension installed. Existing sessions: /reload; new sessions load it automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
