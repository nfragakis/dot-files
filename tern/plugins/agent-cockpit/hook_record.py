#!/usr/bin/env python3
"""Record an exact SessionStart owner, silently; never inspect provider auth files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import stat
import sys


INPUT_LIMIT = 65536
RECORD_LIMIT = 16384
PROC_LIMIT = 16384
ANCESTOR_LIMIT = 64
ENV_KEYS = (
    "HOME", "XDG_STATE_HOME", "TERN_PANE", "TERN_PANE_SOCKET", "TERN_DAEMON_SOCKET",
    "CLAUDE_CONFIG_DIR", "CODEX_HOME", "CODEX_THREAD_ID",
)


def record_filename(provider: str, pane: str) -> str:
    if provider not in ("claude", "codex"):
        raise ValueError("unsupported provider")
    return f"{provider}-{hashlib.sha256(pane.encode('utf-8')).hexdigest()}.json"


def _text(value: object, limit: int) -> str:
    if not isinstance(value, str) or not value or len(value) > limit:
        return ""
    if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return ""
    return value


def _path(value: object, home: Path) -> Path | None:
    text = _text(value, 4096)
    if text == "~" or text.startswith("~/"):
        text = str(home) + text[1:]
    path = Path(text) if text else None
    return path if path is not None and path.is_absolute() else None


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("oversized process record")
    return data


def process_stat(pid: int, proc: Path = Path("/proc")) -> tuple[int, str]:
    """Return parent PID and field 22 without splitting the parenthesized comm."""
    data = _read(proc / str(pid) / "stat", 4096).decode("utf-8")
    opening, closing = data.find("("), data.rfind(")")
    if opening < 1 or closing <= opening or int(data[:opening].strip()) != pid:
        raise ValueError("invalid process identity")
    fields = data[closing + 1:].split()
    if len(fields) < 20 or fields[0] == "Z" or not fields[19].isdigit():
        raise ValueError("unavailable process identity")
    parent = int(fields[1])
    if parent < 0:
        raise ValueError("invalid parent")
    return parent, fields[19]

def _provider_process(provider: str, argv: list[str], executable: str) -> bool:
    executable_path = Path(executable.removesuffix(" (deleted)"))
    executable = executable_path.name
    if executable == provider:
        return True
    if (provider == "claude" and executable_path.parent.name == "versions"
            and executable_path.parent.parent.name == "claude"
            and argv and Path(argv[0]).name == "claude"):
        return True
    if executable not in ("node", "nodejs", "bun") or len(argv) < 2:
        return False
    script = Path(argv[1])
    if provider == "claude":
        return script.name == "claude" or (
            script.name == "cli.js" and "@anthropic-ai" in script.parts and "claude-code" in script.parts
        )
    return script.name == "codex.js" and "@openai" in script.parts and "codex" in script.parts


def provider_owner(provider: str, parent: int, proc: Path = Path("/proc")) -> tuple[int, str] | None:
    """Use ancestry, not argv mentions, cwd, newest files, or a hook shell PID."""
    seen: set[int] = set()
    owner = None
    for _ in range(ANCESTOR_LIMIT):
        if parent <= 1:
            return owner
        if parent in seen:
            return None
        seen.add(parent)
        pid = parent
        parent, started = process_stat(pid, proc)
        raw = _read(proc / str(pid) / "cmdline", PROC_LIMIT)
        if not raw or not raw.endswith(b"\0"):
            return None
        argv = [part.decode("utf-8") for part in raw[:-1].split(b"\0")]
        # A managed shared server inherits its FIRST client's pane. Even a
        # matching CODEX_THREAD_ID is not evidence of a later TUI's ownership.
        if provider == "codex" and (
                any(arg in ("app-server", "--managed-daemon") for arg in argv[1:])
                or Path(argv[0]).name == "codex-app-server"):
            return None
        # Unrelated ancestors (notably user systemd) may deny /proc/PID/exe
        # reads. Only executable candidates need positive provider validation.
        if Path(argv[0]).name not in (provider, "node", "nodejs", "bun"):
            continue
        executable = os.readlink(proc / str(pid) / "exe")
        if provider == "codex" and Path(executable.removesuffix(" (deleted)")).name == "codex-app-server":
            return None
        if _provider_process(provider, argv, executable):
            if provider == "claude":
                return pid, started
            if owner is None:
                owner = (pid, started)
    return None


def _private_directory(state: Path) -> int:
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = os.open(state, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        info = os.fstat(current)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise ValueError("unsafe state directory")
        for name in ("tern", "agent-cockpit", "sessions"):
            try:
                os.mkdir(name, mode=0o700, dir_fd=current)
            except FileExistsError:
                pass
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=current)
            try:
                info = os.fstat(child)
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                    raise ValueError("unsafe record directory")
                os.fchmod(child, 0o700)
            except BaseException:
                os.close(child)
                raise
            os.close(current)
            current = child
        return current
    except BaseException:
        os.close(current)
        raise


def record(provider: str, payload: object, environ: dict[str, str], *,
           parent: int | None = None, proc: Path = Path("/proc")) -> Path | None:
    if provider not in ("claude", "codex") or not isinstance(payload, dict):
        return None
    if payload.get("hook_event_name") != "SessionStart" or payload.get("agent_id"):
        return None
    pane = _text(environ.get("TERN_PANE"), 512)
    namespace = _text(environ.get("TERN_PANE_SOCKET") or environ.get("TERN_DAEMON_SOCKET"), 4096)
    session = _text(payload.get("session_id"), 512)
    if not pane or not namespace or not session:
        return None
    if provider == "codex" and environ.get("CODEX_THREAD_ID") not in (None, "", session):
        return None
    home = Path(environ.get("HOME") or Path.home())
    if not home.is_absolute():
        return None
    key, default = ("CLAUDE_CONFIG_DIR", ".claude") if provider == "claude" else ("CODEX_HOME", ".codex")
    config = _path(environ.get(key) or str(home / default), home)
    state = _path(environ.get("XDG_STATE_HOME") or str(home / ".local/state"), home)
    if config is None or state is None:
        return None
    transcript = payload.get("transcript_path")
    transcript_path = _path(transcript, home) if transcript not in (None, "") else None
    if transcript not in (None, "") and transcript_path is None:
        return None
    owner = provider_owner(provider, os.getppid() if parent is None else parent, proc)
    if owner is None:
        return None
    pid, started = owner
    value = {"provider": provider, "pane": pane, "pid": pid, "started": started,
             "session_id": session, "config_dir": str(config), "socket": namespace}
    if transcript_path is not None:
        value["transcript_path"] = str(transcript_path)
    data = (json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > RECORD_LIMIT:
        return None
    directory = _private_directory(state)
    temporary = f".record-{os.getpid()}-{secrets.token_hex(8)}"
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=directory)
        created = True
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            # Recheck PID reuse/exits after preparing the complete private record.
            if process_stat(pid, proc)[1] != started:
                return None
            os.replace(temporary, record_filename(provider, pane),
                       src_dir_fd=directory, dst_dir_fd=directory)
        return state / "tern/agent-cockpit/sessions" / record_filename(provider, pane)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        finally:
            os.close(directory)


def main(argv: list[str] | None = None, stream=None, environ: dict[str, str] | None = None) -> int:
    try:
        args = sys.argv[1:] if argv is None else argv
        if len(args) != 1 or args[0] not in ("claude", "codex"):
            return 0
        data = (sys.stdin.buffer if stream is None else stream).read(INPUT_LIMIT + 1)
        if len(data) > INPUT_LIMIT:
            return 0
        payload = json.loads(data)
        selected = {key: os.environ.get(key, "") for key in ENV_KEYS} if environ is None else environ
        record(args[0], payload, selected)
    except Exception:
        pass
    return 0


def _expired(_signum, _frame) -> None:
    raise TimeoutError("hook deadline")


if __name__ == "__main__":
    # Bound even a producer that never closes stdin. SessionStart must not hold
    # up normal provider launch, and every failure remains silent and successful.
    signal.signal(signal.SIGALRM, _expired)
    signal.setitimer(signal.ITIMER_REAL, 2.0)
    raise SystemExit(main())
