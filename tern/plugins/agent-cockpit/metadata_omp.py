"""Recorded OMP metadata for the exact process's own root session.

OMP appends to its transcript without holding it open, so an open descriptor is
only one source. OMP also records each terminal's current session file under
terminal-sessions/<pts>; that record is trusted only for this process's tty and
only when written during this process's lifetime (a reused pts keeps a stale
one). Failing both, the process's own `--resume <file>` argument names it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat

from metadata_common import clean, records
from metadata_usage import count, counters, fields, money, remember, scan

MAX_FDS = 512
MAX_TRANSCRIPTS = 32
HEADER_BYTES = 65536


def _session(path: Path) -> dict:
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            return {}
        with path.open("rb") as stream:
            data = stream.read(HEADER_BYTES)
        sessions = []
        for line in data.split(b"\n")[:-1]:
            try:
                value = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if isinstance(value, dict) and value.get("type") == "session":
                sessions.append(value)
        if len(sessions) != 1:
            return {}
        header = sessions[0]
        identity = header.get("id")
        if not isinstance(identity, str) or not identity or len(identity) > 200:
            return {}
        return header
    except (OSError, ValueError):
        return {}


def _capacity(model: str, agent: Path) -> int | None:
    """The context window OMP's own model catalog records for `provider/model`, if unambiguous."""
    provider, _, name = model.partition("/")
    if not provider or not name:
        return None
    try:
        connection = sqlite3.connect(f"file:{agent / 'models.db'}?mode=ro", uri=True, timeout=0.2)
        try:
            rows = connection.execute(
                "SELECT models FROM model_cache WHERE provider_id = ? OR provider_id LIKE ? ESCAPE '\\'",
                (provider, provider.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + ":%"),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    windows = set()
    for (raw,) in rows:
        try:
            models = json.loads(raw)
        except ValueError:
            continue
        for item in models if isinstance(models, list) else models.values() if isinstance(models, dict) else ():
            if isinstance(item, dict) and item.get("id") == name and count(item.get("contextWindow")):
                windows.add(item["contextWindow"])
    return windows.pop() if len(windows) == 1 and min(windows) > 0 else None


def _process_start(pid: int, proc_root: Path) -> float | None:
    try:
        fields = (proc_root / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        boot = next(int(line.split()[1]) for line in (proc_root / "stat").read_text().splitlines()
                    if line.startswith("btime "))
        return boot + int(fields[19]) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def _sessions_root(pid: int, proc_root: Path) -> Path:
    home = os.environ.get("HOME") or str(Path.home())
    try:
        for entry in (proc_root / str(pid) / "environ").read_bytes()[:65536].split(b"\0"):
            if entry.startswith(b"HOME="):
                home = entry[5:].decode("utf-8", "replace")
    except OSError:
        pass
    return Path(home) / ".omp" / "agent"


def _session_file(value: str, agent: Path) -> Path | None:
    path = Path(value)
    if not path.is_absolute() or path.suffix != ".jsonl":
        return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to((agent / "sessions").resolve(strict=True))
    except (OSError, ValueError):
        return None
    return resolved


def _breadcrumb(pid: int, proc_root: Path) -> tuple[Path, bytes] | None:
    """OMP's own per-terminal record of its current session, if this process wrote it."""
    try:
        tty = os.readlink(proc_root / str(pid) / "fd" / "0")
    except OSError:
        return None
    if not tty.startswith("/dev/pts/") or not tty[9:].isdigit():
        return None
    agent = _sessions_root(pid, proc_root)
    crumb = agent / "terminal-sessions" / ("pts-" + tty[9:])
    started = _process_start(pid, proc_root)
    try:
        info = crumb.stat()
        raw = crumb.read_bytes()[:16384]
    except OSError:
        return None
    # Process start is second-granular via btime; allow that skew, nothing more.
    if started is None or info.st_mtime < started - 2:
        return None
    lines = raw.decode("utf-8", "replace").splitlines()
    path = _session_file(lines[1], agent) if len(lines) > 1 else None
    return (path, raw) if path else None


def _resume_argument(pid: int, proc_root: Path) -> Path | None:
    try:
        argv = (proc_root / str(pid) / "cmdline").read_bytes()[:16384].split(b"\0")
    except OSError:
        return None
    args = [part.decode("utf-8", "replace") for part in argv if part]
    for index, arg in enumerate(args[1:-1], 1):
        if arg == "--resume":
            return _session_file(args[index + 1], _sessions_root(pid, proc_root))
        if arg.startswith("--resume="):
            return _session_file(arg[9:], _sessions_root(pid, proc_root))
    return None


def _open_transcripts(pid: int, proc_root: Path) -> set[Path] | None:
    paths = set()
    try:
        with os.scandir(proc_root / str(pid) / "fd") as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_FDS:
                    return None
                try:
                    target = os.readlink(entry.path)
                except OSError:
                    continue
                path = Path(target)
                if path.is_absolute() and path.suffix == ".jsonl":
                    paths.add(path)
                    if len(paths) > MAX_TRANSCRIPTS:
                        return None
        return paths
    except OSError:
        return None


def _text(content: object) -> str:
    if isinstance(content, str):
        return clean(content)
    if not isinstance(content, list):
        return ""
    parts = []
    size = 0
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = clean(part.get("text"))
        if text:
            parts.append(text)
            size += len(text)
            if size >= 300:
                break
    return clean(" ".join(parts))


def _usage(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    incoming, outgoing = value.get("input"), value.get("output")
    if not all(type(count) is int and count >= 0 for count in (incoming, outgoing)):
        return ""
    text = f"Latest provider response record: {incoming} uncached input / {outgoing} output tokens"
    for key, label in (("cacheRead", "cache read"), ("cacheWrite", "cache write")):
        count = value.get(key)
        if type(count) is int and count >= 0:
            text += f"; {count} {label}"
    return clean(text)


def _account(state: dict, record: dict, identity: str) -> None:
    kind = record.get("type")
    if kind == "session":
        if record.get("id") != identity or record.get("parentSession") or record.get("parentSessionId"):
            state["invalid"] = True
        return
    message = record.get("message")
    if kind == "model_usage":
        usage = record.get("usage")
        key = record.get("id")
    elif kind == "message" and isinstance(message, dict):
        if message.get("role") == "toolResult" and message.get("toolName") == "task":
            details = message.get("details")
            # Async task launch records have empty results and AgentProgress
            # IDs; settled records can repeat the same IDs in both arrays.
            for field in ("results", "progress"):
                agents = details.get(field) if isinstance(details, dict) else None
                if isinstance(agents, list):
                    for agent in agents:
                        if isinstance(agent, dict):
                            remember(state, "agents", agent.get("id"), True)
            return
        if message.get("role") != "assistant":
            return
        usage = message.get("usage")
        key = message.get("responseId") or record.get("id")
        snapshot = message.get("contextSnapshot")
        prompt = snapshot.get("promptTokens") if isinstance(snapshot, dict) else None
        state.pop("prompt", None)
        if count(prompt):
            state["prompt"] = prompt
        elif isinstance(usage, dict) and all(count(usage.get(name)) for name in ("input", "cacheRead", "cacheWrite")):
            state["prompt"] = usage["input"] + usage["cacheRead"] + usage["cacheWrite"]
    else:
        return
    values = counters(usage, ("input", "output", "cacheRead", "cacheWrite"))
    if values is None:
        state["missing_usage"] = True
        return
    cost = usage.get("cost")
    cost = cost.get("total") if isinstance(cost, dict) else None
    remember(state, "ledger", key, [values, cost if money(cost) else None])


def _session_usage(path: Path, identity: str) -> dict:
    state, coverage = scan("omp", path, identity, _account)
    if state.get("invalid"):
        return {}
    result = fields(state, coverage, "OMP root assistant + model_usage records; excludes child usage; input excludes cache; no live context/agent state")
    if result["session_cost"].startswith("Recorded session:"):
        result["session_cost"] = result["session_cost"].replace("Recorded session:", "Provider estimate:") + " (not billing)"
    return result

def _owned_advisor(path: Path, headers: dict[Path, dict]) -> bool:
    # Installed OMP advisor/transcript-recorder.ts reserves these names and
    # creates them at <owning-session-file minus .jsonl>/<advisor name>.
    # Advisors open a separate SessionManager without a parentSession header.
    # The exact storage owner must itself have a valid session header: a name
    # alone never excludes an otherwise independent open root.
    if path.name != "__advisor.jsonl" and not (
        path.name.startswith("__advisor.") and path.name.endswith(".jsonl")
    ):
        return False
    owner = Path(str(path.parent) + ".jsonl")
    return bool(headers[owner] if owner in headers else _session(owner))


def collect(pid: int, proc_root: Path = Path("/proc")) -> dict:
    """Never use cwd, terminal breadcrumbs, child processes, or newest-file guesses."""
    paths = _open_transcripts(pid, proc_root) or set()
    headers = {path: _session(path) for path in paths}
    roots = []
    for path, header in headers.items():
        # The root process also holds task and advisor transcripts open.
        if (header and not header.get("parentSession") and not header.get("parentSessionId")
                and not _owned_advisor(path, headers)):
            roots.append((path, header))
    crumb = None
    if len(roots) == 1:
        source = "OMP open root transcript"
    elif roots:
        return {}
    else:
        crumb = _breadcrumb(pid, proc_root)
        path = crumb[0] if crumb else _resume_argument(pid, proc_root)
        header = _session(path) if path else {}
        if not header or header.get("parentSession") or header.get("parentSessionId"):
            return {}
        roots = [(path, header)]
        source = "OMP terminal session record" if crumb else "OMP --resume argument"
    path, header = roots[0]
    identity = header["id"]
    accounting = _session_usage(path, identity)
    if not accounting:
        return {}
    result = {}
    for record in records(path):
        kind = record.get("type")
        if kind == "session":
            if record.get("id") != identity or record.get("parentSession") or record.get("parentSessionId"):
                return {}
            title = clean(record.get("title"), limit=120)
            if title and "title" not in result:
                result["title"] = title
        elif kind == "title":
            title = clean(record.get("title"), limit=120)
            if title:
                result["title"] = title
        elif kind == "model_change":
            model = clean(record.get("model"), limit=100)
            if model:
                result["model"] = model
        elif kind == "message":
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            text = _text(message.get("content"))
            if role == "user" and text:
                result["request"] = text
            elif role == "assistant":
                if text:
                    result["last_response"] = text
                model = clean(message.get("model"), limit=100)
                if model:
                    provider = clean(message.get("provider"), limit=100)
                    result["model"] = clean(f"{provider}/{model}" if provider and "/" not in model else model, limit=100)
                usage = _usage(message.get("usage"))
                if usage:
                    result["usage"] = usage
                else:
                    result.pop("usage", None)
        # Conversation records only: OMP also writes bookkeeping records when a session is restored.
        message = record.get("message")
        if kind == "message" and isinstance(message, dict) and message.get("role") in ("user", "assistant"):
            updated = clean(record.get("updatedAt") or record.get("timestamp"), limit=100)
            if updated:
                result["updated_at"] = updated
    # A session switch during the read must not leave stale attribution behind.
    current = _open_transcripts(pid, proc_root) or set()
    if current != paths or _session(path).get("id") != identity:
        return {}
    if crumb and _breadcrumb(pid, proc_root) != crumb:
        return {}
    result.update(session_id=identity, transcript_path=str(path), metadata_source=source + " · recorded metadata")
    numbers = accounting.get("usage_stats")
    window = _capacity(result.get("model", ""), _sessions_root(pid, proc_root)) if numbers is not None else None
    if window:
        numbers["capacity"] = window
        accounting["usage_source"] = clean(accounting["usage_source"] + "; window from OMP model catalog")
    result.update(accounting)
    return result
