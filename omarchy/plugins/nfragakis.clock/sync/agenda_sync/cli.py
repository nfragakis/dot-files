from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .model import expand_path, iso_now, load_json, local_window, prepare_events, atomic_write_json


DEFAULT_CONFIG = "~/.config/omarchy/calendar-dashboard.json"
DEFAULT_OUTPUT = "~/.local/state/omarchy/calendar-dashboard.json"


def _provider_identity(config: dict[str, Any]) -> str:
    provider_type = str(config.get("type") or "unknown")
    account = str(config.get("account") or "")
    return f"{provider_type}:{account}" if account else provider_type


def sync(config_path: Path, output_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    if not isinstance(config, dict) or config.get("version") != 1:
        raise RuntimeError(f"invalid or missing version 1 configuration: {config_path}")

    window = config.get("window") or {}
    past_days = max(0, int(window.get("pastDays", 7)))
    future_days = max(1, int(window.get("futureDays", 60)))
    start, end = local_window(past_days, future_days)
    start_iso = start.astimezone().isoformat()
    end_iso = end.astimezone().isoformat()
    previous = load_json(output_path, {}) or {}

    all_events: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    failed_source_ids: set[str] = set()

    for provider_config in config.get("providers", []):
        if provider_config.get("enabled", True) is False:
            continue
        provider_type = str(provider_config.get("type") or "")
        identity = _provider_identity(provider_config)
        try:
            if provider_type == "evolution":
                from .providers import evolution

                events, source = evolution.fetch(provider_config, int(start.timestamp()), int(end.timestamp()))
            elif provider_type == "google":
                from .providers import google

                events, source = google.fetch(provider_config, start_iso, end_iso)
            elif provider_type == "microsoft":
                from .providers import microsoft

                events, source = microsoft.fetch(provider_config, start_iso, end_iso)
            else:
                raise RuntimeError(f"unknown calendar provider: {provider_type or '<missing>'}")
            source["status"] = "ok"
            sources.append(source)
            all_events.extend(events)
        except Exception as error:  # provider isolation is deliberate
            failed_source_ids.add(identity)
            errors.append({"source": identity, "message": str(error)})
            sources.append({"id": identity, "name": identity, "count": 0, "status": "error"})

    if failed_source_ids:
        for event in previous.get("events", []):
            source_id = str(event.get("sourceId") or "")
            if source_id in failed_source_ids or any(source_id.startswith(value + ":") for value in failed_source_ids):
                stale = dict(event)
                stale["stale"] = True
                all_events.append(stale)

    tasks: list[dict[str, Any]] = []
    todoist_config = config.get("todoist") or {}
    if todoist_config.get("enabled", False):
        try:
            from .providers import todoist

            tasks, source = todoist.fetch(todoist_config)
            source["status"] = "ok"
            sources.append(source)
        except Exception as error:
            errors.append({"source": "todoist", "message": str(error)})
            sources.append({"id": "todoist", "name": "Todoist", "count": 0, "status": "error"})
            tasks = previous.get("tasks", [])
            for task in tasks:
                task["stale"] = True

    payload = {
        "version": 1,
        "syncedAt": iso_now(),
        "window": {"start": start_iso, "end": end_iso},
        "sources": sources,
        "errors": errors,
        "events": prepare_events(all_events),
        "tasks": tasks,
    }
    atomic_write_json(output_path, payload)
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Sync calendars and Todoist for the Omarchy clock")
    result.add_argument("--config", default=DEFAULT_CONFIG)
    result.add_argument("--output", default=DEFAULT_OUTPUT)
    result.add_argument("--summary", action="store_true", help="print counts after syncing")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        payload = sync(expand_path(args.config), expand_path(args.output))
    except Exception as error:
        print(f"calendar-dashboard-sync: {error}", file=sys.stderr)
        return 1
    if args.summary:
        print(
            json.dumps(
                {
                    "events": len(payload["events"]),
                    "tasks": len(payload["tasks"]),
                    "errors": payload["errors"],
                    "output": str(expand_path(args.output)),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
