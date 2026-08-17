import tempfile
import unittest
from pathlib import Path

from agenda_sync.model import (
    atomic_write_json,
    dedupe_events,
    expand_event_days,
    load_json,
    meeting_url,
    safe_https_url,
)


def event(**overrides):
    value = {
        "id": "one",
        "sourceId": "test:one",
        "provider": "test",
        "calendarId": "calendar",
        "calendarName": "Calendar",
        "start": "2026-08-17T09:00:00-05:00",
        "end": "2026-08-17T10:00:00-05:00",
        "title": "Standup",
        "allDay": False,
    }
    value.update(overrides)
    return value


class ModelTests(unittest.TestCase):
    def test_meeting_url_prefers_known_conference_host(self):
        chosen = meeting_url(
            "See https://example.com/notes and https://us06web.zoom.us/j/12345"
        )
        self.assertEqual(chosen, "https://us06web.zoom.us/j/12345")

    def test_non_https_urls_are_rejected(self):
        self.assertEqual(safe_https_url("javascript:alert(1)"), "")
        self.assertEqual(safe_https_url("http://meet.google.com/abc"), "")

    def test_all_day_end_is_exclusive(self):
        rows = expand_event_days(
            event(start="2026-08-17", end="2026-08-19", allDay=True)
        )
        self.assertEqual([row["dateKey"] for row in rows], ["2026-08-17", "2026-08-18"])

    def test_duplicate_prefers_event_with_join_and_event_urls(self):
        plain = event(id="plain", icalUid="shared")
        rich = event(
            id="rich",
            icalUid="shared",
            meetingUrl="https://meet.google.com/abc-defg-hij",
            eventUrl="https://calendar.google.com/calendar/event?eid=abc",
        )
        result = dedupe_events([plain, rich])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "rich")

    def test_atomic_json_is_private_and_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            atomic_write_json(path, {"ok": True})
            self.assertEqual(load_json(path), {"ok": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
