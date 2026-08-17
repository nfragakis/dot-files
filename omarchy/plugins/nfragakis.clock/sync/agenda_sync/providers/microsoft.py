from __future__ import annotations

import urllib.parse
from typing import Any

from ..model import atomic_write_text, expand_path, http_json, meeting_url, safe_https_url


SCOPES = ["Calendars.Read"]
COLOR_MAP = {
    "auto": "#4f6bed",
    "lightBlue": "#4f9dda",
    "lightGreen": "#6bb700",
    "lightOrange": "#f7630c",
    "lightGray": "#8a8886",
    "lightYellow": "#fce100",
    "lightTeal": "#00b7c3",
    "lightPink": "#e3008c",
    "lightBrown": "#8e562e",
    "lightRed": "#d13438",
    "maxColor": "#4f6bed",
}


def _graph_pages(url: str, token: str, *, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    next_url = url
    while next_url:
        document = http_json(next_url, token=token, headers=headers)
        rows.extend(document.get("value", []))
        next_url = str(document.get("@odata.nextLink") or "")
    return rows


def _graph_datetime(value: dict[str, Any]) -> str:
    text = str(value.get("dateTime") or "")
    if not text:
        return ""
    if text.endswith("Z") or "+" in text[10:] or "-" in text[10:]:
        return text
    # Requests ask Graph for UTC. Graph's dateTimeTimeZone shape keeps the zone
    # in a sibling field instead of appending an offset to dateTime.
    return text + "Z"


def fetch(
    config: dict[str, Any], start_iso: str, end_iso: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        import msal
    except ImportError as error:
        raise RuntimeError("Microsoft provider dependency is missing; run sync/setup --direct-deps") from error

    account = str(config.get("account") or "microsoft")
    client_id = str(config.get("clientId") or "")
    if not client_id:
        raise RuntimeError(f"Microsoft provider {account} has no clientId")
    tenant = str(config.get("tenant") or "organizations")
    cache_path = expand_path(config.get("tokenCache", f"~/.local/share/nfragakis-calendar-dashboard/auth/microsoft-{account}.cache"))

    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))
    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{tenant}",
        token_cache=cache,
    )
    username = config.get("username")
    accounts = app.get_accounts(username=username) if username else app.get_accounts()
    if not accounts:
        raise RuntimeError(f"No Microsoft login cached for {account}; run calendar-dashboard-auth microsoft")
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if cache.has_state_changed:
        atomic_write_text(cache_path, cache.serialize())
    if not result or "access_token" not in result:
        message = (result or {}).get("error_description") or "silent token acquisition failed"
        raise RuntimeError(f"Microsoft authentication failed for {account}: {message}")
    token = result["access_token"]

    select_calendars = urllib.parse.urlencode({"$select": "id,name,color,isDefaultCalendar"})
    calendars = _graph_pages(f"https://graph.microsoft.com/v1.0/me/calendars?{select_calendars}", token)
    allowed_ids = {str(value) for value in config.get("calendarIds", [])}
    events: list[dict[str, Any]] = []
    used_calendars = 0
    headers = {"Prefer": 'outlook.timezone="UTC"'}

    fields = ",".join(
        [
            "id",
            "subject",
            "start",
            "end",
            "isAllDay",
            "isCancelled",
            "location",
            "onlineMeeting",
            "onlineMeetingUrl",
            "webLink",
            "bodyPreview",
            "responseStatus",
            "iCalUId",
            "showAs",
        ]
    )
    for calendar in calendars:
        calendar_id = str(calendar.get("id") or "")
        if not calendar_id or (allowed_ids and calendar_id not in allowed_ids):
            continue
        used_calendars += 1
        query = urllib.parse.urlencode(
            {
                "startDateTime": start_iso,
                "endDateTime": end_iso,
                "$top": 1000,
                "$select": fields,
            }
        )
        encoded_id = urllib.parse.quote(calendar_id, safe="")
        rows = _graph_pages(
            f"https://graph.microsoft.com/v1.0/me/calendars/{encoded_id}/calendarView?{query}",
            token,
            headers=headers,
        )
        for raw in rows:
            if raw.get("isCancelled"):
                continue
            start = raw.get("start") or {}
            end = raw.get("end") or {}
            online = raw.get("onlineMeeting") or {}
            events.append(
                {
                    "id": f"microsoft:{account}:{calendar_id}:{raw.get('id', '')}",
                    "sourceId": f"microsoft:{account}",
                    "provider": "microsoft",
                    "account": account,
                    "calendarId": f"microsoft:{account}:{calendar_id}",
                    "calendarName": str(calendar.get("name") or account),
                    "color": COLOR_MAP.get(str(calendar.get("color") or "auto"), "#4f6bed"),
                    "start": _graph_datetime(start),
                    "end": _graph_datetime(end) or _graph_datetime(start),
                    "allDay": bool(raw.get("isAllDay")),
                    "title": str(raw.get("subject") or "Untitled event"),
                    "location": str((raw.get("location") or {}).get("displayName") or ""),
                    "meetingUrl": meeting_url(
                        online.get("joinUrl"),
                        raw.get("onlineMeetingUrl"),
                        (raw.get("location") or {}).get("displayName"),
                        raw.get("bodyPreview"),
                    ),
                    "eventUrl": safe_https_url(raw.get("webLink")),
                    "responseStatus": str((raw.get("responseStatus") or {}).get("response") or ""),
                    "icalUid": str(raw.get("iCalUId") or ""),
                }
            )

    return events, {
        "id": f"microsoft:{account}",
        "name": f"Microsoft · {account}",
        "count": len(events),
        "calendarCount": used_calendars,
    }
