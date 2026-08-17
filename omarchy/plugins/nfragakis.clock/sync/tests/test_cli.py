import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agenda_sync import cli


class SyncTests(unittest.TestCase):
    def synced_todoist_config(self, configured_filter):
        seen_config = {}

        def fake_fetch(config):
            seen_config.update(config)
            return [], {"id": "todoist", "name": "Todoist", "count": 0}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            output_path = root / "dashboard.json"
            todoist_config = {"enabled": True, "tokenFile": "/unused"}
            if configured_filter is not None:
                todoist_config["filter"] = configured_filter
            config_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "window": {"pastDays": 7, "futureDays": 60},
                        "providers": [],
                        "todoist": todoist_config,
                    }
                ),
                encoding="utf-8",
            )

            with patch("agenda_sync.providers.todoist.fetch", side_effect=fake_fetch):
                cli.sync(config_path, output_path)

        return seen_config

    def test_legacy_today_filter_is_upgraded_to_the_calendar_future_window(self):
        seen_config = self.synced_todoist_config("today | overdue")
        self.assertEqual(seen_config["filter"], "overdue | 60 days")

    def test_custom_filter_cannot_narrow_the_calendar_future_window(self):
        seen_config = self.synced_todoist_config("#Work & today")
        self.assertEqual(seen_config["filter"], "overdue | 60 days")


if __name__ == "__main__":
    unittest.main()
