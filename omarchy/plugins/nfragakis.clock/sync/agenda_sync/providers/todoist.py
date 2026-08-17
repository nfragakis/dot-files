from __future__ import annotations

import urllib.parse
from typing import Any

from ..model import expand_path, http_json


def fetch(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    token_path = expand_path(config.get("tokenFile", "~/.config/todoist/api_key"))
    token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError(f"Todoist token file is empty: {token_path}")

    query = str(config.get("filter") or "today | overdue")
    limit = max(1, min(200, int(config.get("limit", 50))))
    results: list[dict[str, Any]] = []
    cursor = ""
    while True:
        query_params: dict[str, Any] = {"query": query, "limit": limit}
        if cursor:
            query_params["cursor"] = cursor
        params = urllib.parse.urlencode(query_params)
        url = f"https://api.todoist.com/api/v1/tasks/filter?{params}"
        document = http_json(url, token=token)
        results.extend(document.get("results", []))
        cursor = str(document.get("next_cursor") or "")
        if not cursor:
            break

    tasks: list[dict[str, Any]] = []
    for task in results:
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        due = task.get("due") or {}
        tasks.append(
            {
                "id": task_id,
                "content": str(task.get("content") or "Untitled task"),
                "description": str(task.get("description") or ""),
                "priority": int(task.get("priority") or 1),
                "projectId": str(task.get("project_id") or ""),
                "labels": [str(value) for value in task.get("labels", [])],
                "due": str(due.get("datetime") or due.get("date") or due.get("string") or ""),
                "url": f"https://app.todoist.com/app/task/{urllib.parse.quote(task_id, safe='')}",
            }
        )

    tasks.sort(key=lambda item: (-item["priority"], item["due"] or "9999", item["content"].lower()))
    return tasks, {"id": "todoist", "name": "Todoist", "count": len(tasks), "filter": query}
