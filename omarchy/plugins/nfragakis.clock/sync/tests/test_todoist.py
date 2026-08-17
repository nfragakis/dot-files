import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agenda_sync.providers import todoist


class TodoistTests(unittest.TestCase):
    def test_tasks_are_normalized_and_prioritized(self):
        response = {
            "results": [
                {"id": "low", "content": "Later", "priority": 1, "due": {"date": "2026-08-17"}},
                {"id": "high", "content": "Urgent", "priority": 4, "due": {"date": "2026-08-18"}},
            ],
            "next_cursor": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("secret", encoding="utf-8")
            with patch.object(todoist, "http_json", return_value=response):
                tasks, source = todoist.fetch({"tokenFile": str(token), "filter": "today | overdue"})
        self.assertEqual([task["id"] for task in tasks], ["high", "low"])
        self.assertEqual(tasks[0]["url"], "https://app.todoist.com/app/task/high")
        self.assertEqual(source["count"], 2)


if __name__ == "__main__":
    unittest.main()
