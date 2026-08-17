import unittest

from agenda_sync.providers.evolution import _evolution_uri, _ical_properties


class EvolutionTests(unittest.TestCase):
    def test_unfolds_custom_meeting_properties(self):
        raw = (
            "BEGIN:VEVENT\r\n"
            "UID:abc\r\n"
            "X-MICROSOFT-SKYPETEAMSMEETINGURL:https://teams.microsoft.com/l/\r\n"
            " meetup-join/xyz\r\n"
            "END:VEVENT\r\n"
        )
        properties = _ical_properties(raw)
        self.assertEqual(properties["UID"], ["abc"])
        self.assertEqual(
            properties["X-MICROSOFT-SKYPETEAMSMEETINGURL"],
            ["https://teams.microsoft.com/l/meetup-join/xyz"],
        )

    def test_event_uri_encodes_source_component_and_recurrence(self):
        uri = _evolution_uri("source one", "component&two", "20260817T140000Z")
        self.assertTrue(uri.startswith("calendar:///?"))
        self.assertIn("source-uid=source+one", uri)
        self.assertIn("comp-uid=component%26two", uri)
        self.assertIn("comp-rid=20260817T140000Z", uri)


if __name__ == "__main__":
    unittest.main()
