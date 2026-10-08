#!/usr/bin/python3
"""Use packaged transcript collectors with local fixes at their CLI boundaries."""

import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time


def codex_rpc_request(proc, request_id, method, params=None, timeout=8):
    proc.stdin.write(json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    deadline = time.monotonic() + timeout
    line = bytearray()
    # Read directly from the pipe, leaving subsequent messages in the pipe.
    # TextIOWrapper.readline() can prefetch notifications AND the response;
    # select() then waits for new bytes despite the response already being buffered.
    while time.monotonic() < deadline:
        if not select.select([proc.stdout], [], [], min(0.25, max(0, deadline - time.monotonic())))[0]:
            continue
        byte = os.read(proc.stdout.fileno(), 1)
        if not byte:
            raise RuntimeError("Codex app-server closed stdout during " + method)
        if byte != b"\n":
            line.extend(byte)
            continue
        try:
            message = json.loads(line)
        except ValueError:
            line.clear()
            continue
        line.clear()
        if message.get("id") == request_id:
            return message
    raise TimeoutError(method)


def claude_login(read_login, cache_dir, claude_dir):
    login = read_login(claude_dir)
    if not login[0] or login[1] <= 0 or login[1] > time.time() * 1000:
        return login
    # Claude owns token rotation and credential writes. Let its initialization
    # renew the expired token without prompts, model requests, hooks, or MCP.
    cli = shutil.which("claude", path=os.pathsep.join((
        os.environ.get("PATH", ""), str(Path.home() / ".local/share/mise/shims"),
        str(Path.home() / ".local/bin"), str(Path.home() / ".npm-global/bin"),
    )))
    if not cli:
        return login
    lock_path = cache_dir / "claude-renew.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        login = read_login(claude_dir)
        if login[1] > time.time() * 1000:
            return login
        env = os.environ.copy()
        env["CLAUDE_CONFIG_DIR"] = str(claude_dir)
        try:
            with tempfile.TemporaryDirectory(prefix="omarchy-claude-renew-") as cwd:
                subprocess.run([
                    cli, "--init-only", "--setting-sources", "",
                    "--settings", '{"disableAllHooks":true}',
                    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                ], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25, check=True)
        except (OSError, subprocess.SubprocessError):
            # The upstream collector keeps cached limits and reports expired auth.
            pass
        return read_login(claude_dir)


def main():
    agent = sys.argv.pop(1)
    if agent not in ("claude", "codex"):
        raise SystemExit("Expected claude or codex")
    path = Path(os.environ.get("OMARCHY_PATH") or "/usr/share/omarchy") / "bin" / ("omarchy-agent-usage-" + agent)
    loader = importlib.machinery.SourceFileLoader("packaged_" + agent, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    collector = importlib.util.module_from_spec(spec)
    loader.exec_module(collector)
    # Keep transcript parsing, cache contracts, and limit normalization upstream.
    # These two replacements are limited to the verified defective CLI boundaries.
    if agent == "codex":
        collector.rpc_request = codex_rpc_request
    else:
        original_login = collector.oauth_login
        collector.oauth_login = lambda directory: claude_login(original_login, collector.cache_root(), directory)
    collector.main()


if __name__ == "__main__":
    main()
