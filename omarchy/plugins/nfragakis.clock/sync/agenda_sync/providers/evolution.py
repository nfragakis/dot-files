from __future__ import annotations

import re
import urllib.parse
from datetime import datetime
from typing import Any

from ..model import meeting_url


def _ical_properties(raw: str) -> dict[str, list[str]]:
    unfolded = re.sub(r"\r?\n[ \t]", "", raw or "")
    properties: dict[str, list[str]] = {}
    for line in unfolded.splitlines():
        if ":" not in line:
            continue
        left, value = line.split(":", 1)
        name = left.split(";", 1)[0].upper()
        properties.setdefault(name, []).append(
            value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
        )
    return properties


def _evolution_uri(source_uid: str, component_uid: str, recurrence_id: str = "") -> str:
    query = {
        "source-uid": source_uid,
        "comp-uid": component_uid,
    }
    if recurrence_id:
        query["comp-rid"] = recurrence_id
    return "calendar:///?" + urllib.parse.urlencode(query)


def _instance_value(value) -> str:
    if value.is_date():
        return f"{value.get_year():04d}-{value.get_month():02d}-{value.get_day():02d}"
    zone = value.get_timezone()
    if zone is not None:
        timestamp = value.as_timet_with_zone(zone)
        return datetime.fromtimestamp(timestamp).astimezone().isoformat()
    # Floating iCalendar times are local wall times by definition.
    return datetime(
        value.get_year(),
        value.get_month(),
        value.get_day(),
        value.get_hour(),
        value.get_minute(),
        value.get_second(),
    ).astimezone().isoformat()


def fetch(
    config: dict[str, Any], start_timestamp: int, end_timestamp: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        import gi

        gi.require_version("ECal", "2.0")
        gi.require_version("EDataServer", "1.2")
        gi.require_version("ICalGLib", "4.0")
        from gi.repository import ECal, EDataServer
    except (ImportError, ValueError) as error:
        raise RuntimeError("Evolution provider requires /usr/bin/python3 and python-gobject") from error

    registry = EDataServer.SourceRegistry.new_sync(None)
    sources = registry.list_enabled(EDataServer.SOURCE_EXTENSION_CALENDAR)
    selected_only = config.get("selectedOnly", True) is not False
    allowed_ids = {str(value) for value in config.get("calendarIds", [])}
    events: list[dict[str, Any]] = []
    used_sources = 0

    for source in sources:
        source_uid = str(source.get_uid())
        extension = source.get_extension(EDataServer.SOURCE_EXTENSION_CALENDAR)
        if allowed_ids and source_uid not in allowed_ids:
            continue
        if selected_only and not extension.get_selected():
            continue
        used_sources += 1

        client = ECal.Client.connect_sync(source, ECal.ClientSourceType.EVENTS, 10, None)
        if client is None:
            continue

        calendar_name = str(source.get_display_name() or source_uid)
        color = str(extension.get_color() or "#62a0ea")

        def instance_callback(component, instance_start, instance_end, _user_data, _cancellable):
            raw = component.as_ical_string() or ""
            props = _ical_properties(raw)
            uid = str(component.get_uid() or (props.get("UID") or [""])[0])
            recurrence_id = str((props.get("RECURRENCE-ID") or [""])[0])
            start = _instance_value(instance_start)
            end = _instance_value(instance_end)
            custom_candidates: list[str] = []
            for name in (
                "CONFERENCE",
                "X-GOOGLE-CONFERENCE",
                "X-MICROSOFT-SKYPETEAMSMEETINGURL",
                "X-MICROSOFT-ONLINEMEETINGCONFLINK",
            ):
                custom_candidates.extend(props.get(name, []))

            description = str(component.get_description() or "")
            location = str(component.get_location() or "")
            events.append(
                {
                    "id": f"evolution:{source_uid}:{uid}:{recurrence_id or start}",
                    "sourceId": f"evolution:{source_uid}",
                    "provider": "evolution",
                    "account": calendar_name,
                    "calendarId": f"evolution:{source_uid}",
                    "calendarName": calendar_name,
                    "color": color,
                    "start": start,
                    "end": end,
                    "allDay": bool(instance_start.is_date()),
                    "title": str(component.get_summary() or "Untitled event"),
                    "location": location,
                    "meetingUrl": meeting_url(custom_candidates, location, description, props.get("URL", [])),
                    "eventUrl": _evolution_uri(source_uid, uid, recurrence_id),
                    "responseStatus": "",
                    "icalUid": uid,
                }
            )
            return True

        client.generate_instances_sync(
            start_timestamp,
            end_timestamp,
            None,
            instance_callback,
            None,
        )

    return events, {
        "id": "evolution",
        "name": "Evolution Data Server",
        "count": len(events),
        "calendarCount": used_sources,
    }
