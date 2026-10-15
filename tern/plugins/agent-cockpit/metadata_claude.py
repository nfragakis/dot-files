"""Read recorded Claude metadata only after an exact session identity match."""
from __future__ import annotations

from pathlib import Path
import re

from metadata_common import clean, records
from metadata_usage import counters, digest, fields, money, remember, scan


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


def _account(state: dict, record: dict, identity: str) -> None:
    if record.get("isSidechain"):
        return
    session = record.get("sessionId")
    if not isinstance(session, str) or not session:
        return
    if session != identity:
        state["invalid"] = True
        return
    tool_result = record.get("toolUseResult")
    if isinstance(tool_result, dict) and isinstance(tool_result.get("agentId"), str):
        remember(state, "agents", tool_result["agentId"], True)
    if record.get("type") == "cost-state":
        # Actual Claude Code persisted provider snapshot; replace, never add
        # successive cumulative cost-state values (including after resume).
        if money(record.get("totalCostUSD")):
            state["reported_cost"] = record["totalCostUSD"]
            state["unknown_cost"] = record.get("hasUnknownModelCost") is True
        model_usage = record.get("modelUsage")
        if isinstance(model_usage, dict) and model_usage:
            values = [counters(value, ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"))
                      for value in model_usage.values()]
            if all(value is not None for value in values):
                state["snapshot"] = [sum(value[index] for value in values) if all(value[index] is not None for value in values) else None
                                     for index in range(4)]
        return
    message = record.get("message")
    if record.get("type") != "assistant" or not isinstance(message, dict) or message.get("model") == "<synthetic>":
        return
    values = counters(message.get("usage"), ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
    state.pop("prompt", None)
    if values is None:
        state["missing_usage"] = True
        return
    if all(value is not None for value in (values[0], values[2], values[3])):
        state["prompt"] = values[0] + values[2] + values[3]
    key = message.get("id")
    if isinstance(key, str):
        previous = state["ledger"].get(digest(key))
        if previous:
            # Claude serializes separate blocks/streaming updates with the
            # same message ID. Usage is cumulative for that message.
            values = [max(old, new) if old is not None and new is not None else old if new is None else new
                      for old, new in zip(previous[0], values)]
    remember(state, "ledger", key, [values, None])


def _session_usage(path: Path, identity: str) -> dict:
    state, coverage = scan("claude", path, identity, _account)
    if state.get("invalid"):
        return {}
    result = fields(state, coverage, "Claude mainline message IDs (agents excluded; input excludes cache); cost-state is provider session snapshot; no live context/agent state")
    if coverage.startswith("complete recorded file") and "snapshot" in state:
        snapshot = fields({"ledger": {"snapshot": [state["snapshot"], None]}}, coverage, "")
        result["session_tokens"] = snapshot["session_tokens"].replace("Recorded session:", "Provider session snapshot:")
        result["usage_stats"].update({key: value for key, value in zip(
            ("input", "output", "cache_read", "cache_write"), state["snapshot"]) if value is not None})
    if coverage.startswith("complete recorded file") and "reported_cost" in state:
        result["session_cost"] = f"Provider estimate snapshot: ${state['reported_cost']:.6f} USD (not billing)"
        if not state.get("unknown_cost"):
            result["usage_stats"]["cost"] = float(state["reported_cost"])
        if state.get("unknown_cost"):
            result["session_cost"] += " (incomplete: unknown model cost)"
    else:
        result["session_cost"] = "Unavailable: no Claude cost-state totalCostUSD" if coverage.startswith("complete recorded file") else result["session_cost"]
    return result

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
            value = clean(record.get("gitBranch"))
            if value:
                result["git_branch"] = value
            # Conversation records only: resumes and snapshots also carry timestamps.
            value = clean(record.get("timestamp")) if kind in ("user", "assistant") else ""
            if value:
                result["updated_at"] = value
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
    accounting = _session_usage(path, session_id)
    if not accounting:
        return {}
    result.update(accounting)
    if custom_title or ai_title:
        result["title"] = custom_title or ai_title
    result.update(
        session_id=session_id,
        transcript_path=str(path),
        metadata_source="Claude transcript · recorded metadata",
    )
    return result
