"""Incremental JSONL accounting; persistent state contains only counters and hashes.

Each poll consumes at most 6 MiB, plus two 4 KiB identity checkpoints. A new or
rewritten file is indexed from byte zero; incomplete coverage is never a total.
Caches are disposable, versioned, per-user, bounded, and atomically replaced.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile

from metadata_common import clean

READ_BUDGET = 6 * 1024 * 1024
MAX_LINE = 1024 * 1024
MAX_IDENTITIES = 20000
MAX_CACHE = 8 * 1024 * 1024
VERSION = 3


def count(value: object) -> bool:
    return type(value) is int and 0 <= value <= 10**18


def money(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**12


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def counters(value: object, names: tuple[str, ...]) -> list | None:
    if not isinstance(value, dict):
        return None
    result = [value.get(name) for name in names]
    if not all(count(item) for item in result[:2]):
        return None
    return [item if count(item) else None for item in result]


def remember(state: dict, category: str, identity: object, value: object) -> bool:
    if not isinstance(identity, str) or not identity or len(identity) > 500:
        state["missing_identity" if category == "ledger" else "missing_agent_identity"] = True
        return False
    entries = state.setdefault(category, {})
    key = digest(identity)
    if key not in entries and len(entries) >= MAX_IDENTITIES:
        state["limited"] = True
        return False
    entries[key] = value
    return True


def new_state() -> dict:
    return {"ledger": {}, "agents": {}, "offset": 0, "skip": False}


def _checkpoint(stream, offset: int) -> str:
    stream.seek(max(0, offset - 4096))
    return digest(stream.read(min(4096, offset)))


def _cache_path(provider: str, path: Path, identity: str) -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return root / "tern" / "agent-cockpit" / "usage" / (digest(f"{provider}\0{path.absolute()}\0{identity}") + ".json")


def scan(provider: str, path: Path, identity: str, reduce) -> tuple[dict, str]:
    """Replay complete records once; return coverage at this file's observed EOF.

    Prefix and cursor fingerprints detect replacement/truncation and common
    in-place rewrites. Same-size modified files are always reindexed. Providers
    use append-only JSONL; arbitrary edits to old middle bytes during an append
    cannot be certified without rereading the entire file.
    """
    state = new_state()
    cache = _cache_path(provider, path, identity)
    try:
        with path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return state, "unavailable: transcript is not a regular file"
            source = [info.st_dev, info.st_ino]
            try:
                with cache.open("rb") as saved:
                    raw = saved.read(MAX_CACHE + 1)
                candidate = json.loads(raw) if len(raw) <= MAX_CACHE else {}
                offset = candidate.get("offset")
                if (candidate.get("version") == VERSION and candidate.get("source") == source
                        and count(offset) and offset <= info.st_size
                        and type(candidate.get("size")) is int and info.st_size >= candidate["size"]
                        and (info.st_size != candidate["size"] or info.st_mtime_ns == candidate.get("mtime"))
                        and candidate.get("prefix") == _checkpoint(stream, min(offset, 4096))
                        and candidate.get("checkpoint") == _checkpoint(stream, offset)
                        and isinstance(candidate.get("ledger"), dict)
                        and isinstance(candidate.get("agents"), dict)):
                    state = candidate
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            stream.seek(state["offset"])
            end = min(info.st_size, state["offset"] + READ_BUDGET)
            pending = False
            while stream.tell() < end:
                start = stream.tell()
                line = stream.readline(min(MAX_LINE + 1, end - start))
                if not line:
                    break
                if state.get("skip"):
                    state["offset"] = stream.tell()
                    state["skip"] = not line.endswith(b"\n")
                    continue
                if not line.endswith(b"\n"):
                    if len(line) > MAX_LINE:
                        # Attachments and tool output, not usage records: skip and disclose.
                        state["oversized"] = state.get("oversized", 0) + 1
                        state["skip"] = True
                        state["offset"] = stream.tell()
                        continue
                    # Retry from the record's start; never persist partial
                    # transcript bytes. A budget boundary is not writer lag.
                    pending = stream.tell() >= info.st_size
                    break
                state["offset"] = stream.tell()
                try:
                    entry = json.loads(line)
                    if isinstance(entry, dict):
                        reduce(state, entry, identity)
                    else:
                        state["damaged"] = True
                except (ValueError, UnicodeError):
                    state["damaged"] = True
            # Replacement or truncation while open must not publish old counters.
            current = path.stat()
            if ((current.st_dev, current.st_ino) != tuple(source)
                    or current.st_size < info.st_size
                    or (current.st_size == info.st_size and current.st_mtime_ns != info.st_mtime_ns)):
                return new_state(), "unavailable: transcript changed while reading"
            state.update(version=VERSION, source=source, size=info.st_size, mtime=info.st_mtime_ns,
                         prefix=_checkpoint(stream, min(state["offset"], 4096)),
                         checkpoint=_checkpoint(stream, state["offset"]))
            if state.get("invalid"):
                return state, "unavailable: conflicting session identity"
            if state.get("damaged") or state.get("limited"):
                coverage = "incomplete: malformed record or accounting identity limit"
            elif state["offset"] < info.st_size:
                coverage = (f"indexing: {state['offset']}/{info.st_size} bytes"
                            if info.st_size - state["offset"] > MAX_LINE or not pending
                            else "incomplete: waiting for complete JSONL record")
            else:
                coverage = "complete recorded file"
                if state.get("oversized"):
                    coverage += f"; {state['oversized']} oversized records (>1 MiB) skipped"
            try:
                cache.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                encoded = json.dumps(state, separators=(",", ":")).encode()
                if len(encoded) <= MAX_CACHE:
                    fd, temporary = tempfile.mkstemp(prefix=".usage-", dir=cache.parent)
                    try:
                        with os.fdopen(fd, "wb") as saved:
                            saved.write(encoded)
                        os.replace(temporary, cache)
                    finally:
                        try:
                            os.unlink(temporary)
                        except FileNotFoundError:
                            pass
            except OSError:
                coverage += "; cache unavailable (bounded reindex each poll)"
            return state, coverage
    except (OSError, ValueError):
        return state, "unavailable: transcript unreadable"


def totals(state: dict) -> tuple[str, str]:
    ledger = state.get("ledger", {})
    if not ledger:
        return "Unavailable: no attributable usage records", "Unavailable: no reported cost records"
    values = list(ledger.values())
    counts = [sum(value[0][index] for value in values if value[0][index] is not None) for index in range(4)]
    tokens = f"Recorded session: {counts[0]} input / {counts[1]} output tokens"
    for index, label in ((2, "cache read"), (3, "cache write")):
        if all(value[0][index] is not None for value in values):
            tokens += f"; {counts[index]} {label}"
        else:
            tokens += f"; {label} unavailable"
    costs = [value[1] for value in values]
    cost = (f"Recorded session: ${sum(costs):.6f} USD"
            if all(money(value) for value in costs) else "Unavailable: not all usage records report cost")
    if state.get("missing_usage") or state.get("missing_identity"):
        tokens = "Unavailable: some provider messages lack attributable usage"
        cost = "Unavailable: some provider messages lack attributable usage/cost"
    return clean(tokens), clean(cost)


def stats(state: dict) -> dict:
    """Numeric counterparts of a complete ledger, for meters; absent when not attributable."""
    result = {}
    ledger = list(state.get("ledger", {}).values())
    if ledger and not (state.get("missing_usage") or state.get("missing_identity")):
        for index, name in enumerate(("input", "output", "cache_read", "cache_write")):
            if all(value[0][index] is not None for value in ledger):
                result[name] = sum(value[0][index] for value in ledger)
        costs = [value[1] for value in ledger]
        if all(money(value) for value in costs):
            result["cost"] = float(sum(costs))
    if count(state.get("prompt")):
        result["context"] = state["prompt"]
        if count(state.get("capacity")) and state["capacity"]:
            result["capacity"] = state["capacity"]
    if state.get("agents") and not state.get("missing_agent_identity"):
        result["agents"] = len(state["agents"])
    return result


def fields(state: dict, coverage: str, source: str) -> dict:
    complete = coverage.startswith("complete recorded file")
    tokens, cost = totals(state) if complete else (f"Unavailable: {coverage}", f"Unavailable: {coverage}")
    context = ("Unavailable: no recorded request context; capacity not reported"
               if complete else f"Unavailable: {coverage}")
    prompt = state.get("prompt")
    if complete and count(prompt):
        capacity = state.get("capacity")
        context = f"Last recorded request: {prompt} input tokens"
        context += f" / {capacity} capacity ({100 * prompt / capacity:.1f}%)" if count(capacity) and capacity else "; capacity not reported"
    agents = state.get("agents", {})
    subagents = (f"{len(agents)} recorded unique agents (not live)" if complete and agents
                 else "Unavailable: no recorded agent identities" if complete else f"Unavailable: {coverage}")
    if complete and state.get("missing_agent_identity"):
        subagents = (f"{len(agents)} recorded unique agents (incomplete identities; not live)"
                     if agents else "Unavailable: some task agent identities missing")
    result = {key: clean(value) for key, value in {
        "session_tokens": tokens, "session_cost": cost, "context_usage": context,
        "subagents": subagents, "usage_source": f"{source} · {coverage}",
    }.items()}
    if complete:
        result["usage_stats"] = stats(state)
    return result
