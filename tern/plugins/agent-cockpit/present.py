#!/usr/bin/env python3
"""Place the exact host-owned cockpit without the defective window ID bridge."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time


def run(args: tuple[str, ...], env: dict[str, str], deadline: float) -> subprocess.CompletedProcess[str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Cockpit presentation exceeded its deadline")
    return subprocess.run(["tern", *args], env=env, check=True, capture_output=True, text=True,
                          timeout=min(1.5, remaining))


def ownership(token: str, pane: str, env: dict[str, str], deadline: float) -> str:
    snapshot = json.loads(run(("ls", "--json"), env, deadline).stdout)
    blocks = [(session, tab, block) for session in snapshot.get("sessions", [])
              for tab in session.get("tabs", []) for block in tab.get("blocks", [])]
    owned = [str(block["id"]) for _, _, block in blocks
             if block.get("title") == "Agent Cockpit · " + token and block.get("exited") is None]
    if owned != [pane]:
        raise ValueError("The exact host-owned cockpit is no longer available")
    focused = [str(block["id"]) for session, tab, block in blocks
               if session.get("shown") and tab.get("shown") and block.get("focused")]
    if len(focused) != 1:
        raise ValueError("The native window has no unique focused owner")
    return focused[0]


def main() -> int:
    token, pane = sys.argv[1:3]
    if not token.isascii() or not token.replace("-", "").isalnum() or len(token) > 128 or not pane.isdecimal():
        raise ValueError("Expected the cockpit control token and host pane")
    # BlockCx.pane is the daemon's native id, not a window's packed remote id.
    # TERN_PANE selects its owning window, including legacy opaque window keys.
    env = dict(os.environ, TERN_PANE=pane, TERN_WINDOW_KEY="", TERN_WINDOW_SOCKET="")
    env.pop("TERN_CONTROL", None)
    socket = env.get("TERN_DAEMON_SOCKET") or env.get("TERN_PANE_SOCKET")
    if not socket:
        socket = str(Path(env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "tern/daemon.sock")
    env["TERN_PANE_SOCKET"] = env["TERN_DAEMON_SOCKET"] = socket
    env["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + env.get("PATH", "")
    deadline = time.monotonic() + 4
    owner = ownership(token, pane, env, deadline)
    run(("pip", pane, "--over", owner), env, deadline)
    # Closing the carrier or choosing another pane cancels late presentation.
    if ownership(token, pane, env, deadline) not in (owner, pane):
        raise ValueError("Cockpit presentation was superseded by a newer selection")
    run(("focus", pane), env, deadline)
    print(json.dumps({"pane": pane, "window": ""}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (IndexError, OSError, ValueError, subprocess.SubprocessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(detail, file=sys.stderr)
        sys.exit(1)
