from __future__ import annotations

import html
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


URL_RE = re.compile(r"https://[^\s<>\"']+", re.IGNORECASE)
MEETING_HOST_PARTS = (
    "meet.google.com",
    "teams.microsoft.com",
    "teams.live.com",
    "zoom.us",
    "zoom.com",
    "chime.aws",
    "meetings.amazon.com",
    "webex.com",
    "whereby.com",
    "pexip.me",
)


def expand_path(value: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def parse_datetime(value: str, *, end_of_day: bool = False) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("missing date/time")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        parsed_date = date.fromisoformat(text)
        return datetime.combine(parsed_date, time.max if end_of_day else time.min).astimezone()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def safe_https_url(value: Any) -> str:
    text = html.unescape(str(value or "").strip()).rstrip(".,);]")
    try:
        parsed = urllib.parse.urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return ""
    if any(char.isspace() for char in text) or any(char in text for char in '"\'<>'):
        return ""
    return text


def urls_in(*values: Any) -> list[str]:
    found: list[str] = []
    for value in values:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        for match in URL_RE.findall(text):
            url = safe_https_url(match)
            if url and url not in found:
                found.append(url)
    return found


def meeting_url(*candidates: Any) -> str:
    urls: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, (list, tuple)):
            urls.extend(urls_in(*candidate))
        else:
            direct = safe_https_url(candidate)
            if direct:
                urls.append(direct)
            urls.extend(urls_in(candidate))

    unique: list[str] = []
    for url in urls:
        if url not in unique:
            unique.append(url)
    for url in unique:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if any(part == host or host.endswith("." + part) for part in MEETING_HOST_PARTS):
            return url
    return ""


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(event)
    normalized["id"] = str(event.get("id") or "")
    normalized["sourceId"] = str(event.get("sourceId") or "unknown")
    normalized["provider"] = str(event.get("provider") or "unknown")
    normalized["account"] = str(event.get("account") or "")
    normalized["calendarId"] = str(event.get("calendarId") or normalized["sourceId"])
    normalized["calendarName"] = str(event.get("calendarName") or normalized["calendarId"])
    normalized["color"] = str(event.get("color") or "#62a0ea")
    normalized["title"] = str(event.get("title") or "Untitled event")
    normalized["location"] = str(event.get("location") or "")
    normalized["allDay"] = bool(event.get("allDay"))
    normalized["start"] = str(event.get("start") or "")
    normalized["end"] = str(event.get("end") or normalized["start"])
    normalized["meetingUrl"] = safe_https_url(event.get("meetingUrl"))
    event_url = str(event.get("eventUrl") or "").strip()
    normalized["eventUrl"] = event_url if event_url.startswith("calendar:///") else safe_https_url(event_url)
    normalized["responseStatus"] = str(event.get("responseStatus") or "")
    normalized["icalUid"] = str(event.get("icalUid") or "")
    if not normalized["id"]:
        normalized["id"] = ":".join(
            [normalized["sourceId"], normalized["icalUid"] or normalized["title"], normalized["start"]]
        )
    return normalized


def dedupe_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in events:
        event = normalize_event(raw)
        identity = event.get("icalUid") or f"{event['sourceId']}:{event['id']}"
        try:
            canonical_start = str(int(parse_datetime(event["start"]).timestamp()))
        except (TypeError, ValueError):
            canonical_start = event["start"]
        key = f"{identity}:{canonical_start}"
        previous = selected.get(key)
        if previous is None:
            selected[key] = event
            order.append(key)
            continue
        score = int(bool(event.get("meetingUrl"))) * 2 + int(bool(event.get("eventUrl")))
        old_score = int(bool(previous.get("meetingUrl"))) * 2 + int(bool(previous.get("eventUrl")))
        if score > old_score:
            selected[key] = event
    return [selected[key] for key in order]


def expand_event_days(event: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = normalize_event(event)
    start = parse_datetime(normalized["start"])
    # RFC 5545 and both provider APIs represent an all-day DTEND as an
    # exclusive midnight boundary. Parsing it as the end of that date would
    # add a phantom extra row.
    end = parse_datetime(normalized["end"] or normalized["start"])
    if end < start:
        end = start

    first = start.astimezone().date()
    last = end.astimezone().date()
    if end.astimezone().time() == time.min and end > start:
        last -= timedelta(days=1)
    if last < first:
        last = first

    rows: list[dict[str, Any]] = []
    cursor = first
    while cursor <= last:
        row = dict(normalized)
        row["dateKey"] = cursor.isoformat()
        row["rowId"] = f"{normalized['id']}:{row['dateKey']}"
        rows.append(row)
        cursor += timedelta(days=1)
    return rows


def prepare_events(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in dedupe_events(events):
        try:
            rows.extend(expand_event_days(event))
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda item: (item["dateKey"], not item["allDay"], item["start"], item["title"].lower()))
    return rows


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def http_json(
    url: str,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {error.code} from {urllib.parse.urlsplit(url).hostname}: {body}") from error


def local_window(past_days: int, future_days: int) -> tuple[datetime, datetime]:
    today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=past_days), today + timedelta(days=future_days + 1)
