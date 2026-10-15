#!/usr/bin/env python3
"""Read bounded local metadata after exact pane/process/session attribution."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

import metadata_claude
import metadata_codex
import metadata_omp
from metadata_common import clean, read_object

MAX_INPUT = 65536
MAX_PROCESS_OUTPUT = 65536
MAX_PANES = 32
RUNTIME_SECONDS = 3.0
PROCESS_SECONDS = 0.5
PROC_ROOT = Path("/proc")
_ENV_KEYS = {"HOME", "XDG_STATE_HOME", "TERN_PANE", "TERN_PANE_SOCKET", "TERN_DAEMON_SOCKET"}
_FIELDS = {
    "session_id": 200, "title": 120, "model": 100, "request": 300,
    "last_response": 300, "git_branch": 300, "updated_at": 100,
    "usage": 300, "metadata_source": 200, "transcript_path": 4096,
}
_LIFECYCLE_EVENTS = {
    "SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "PostToolUseFailure", "PermissionRequest", "Notification", "Stop", "SessionEnd",
}


class CollectionTimeout(Exception):
    pass


def _read(path: Path, limit: int) -> bytes:
    try:
        with path.open("rb") as stream:
            value = stream.read(limit + 1)
        return value if len(value) <= limit else b""
    except OSError:
        return b""


def _started(pid: int, proc_root: Path) -> str:
    raw = _read(proc_root / str(pid) / "stat", 8192)
    try:
        fields = raw.rsplit(b")", 1)[1].split()
        return fields[19].decode("ascii") if fields[19].isdigit() and fields[0] not in (b"Z", b"X") else ""
    except (IndexError, UnicodeError):
        return ""


def _environment(pid: int, proc_root: Path) -> dict:
    selected = {}
    for entry in _read(proc_root / str(pid) / "environ", 65536).split(b"\0"):
        key, separator, value = entry.partition(b"=")
        if separator and key.decode("utf-8", "replace") in _ENV_KEYS:
            selected[key.decode()] = value.decode("utf-8", "replace")
    return selected


def _socket(environ: dict) -> str:
    return environ.get("TERN_PANE_SOCKET") or environ.get("TERN_DAEMON_SOCKET") or ""


def _provider(pid: int, provider: str, proc_root: Path) -> bool:
    raw = _read(proc_root / str(pid) / "cmdline", 16384)
    argv = [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]
    if not argv:
        return False
    if provider == "codex" and any(arg in ("app-server", "--managed-daemon") for arg in argv[1:]):
        return False
    if provider == "claude" and any(arg == "--agent-id" or arg.startswith("--agent-id=") for arg in argv[1:]):
        return False
    executable = Path(argv[0]).name
    if executable == provider:
        return True
    if executable in ("node", "bun", "nodejs") and len(argv) > 1:
        script = Path(argv[1])
        return script.name in (provider, provider + ".js", provider + ".mjs") or (
            provider == "claude" and script.name == "cli.js" and "claude-code" in script.parts
        )
    return False


def _query_process(pane: str, environ: dict, deadline: float) -> dict:
    remaining = min(PROCESS_SECONDS, deadline - time.monotonic())
    if remaining <= 0:
        return {}
    child_env = dict(environ)
    namespace = _socket(environ)
    if namespace:
        # The ctl client scopes on PANE_SOCKET; DAEMON_SOCKET alone does not route it.
        child_env["TERN_PANE_SOCKET"] = namespace
    process = None
    try:
        process = subprocess.Popen(
            ["tern", "process", pane, "--json"], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=child_env,
        )
        end = time.monotonic() + remaining
        chunks = []
        size = 0
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                wait = end - time.monotonic()
                if wait <= 0 or not selector.select(wait):
                    return {}
                chunk = os.read(process.stdout.fileno(), min(8192, MAX_PROCESS_OUTPUT + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_PROCESS_OUTPUT:
                    return {}
        if process.wait(timeout=max(0.001, end - time.monotonic())) != 0:
            return {}
        value = json.loads(b"".join(chunks))
        return value if isinstance(value, dict) and str(value.get("pane")) == pane else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()


def _hook(provider: str, pane: str, pid: int, started: str, environ: dict, proc_root: Path) -> dict:
    from hook_record import record_filename

    target = _environment(pid, proc_root)
    namespace = _socket(environ) or _socket(target)
    if target.get("TERN_PANE") != pane or _socket(target) != namespace:
        return {}
    home = Path(target.get("HOME") or str(Path.home()))
    state = Path(target.get("XDG_STATE_HOME") or str(home / ".local" / "state"))
    record = read_object(state / "tern" / "agent-cockpit" / "sessions" / record_filename(provider, pane))
    if not (
        record.get("provider") == provider and record.get("pane") == pane
        and type(record.get("pid")) is int and record["pid"] == pid
        and record.get("started") == started and record.get("socket", "") == namespace
    ):
        return {}
    identity = record.get("session_id")
    config = record.get("config_dir")
    transcript = record.get("transcript_path")
    if not isinstance(identity, str) or not identity or len(identity) > 200:
        return {}
    if not isinstance(config, str) or not Path(config).is_absolute() or len(config) > 4096:
        return {}
    if transcript is not None and (not isinstance(transcript, str) or not Path(transcript).is_absolute() or len(transcript) > 4096):
        return {}
    return record


def _lifecycle(record: dict) -> dict:
    """Only an exact owner's hook record can establish a live phase."""
    value = record.get("lifecycle")
    if not isinstance(value, dict):
        return {}
    status, event, observed = (value.get(name) for name in ("status", "event", "observed_at"))
    activity = value.get("activity")
    if status not in ("working", "waiting_input", "idle", "exited", "unknown"):
        return {}
    if not isinstance(event, str) or event not in _LIFECYCLE_EVENTS:
        return {}
    if not isinstance(activity, str) or len(activity) > 300:
        return {}
    if not isinstance(observed, str) or len(observed) > 40 or not observed.endswith("Z"):
        return {}
    try:
        timestamp = datetime.fromisoformat(observed[:-1] + "+00:00")
    except ValueError:
        return {}
    if timestamp.tzinfo != timezone.utc:
        return {}
    return {"status": status, "activity": clean(activity, 300), "event": event, "observed_at": observed}


