"""Read recorded Codex metadata for an already-attributed thread ID."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from metadata_common import clean, records


_THREAD_FIELDS = (
    "id", "rollout_path", "name", "title", "model", "git_branch",
    "updated_at_ms", "updated_at",
)


def _database_order(path: Path) -> tuple[int, str]:
    # Prefer the current schema revision, not the newest session or file mtime.
    revision = path.stem.removeprefix("state_")
    return (int(revision) if revision.isdecimal() else -1, path.name)


def _thread(session_id: str, config_dir: Path) -> dict:
    try:
        databases = sorted(config_dir.glob("state*.sqlite"), key=_database_order, reverse=True)
    except OSError:
        return {}
    for path in databases:
        connection = None
        try:
            # immutable=1 would hide committed metadata still in the live WAL.
            connection = sqlite3.connect(
                path.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.05,
            )
            columns = {row[1] for row in connection.execute('PRAGMA table_info("threads")')}
            if "id" not in columns:
                continue
            fields = [field for field in _THREAD_FIELDS if field in columns]
            projection = ", ".join('"' + field + '"' for field in fields)
            rows = connection.execute(
                f'SELECT {projection} FROM "threads" WHERE "id" = ? LIMIT 2',
                (session_id,),
            ).fetchall()
            if len(rows) == 1 and rows[0][fields.index("id")] == session_id:
                return dict(zip(fields, rows[0]))
        except (OSError, sqlite3.Error, ValueError):
            continue
        finally:
            if connection is not None:
                connection.close()
    return {}


def _timestamp(value: object, *, milliseconds: bool = False) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        try:
            if value < 0:
                return ""
            instant = datetime.fromtimestamp(value / 1000 if milliseconds else value, timezone.utc)
            return instant.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except (OverflowError, OSError, ValueError):
            return ""
    value = clean(value, limit=100)
    if value:
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                return value
        except ValueError:
            pass
    return ""


def _newer(candidate: str, existing: str) -> bool:
    if not candidate:
        return not existing
    if not existing:
        return True
    return datetime.fromisoformat(candidate.replace("Z", "+00:00")) >= datetime.fromisoformat(
        existing.replace("Z", "+00:00"),
    )


def _latest(existing: str, candidate: str) -> str:
    return candidate if candidate and _newer(candidate, existing) else existing


def _message(payload: dict) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    text = []
    remaining = 300
    for part in content:
        if not isinstance(part, dict) or part.get("type") not in ("input_text", "output_text", "text"):
            continue
        value = clean(part.get("text"), limit=remaining)
        if value:
            text.append(value)
            remaining -= len(value) + 1
            if remaining <= 0:
                break
    return clean(" ".join(text))


def _usage(payload: dict) -> str:
    info = payload.get("info")
    usage = info.get("last_token_usage") if isinstance(info, dict) else None
    if not isinstance(usage, dict):
        return ""
    incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
    if not all(type(value) is int and value >= 0 for value in (incoming, outgoing)):
        return ""
    # These are per-model-call counts; bounded transcript slices cannot supply totals.
    return clean(f"Last model call: {incoming} in / {outgoing} out")


def _rollout(session_id: str, path: Path) -> tuple[dict, dict]:
    details: dict = {}
    field_times: dict = {}
    validated = False
    try:
        for record in records(path):
            payload = record.get("payload")
            kind = record.get("type")
            if kind == "session_meta":
                if not isinstance(payload, dict):
                    return {}, {}
                identities = [payload[key] for key in ("id", "session_id") if key in payload]
                if not identities or any(identity != session_id for identity in identities):
                    return {}, {}
                validated = True
            if not isinstance(payload, dict):
                continue
            stamp = _timestamp(record.get("timestamp"))
            if kind == "session_meta":
                stamp = stamp or _timestamp(payload.get("timestamp"))
            details["updated_at"] = _latest(details.get("updated_at", ""), stamp)
            if kind == "session_meta":
                git = payload.get("git")
                branch = clean(git.get("branch")) if isinstance(git, dict) else ""
                if branch:
                    details["git_branch"] = branch
                    field_times["git_branch"] = stamp
            elif kind == "turn_context":
                model = clean(payload.get("model"), limit=100)
                if model:
                    details["model"] = model
                    field_times["model"] = stamp
            elif kind == "response_item" and payload.get("type") == "message":
                role = payload.get("role")
                if role in ("user", "assistant"):
                    text = _message(payload)
                    if text:
                        details["request" if role == "user" else "last_response"] = text
            elif kind == "event_msg":
                event = payload.get("type")
                if event in ("user_message", "agent_message", "task_complete"):
                    value = payload.get("last_agent_message" if event == "task_complete" else "message")
                    text = clean(value)
                    if text:
                        details["request" if event == "user_message" else "last_response"] = text
                elif event == "token_count":
                    usage = _usage(payload)
                    if usage:
                        details["usage"] = usage
    except (OSError, ValueError):
        return {}, {}
    if not validated:
        return {}, {}
    details = {key: value for key, value in details.items() if value}
    details["session_id"] = session_id
    details["transcript_path"] = str(path)
    return details, field_times


def collect(session_id: str, transcript_path: Path | None, config_dir: Path) -> dict:
    """Collect metadata by exact ID, without deriving ownership or live status."""
    if not isinstance(session_id, str) or not session_id:
        return {}
    thread = _thread(session_id, config_dir)
    details: dict = {}
    database_time = _timestamp(thread.get("updated_at_ms"), milliseconds=True) or _timestamp(
        thread.get("updated_at"),
    )
    if thread:
        details["session_id"] = session_id
        for key, value in (
            ("title", clean(thread.get("name"), limit=120) or clean(thread.get("title"), limit=120)),
            ("model", clean(thread.get("model"), limit=100)),
            ("git_branch", clean(thread.get("git_branch"))),
            ("updated_at", database_time),
        ):
            if value:
                details[key] = value

    paths = [transcript_path] if transcript_path is not None else []
    rollout_path = thread.get("rollout_path")
    if isinstance(rollout_path, str) and rollout_path and "\x00" not in rollout_path:
        path = Path(rollout_path)
        if not path.is_absolute():
            path = config_dir / path
        if path not in paths:
            paths.append(path)
    for path in paths:
        rollout, field_times = _rollout(session_id, path)
        if not rollout:
            continue
        for key, value in rollout.items():
            if key == "updated_at":
                details[key] = _latest(details.get(key, ""), value)
            elif key not in ("model", "git_branch") or key not in details or _newer(
                field_times.get(key, ""), database_time,
            ):
                details[key] = value
        break

    try:
        # Codex appends renames here; the database title can remain stale after renaming.
        for entry in records(config_dir / "session_index.jsonl"):
            if entry.get("id") != session_id:
                continue
            title = clean(entry.get("thread_name"), limit=120)
            if title:
                details["session_id"] = session_id
                details["title"] = title
                stamp = _timestamp(entry.get("updated_at"))
                if stamp:
                    details["updated_at"] = _latest(details.get("updated_at", ""), stamp)
    except (OSError, ValueError):
        pass
    if details:
        details["metadata_source"] = "Codex · recorded metadata"
    return details
