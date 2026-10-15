"""Read recorded Claude metadata only after an exact session identity match."""
from __future__ import annotations

from pathlib import Path
import re

from metadata_common import clean, records


_SESSION_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _transcript(session_id: str, transcript_path: Path | None, config_dir: Path) -> Path | None:
    if transcript_path is not None:
        return Path(transcript_path)
    if not _SESSION_UUID.fullmatch(session_id):
        return None
    # A cwd can contain many sessions. Only the exact UUID filename is eligible.
    try:
        candidates = list((config_dir / "projects").glob(f"*/{session_id}.jsonl"))
    except OSError:
        return None
    return candidates[0] if len(candidates) == 1 else None


def _plain_text(content: object) -> str:
    if isinstance(content, str):
        return clean(content)
    if not isinstance(content, list):
        return ""
    parts = []
    length = 0
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = clean(block.get("text"))
        if text:
            parts.append(text)
            length += len(text) + 1
            if length >= 300:
                break
    return clean(" ".join(parts))


def _usage(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    # These are one recorded assistant message's counters, never session totals.
    counts = {}
    for key in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        count = value.get(key)
        if type(count) is int and count >= 0:
            counts[key] = count
    if "input_tokens" not in counts or "output_tokens" not in counts:
        return ""
    text = (
        f"Latest provider response record: {counts['input_tokens']} uncached input / "
        f"{counts['output_tokens']} output tokens"
    )
    if "cache_read_input_tokens" in counts:
        text += f"; {counts['cache_read_input_tokens']} cache read"
    if "cache_creation_input_tokens" in counts:
        text += f"; {counts['cache_creation_input_tokens']} cache write"
    return clean(text)


def collect(session_id: str, transcript_path: Path | None, config_dir: Path) -> dict:
    """Return bounded, recorded metadata; files never imply live activity."""
    if not isinstance(session_id, str) or not session_id:
        return {}
    path = _transcript(session_id, transcript_path, config_dir)
    if path is None:
        return {}
    result = {}
    ai_title = ""
    custom_title = ""
    validated = False
    try:
        for record in records(path):
            if record.get("isSidechain"):
                continue
            identity = record.get("sessionId")
            if not isinstance(identity, str) or not identity:
                continue
            if identity != session_id:
                # Mixed mainline identities are ambiguous even with a matching filename.
                return {}
            validated = True
            kind = record.get("type")
            if kind == "ai-title":
                title = clean(record.get("aiTitle"), limit=120)
                if title:
                    ai_title = title
            elif kind == "custom-title":
                title = clean(record.get("customTitle"), limit=120)
                if title:
                    custom_title = title
            for source, target in (("gitBranch", "git_branch"), ("timestamp", "updated_at")):
                value = clean(record.get(source))
                if value:
                    result[target] = value
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            if kind == "user" and not record.get("isMeta"):
                text = _plain_text(message.get("content"))
                # Claude also writes locally executed slash commands as user
                # messages. Their provider XML wrapper is not a model request.
                if text and not text.startswith("<command-name>"):
                    result["request"] = text
            elif kind == "assistant":
                text = _plain_text(message.get("content"))
                if text:
                    result["last_response"] = text
                model = clean(message.get("model"), limit=100)
                # Claude's locally generated errors use this sentinel, not a model.
                if model == "<synthetic>":
                    continue
                if model:
                    result["model"] = model
                usage = _usage(message.get("usage"))
                if usage:
                    result["usage"] = usage
                else:
                    result.pop("usage", None)
    except (OSError, ValueError):
        return {}
    if not validated:
        return {}
    if custom_title or ai_title:
        result["title"] = custom_title or ai_title
    result.update(
        session_id=session_id,
        transcript_path=str(path),
        metadata_source="Claude transcript · recorded metadata",
    )
    return result