def _row(item: dict, environ: dict, proc_root: Path, deadline: float) -> dict:
    pane, provider = item.get("pane"), item.get("provider")
    if not isinstance(pane, str) or not pane or len(pane) > 200 or pane.startswith("-") or any(ord(char) < 32 for char in pane):
        return {}
    if provider not in ("omp", "claude", "codex"):
        return {}
    snapshot = _query_process(pane, environ, deadline)
    pids = set()
    for name in ("foreground", "child"):
        process = snapshot.get(name)
        pid = process.get("pid") if isinstance(process, dict) else None
        if type(pid) is int and pid > 0 and _provider(pid, provider, proc_root):
            pids.add(pid)
    if len(pids) != 1:
        return {}
    pid = pids.pop()
    started = _started(pid, proc_root)
    if not started:
        return {}
    record, result = None, {}
    if provider == "omp":
        result = metadata_omp.collect(pid, proc_root)
    else:
        record = _hook(provider, pane, pid, started, environ, proc_root)
        if not record:
            return {}
        adapter = metadata_claude if provider == "claude" else metadata_codex
        transcript = Path(record["transcript_path"]) if record.get("transcript_path") else None
        result = adapter.collect(record["session_id"], transcript, Path(record["config_dir"]))
        if not result and (transcript is None or not transcript.exists()):
            # SessionStart can precede transcript creation; no transcript freshness
            # is used to infer activity or the session's live phase.
            name = "Claude" if provider == "claude" else "Codex"
            result = {
                "session_id": record["session_id"],
                "metadata_source": f"{name} SessionStart hook · exact live process",
            }
    if _started(pid, proc_root) != started or not _provider(pid, provider, proc_root):
        return {}
    if record and _hook(provider, pane, pid, started, environ, proc_root) != record:
        return {}
    output = {field: clean(result.get(field), limit) for field, limit in _FIELDS.items() if clean(result.get(field), limit)}
    lifecycle = _lifecycle(record) if provider == "claude" and record else {}
    if lifecycle:
        output["session_id"] = record["session_id"]
        output["lifecycle"] = lifecycle
    return output


def collect(payload: object, environ: dict | None = None, proc_root: Path = PROC_ROOT) -> dict:
    rows = {}
    if not isinstance(payload, dict) or not isinstance(payload.get("panes"), list):
        return {"rows": rows}
    environ = dict(os.environ if environ is None else environ)
    deadline = time.monotonic() + RUNTIME_SECONDS
    try:
        for item in payload["panes"][:MAX_PANES]:
            if time.monotonic() >= deadline:
                break
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not isinstance(key, str) or not key or len(key) > 300 or key in rows:
                continue
            try:
                result = _row(item, environ, proc_root, deadline)
            except (OSError, ValueError, ImportError):
                continue
            if result:
                rows[key] = result
    except CollectionTimeout:
        pass
    return {"rows": rows}


def main() -> None:
    def expired(_signum, _frame):
        raise CollectionTimeout()

    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, RUNTIME_SECONDS)
    result = {"rows": {}}
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) <= MAX_INPUT:
            result = collect(json.loads(raw))
    except (ValueError, UnicodeError, CollectionTimeout):
        pass
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
