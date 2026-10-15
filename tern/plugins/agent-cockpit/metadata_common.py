"""Bounded, read-only provider metadata I/O; never scan complete conversation history."""
from __future__ import annotations

import json
from pathlib import Path
import re

WINDOW = 512 * 1024


def clean(value: object, limit: int = 300) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:max(0, limit - 1)] + ("…" if limit > 0 else "")


def read_object(path: Path, limit: int = 65536) -> dict:
    try:
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            return {}
        value = json.loads(data)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def records(path: Path):
    """Yield complete JSONL records from nonoverlapping header/tail windows."""
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, 2)
            stream.seek(0)
            first = stream.read(size if size <= 2 * WINDOW else WINDOW)
            chunks = [first]
            if size > 2 * WINDOW:
                offset = size - WINDOW
                stream.seek(offset - 1)
                previous = stream.read(1)
                tail = stream.read(WINDOW)
                if previous != b"\n":
                    tail = tail.partition(b"\n")[2]
                chunks.append(tail)
            for chunk in chunks:
                # A writer may be between writes; its incomplete final record is not evidence.
                for line in chunk.split(b"\n")[:-1]:
                    try:
                        value = json.loads(line)
                    except (ValueError, UnicodeError):
                        continue
                    if isinstance(value, dict):
                        yield value
    except OSError:
        return
