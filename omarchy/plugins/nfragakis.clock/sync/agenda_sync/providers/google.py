from __future__ import annotations

from typing import Any

from ..model import atomic_write_json, expand_path, meeting_url, safe_https_url


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _response_status(event: dict[str, Any]) -> str:
    for attendee in event.get("attendees", []):
        if attendee.get("self"):
            return str(attendee.get("responseStatus") or "")
    return ""


def _conference_urls(event: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    hangout = safe_https_url(event.get("hangoutLink"))
    if hangout:
        urls.append(hangout)
    for entry in (event.get("conferenceData") or {}).get("entryPoints", []):
        uri = safe_https_url(entry.get("uri"))
        if uri:
            urls.append(uri)
    return urls


def fetch(
    config: dict[str, Any], start_iso: str, end_iso: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as error:
        raise RuntimeError("Google provider dependencies are missing; run sync/setup --direct-deps") from error

    account = str(config.get("account") or "google")
    token_path = expand_path(config.get("tokenFile", f"~/.local/share/nfragakis-calendar-dashboard/auth/google-{account}.json"))
    if not token_path.exists():
        raise RuntimeError(f"Google token not found for {account}; run calendar-dashboard-auth google")

    credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        atomic_write_json(token_path, __import__("json").loads(credentials.to_json()))
    if not credentials.valid:
        raise RuntimeError(f"Google credentials are not valid for {account}")

    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    calendars: list[dict[str, Any]] = []
    page_token = None
    while True:
        page = service.calendarList().list(showHidden=False, pageToken=page_token).execute()
        calendars.extend(page.get("items", []))
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    selected_only = config.get("selectedOnly", True) is not False
    allowed_ids = {str(value) for value in config.get("calendarIds", [])}
    events: list[dict[str, Any]] = []
    used_calendars = 0

    for calendar in calendars:
        calendar_id = str(calendar.get("id") or "")
        if not calendar_id:
            continue
        if allowed_ids and calendar_id not in allowed_ids:
            continue
        if selected_only and not calendar.get("selected", calendar.get("primary", False)):
            continue
        used_calendars += 1

        event_page_token = None
        while True:
            page = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start_iso,
                    timeMax=end_iso,
                    singleEvents=True,
                    orderBy="startTime",
                    showDeleted=False,
                    maxResults=2500,
                    pageToken=event_page_token,
                )
                .execute()
            )
            for raw in page.get("items", []):
                if raw.get("status") == "cancelled":
                    continue
                start = raw.get("start") or {}
                end = raw.get("end") or {}
                start_value = start.get("dateTime") or start.get("date") or ""
                end_value = end.get("dateTime") or end.get("date") or start_value
                conference_urls = _conference_urls(raw)
                events.append(
                    {
                        "id": f"google:{account}:{calendar_id}:{raw.get('id', '')}",
                        "sourceId": f"google:{account}",
                        "provider": "google",
                        "account": account,
                        "calendarId": f"google:{account}:{calendar_id}",
                        "calendarName": str(calendar.get("summaryOverride") or calendar.get("summary") or account),
                        "color": str(calendar.get("backgroundColor") or "#4285f4"),
                        "start": str(start_value),
                        "end": str(end_value),
                        "allDay": "date" in start and "dateTime" not in start,
                        "title": str(raw.get("summary") or "Untitled event"),
                        "location": str(raw.get("location") or ""),
                        "meetingUrl": meeting_url(conference_urls, raw.get("location"), raw.get("description")),
                        "eventUrl": safe_https_url(raw.get("htmlLink")),
                        "responseStatus": _response_status(raw),
                        "icalUid": str(raw.get("iCalUID") or ""),
                    }
                )
            event_page_token = page.get("nextPageToken")
            if not event_page_token:
                break

    return events, {
        "id": f"google:{account}",
        "name": f"Google · {account}",
        "count": len(events),
        "calendarCount": used_calendars,
    }
