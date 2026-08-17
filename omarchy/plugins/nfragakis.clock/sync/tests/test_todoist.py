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

    def test_fetch_follows_every_cursor_page(self):
        pages = [
            {
                "results": [
                    {"id": "first", "content": "First", "priority": 1, "due": {"date": "2026-08-18"}}
                ],
                "next_cursor": "next-page",
            },
            {
                "results": [
                    {"id": "second", "content": "Second", "priority": 1, "due": {"date": "2026-08-19"}}
                ],
                "next_cursor": None,
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("secret", encoding="utf-8")
            with patch.object(todoist, "http_json", side_effect=pages) as request:
                tasks, source = todoist.fetch(
                    {"tokenFile": str(token), "filter": "overdue | 60 days", "limit": 50}
                )

        self.assertEqual([task["id"] for task in tasks], ["first", "second"])
        self.assertEqual(source["count"], 2)
        self.assertEqual(request.call_count, 2)
        self.assertIn("cursor=next-page", request.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
