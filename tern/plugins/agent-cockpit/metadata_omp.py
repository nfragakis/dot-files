"""Recorded OMP metadata from the exact process's unique open root session."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from metadata_common import clean, records

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


def collect(pid: int, proc_root: Path = Path("/proc")) -> dict:
    """Never use cwd, terminal breadcrumbs, child processes, or newest-file guesses."""
    paths = _open_transcripts(pid, proc_root)
    if not paths:
        return {}
    roots = []
    for path in paths:
        header = _session(path)
        # OMP keeps task logs open in the root process too. They are not the pane session.
        if header and not header.get("parentSession") and not header.get("parentSessionId"):
            roots.append((path, header))
    if len(roots) != 1:
        return {}
    path, header = roots[0]
    identity = header["id"]
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
        updated = clean(record.get("updatedAt") or record.get("timestamp"), limit=100)
        if updated:
            result["updated_at"] = updated
    # A session switch during the read must not leave stale attribution behind.
    current = _open_transcripts(pid, proc_root)
    if current != paths or _session(path).get("id") != identity:
        return {}
    result.update(session_id=identity, transcript_path=str(path), metadata_source="OMP open root transcript · recorded metadata")
    return result
