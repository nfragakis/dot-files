#!/usr/bin/env python3
"""Keep an occluded cockpit alive only while its owning window still shows it."""
import json
import os
import subprocess
import sys


def main():
    origin, title = sys.argv[1:3]
    env = dict(os.environ, TERN_PANE=origin, TERN_WINDOW_KEY="", TERN_WINDOW_SOCKET="")
    env.pop("TERN_CONTROL", None)
    if env.get("TERN_DAEMON_SOCKET"):
        env["TERN_PANE_SOCKET"] = env["TERN_DAEMON_SOCKET"]

    result = subprocess.run(["tern", "ctl", "state"], env=env, capture_output=True, text=True, timeout=4, check=True)
    value = json.loads(result.stdout)
    focused = value.get("focused") or {}
    if focused.get("label") != title:
        raise ValueError("Cockpit no longer owns window focus")
    if not any(item.get("id") == focused.get("id") for item in value.get("pips", [])):
        raise ValueError("Cockpit has no transient host")
    print(json.dumps({"ok": True}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        sys.exit(1)
