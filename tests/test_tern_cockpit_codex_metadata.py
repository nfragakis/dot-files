from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / "tern/plugins/agent-cockpit"
sys.path.insert(0, str(PLUGIN))
SPEC = importlib.util.spec_from_file_location("cockpit_codex_metadata", PLUGIN / "metadata_codex.py")
assert SPEC is not None and SPEC.loader is not None
CODEX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CODEX)


EARLY = "2026-10-14T10:00:00Z"
MIDDLE = "2026-10-14T11:00:00Z"
LATE = "2026-10-14T12:00:00Z"


def epoch(stamp: str) -> int:
    return int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())


def record(kind: str, payload: object, timestamp: str = EARLY) -> dict:
    return {"type": kind, "payload": payload, "timestamp": timestamp}


def message(role: str, text: str, timestamp: str = MIDDLE) -> dict:
    return record("response_item", {
        "type": "message", "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}],
    }, timestamp)


class CodexMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def jsonl(self, name: str, entries: list[dict]) -> Path:
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        return path

    def rollout(self, session_id: str, *entries: dict, name: str | None = None) -> Path:
        return self.jsonl(name or f"sessions/{session_id}.jsonl", [
            record("session_meta", {"id": session_id, "session_id": session_id, "cwd": "/same/workspace"}),
            *entries,
        ])

    def database(self, columns: dict[str, str], rows: list[dict], name: str = "state_5.sqlite") -> sqlite3.Connection:
        connection = sqlite3.connect(self.home / name)
        self.addCleanup(connection.close)
        declaration = ", ".join(f'"{key}" {kind}' for key, kind in columns.items())
        connection.execute(f"CREATE TABLE threads ({declaration})")
        for row in rows:
            projection = ", ".join(f'"{key}"' for key in row)
            placeholders = ", ".join("?" for _ in row)
            connection.execute(f"INSERT INTO threads ({projection}) VALUES ({placeholders})", tuple(row.values()))
        connection.commit()
        return connection

    def test_concurrent_same_cwd_threads_remain_exact_and_vscode_is_supported(self) -> None:
        first = self.rollout("thread-a", message("user", "Fix parser A"), message("assistant", "Parser A repaired"))
        second = self.rollout("thread-b", message("user", "Review parser B"), message("assistant", "Parser B reviewed"))
        self.database({
            "id": "TEXT PRIMARY KEY", "rollout_path": "TEXT", "cwd": "TEXT", "title": "TEXT",
            "model": "TEXT", "git_branch": "TEXT", "updated_at": "INTEGER", "source": "TEXT",
        }, [
            {"id": "thread-a", "rollout_path": str(first), "cwd": "/same/workspace", "title": "Parser A",
             "model": "gpt-a", "git_branch": "fix/a", "updated_at": epoch(MIDDLE), "source": "vscode"},
            {"id": "thread-b", "rollout_path": str(second), "cwd": "/same/workspace", "title": "Parser B",
             "model": "gpt-b", "git_branch": "review/b", "updated_at": epoch(LATE), "source": "vscode"},
        ])
        first_result = CODEX.collect("thread-a", None, self.home)
        second_result = CODEX.collect("thread-b", None, self.home)
        self.assertEqual(first_result["title"], "Parser A")
        self.assertEqual(first_result["model"], "gpt-a")
        self.assertEqual(first_result["git_branch"], "fix/a")
        self.assertEqual(first_result["request"], "Fix parser A")
        self.assertEqual(first_result["last_response"], "Parser A repaired")
        self.assertEqual(second_result["request"], "Review parser B")
        self.assertEqual(second_result["last_response"], "Parser B reviewed")
        self.assertEqual(second_result["session_id"], "thread-b")
        self.assertNotIn("cwd", first_result)
        self.assertNotIn("status", first_result)

    def test_missing_exact_id_never_uses_newest_cwd_candidate(self) -> None:
        other = self.rollout("other", message("user", "Private unrelated request"))
        self.database({"id": "TEXT", "cwd": "TEXT", "rollout_path": "TEXT", "title": "TEXT"}, [
            {"id": "other", "cwd": "/same/workspace", "rollout_path": str(other), "title": "Other thread"},
        ])
        self.jsonl("session_index.jsonl", [{"id": "other", "thread_name": "Other renamed", "updated_at": LATE}])
        self.assertEqual(CODEX.collect("missing", None, self.home), {})
        self.assertEqual(CODEX.collect("' OR 1=1 --", None, self.home), {})

    def test_readonly_database_sees_committed_live_wal(self) -> None:
        writer = self.database({"id": "TEXT PRIMARY KEY", "title": "TEXT", "model": "TEXT", "updated_at_ms": "INTEGER"}, [
            {"id": "wal-thread", "title": "Checkpointed title", "model": "old-model", "updated_at_ms": epoch(EARLY) * 1000},
        ])
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        writer.execute("UPDATE threads SET title=?, model=?, updated_at_ms=? WHERE id=?", (
            "Committed WAL title", "wal-model", epoch(LATE) * 1000 + 123, "wal-thread",
        ))
        writer.commit()
        self.assertGreater((self.home / "state_5.sqlite-wal").stat().st_size, 0)
        result = CODEX.collect("wal-thread", None, self.home)
        self.assertEqual(result["title"], "Committed WAL title")
        self.assertEqual(result["model"], "wal-model")
        self.assertEqual(result["updated_at"], "2026-10-14T12:00:00.123Z")

    def test_schema_introspection_allows_missing_optional_columns(self) -> None:
        self.database({"id": "TEXT PRIMARY KEY", "title": "TEXT"}, [{"id": "legacy", "title": "Legacy title"}])
        result = CODEX.collect("legacy", None, self.home)
        self.assertEqual(result, {
            "session_id": "legacy", "title": "Legacy title", "metadata_source": "Codex · recorded metadata",
        })

    def test_unusable_newer_database_can_fall_back_to_exact_older_schema(self) -> None:
        self.database({"cwd": "TEXT", "title": "TEXT"}, [{"cwd": "/same/workspace", "title": "Unattributable"}])
        self.database({"id": "TEXT", "name": "TEXT", "title": "TEXT"}, [
            {"id": "legacy", "name": "Human name", "title": "Original prompt title"},
        ], name="state_4.sqlite")
        result = CODEX.collect("legacy", None, self.home)
        self.assertEqual(result["title"], "Human name")
        self.assertEqual(result["session_id"], "legacy")

    def test_latest_exact_index_rename_overrides_stale_database_title(self) -> None:
        self.database({"id": "TEXT", "title": "TEXT", "updated_at": "INTEGER"}, [
            {"id": "renamed", "title": "Stale database title", "updated_at": epoch(LATE)},
        ])
        self.jsonl("session_index.jsonl", [
            {"id": "renamed", "thread_name": "First name", "updated_at": EARLY},
            {"id": "renamed", "thread_name": "Human renamed title", "updated_at": MIDDLE},
            {"id": "other", "thread_name": "Unrelated newer name", "updated_at": LATE},
        ])
        result = CODEX.collect("renamed", None, self.home)
        self.assertEqual(result["title"], "Human renamed title")
        self.assertEqual(result["updated_at"], "2026-10-14T12:00:00.000Z")
        self.assertNotIn("transcript_path", result)

    def test_exact_index_can_supply_metadata_without_database_or_rollout(self) -> None:
        self.jsonl("session_index.jsonl", [
            {"id": "indexed", "thread_name": "Recorded title", "updated_at": MIDDLE},
            {"id": "other", "thread_name": "Wrong title", "updated_at": LATE},
        ])
        result = CODEX.collect("indexed", None, self.home)
        self.assertEqual(result["session_id"], "indexed")
        self.assertEqual(result["title"], "Recorded title")
        self.assertEqual(result["updated_at"], MIDDLE)

    def test_wrong_or_ambiguous_rollout_identity_releases_no_content(self) -> None:
        cases = [
            [record("session_meta", {"id": "other"})],
            [record("session_meta", {"id": "target", "session_id": "other"})],
            [record("session_meta", {"id": "target"}), record("session_meta", {"id": "other"})],
            [record("session_meta", {"cwd": "/same/workspace"})],
            [record("session_meta", None)],
            [],
        ]
        for index, headers in enumerate(cases):
            with self.subTest(headers=headers):
                path = self.jsonl(f"wrong-{index}.jsonl", [
                    *headers, record("turn_context", {"model": "wrong-model"}),
                    message("user", "Wrong request"), message("assistant", "Wrong response"),
                ])
                self.assertEqual(CODEX.collect("target", path, self.home), {})

    def test_wrong_rollout_does_not_discard_valid_database_fields(self) -> None:
        wrong = self.rollout("other", message("assistant", "Do not expose this"))
        self.database({"id": "TEXT", "rollout_path": "TEXT", "title": "TEXT"}, [
            {"id": "target", "rollout_path": str(wrong), "title": "Correct database title"},
        ])
        result = CODEX.collect("target", wrong, self.home)
        self.assertEqual(result["title"], "Correct database title")
        self.assertNotIn("last_response", result)
        self.assertNotIn("transcript_path", result)

    def test_rejected_hook_path_can_use_independently_validated_database_rollout(self) -> None:
        wrong = self.rollout("other", message("user", "Other request"))
        correct = self.rollout("target", message("user", "Correct request"))
        self.database({"id": "TEXT", "rollout_path": "TEXT"}, [{"id": "target", "rollout_path": str(correct)}])
        result = CODEX.collect("target", wrong, self.home)
        self.assertEqual(result["request"], "Correct request")
        self.assertEqual(result["transcript_path"], str(correct))

    def test_recorded_model_branch_and_timestamps_are_attributed_by_record_time(self) -> None:
        path = self.jsonl("model.jsonl", [
            record("session_meta", {"id": "model-thread", "git": {"branch": "initial-branch"}}),
            record("turn_context", {"model": "older-model"}),
        ])
        writer = self.database({
            "id": "TEXT", "model": "TEXT", "git_branch": "TEXT", "updated_at_ms": "INTEGER", "updated_at": "INTEGER",
        }, [{"id": "model-thread", "model": "database-model", "git_branch": "current-branch",
             "updated_at_ms": epoch(MIDDLE) * 1000, "updated_at": epoch(EARLY)}])
        result = CODEX.collect("model-thread", path, self.home)
        self.assertEqual(result["model"], "database-model")
        self.assertEqual(result["git_branch"], "current-branch")
        self.assertEqual(result["updated_at"], "2026-10-14T11:00:00.000Z")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record("turn_context", {"model": "latest-recorded-model"}, LATE)) + "\n")
        writer.execute("UPDATE threads SET updated_at_ms=NULL")
        writer.commit()
        result = CODEX.collect("model-thread", path, self.home)
        self.assertEqual(result["model"], "latest-recorded-model")
        self.assertEqual(result["git_branch"], "initial-branch")
        self.assertEqual(result["updated_at"], LATE)

    def test_last_model_call_usage_is_not_cumulative_or_double_counted(self) -> None:
        path = self.rollout("usage", record("event_msg", {
            "type": "token_count", "info": {
                "last_token_usage": {"input_tokens": 1200, "cached_input_tokens": 800,
                                     "output_tokens": 300, "reasoning_output_tokens": 200},
                "total_token_usage": {"input_tokens": 90000, "output_tokens": 8000},
            },
        }), record("event_msg", {"type": "token_count", "info": None}))
        result = CODEX.collect("usage", path, self.home)
        self.assertEqual(result["usage"], "Last model call: 1200 in / 300 out")

    def test_partial_and_cumulative_counts_never_become_session_totals(self) -> None:
        self.database({"id": "TEXT", "tokens_used": "INTEGER"}, [{"id": "partial", "tokens_used": 99999}])
        path = self.rollout("partial", *[
            record("event_msg", {"type": "token_count", "info": info}) for info in (
                {"total_token_usage": {"input_tokens": 8000, "output_tokens": 500}},
                {"last_token_usage": {"input_tokens": 100}},
                {"last_token_usage": {"input_tokens": True, "output_tokens": 10}},
                {"last_token_usage": {"input_tokens": -1, "output_tokens": 10}},
                {"last_token_usage": {"input_tokens": "100", "output_tokens": 10}},
            )
        ])
        result = CODEX.collect("partial", path, self.home)
        self.assertNotIn("usage", result)
        self.assertNotIn("tokens_used", result)

    def test_malformed_partial_records_and_tool_payloads_do_not_replace_plain_text(self) -> None:
        path = self.rollout("partial-records",
            record("turn_context", {"model": "recorded-model"}),
            record("event_msg", {"type": "user_message", "message": "Latest\nrecorded user request"}),
            message("assistant", "Earlier assistant answer"),
            record("event_msg", {"type": "task_complete", "last_agent_message": "Final plain\nassistant answer"}, LATE),
            record("response_item", {"type": "function_call_output", "output": "SECRET TOOL PAYLOAD"}, LATE),
            record("response_item", {"type": "reasoning", "summary": [{"text": "SECRET REASONING"}]}, LATE),
            message("developer", "SECRET INSTRUCTIONS", LATE),
            record("turn_context", {"model": None}, LATE),
            record("response_item", {"type": "message", "role": "assistant", "content": [None, {"type": "image"}]}, LATE),
            record("event_msg", ["malformed"], LATE),
        )
        with path.open("a", encoding="utf-8") as stream:
            stream.write('not-json\n{"type":"turn_context","payload":{"model":"incomplete"')
        result = CODEX.collect("partial-records", path, self.home)
        self.assertEqual(result["request"], "Latest recorded user request")
        self.assertEqual(result["last_response"], "Final plain assistant answer")
        self.assertEqual(result["model"], "recorded-model")
        self.assertEqual(result["updated_at"], LATE)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_large_transcript_keeps_latest_bounded_text_and_header_identity(self) -> None:
        path = self.rollout("large")
        filler = json.dumps(record("response_item", {"type": "function_call_output", "output": "x" * 8192})) + "\n"
        with path.open("a", encoding="utf-8") as stream:
            for _ in range(512):
                stream.write(filler)
            for entry in (
                record("turn_context", {"model": "gpt-latest"}, LATE),
                message("user", "Latest request " + "q" * 1000, LATE),
                message("assistant", "Latest response " + "a" * 1000, LATE),
            ):
                stream.write(json.dumps(entry) + "\n")
        self.jsonl("session_index.jsonl", [{"id": "large", "thread_name": "Renamed " + "t" * 300, "updated_at": LATE}])
        result = CODEX.collect("large", path, self.home)
        self.assertEqual(result["session_id"], "large")
        self.assertEqual(result["model"], "gpt-latest")
        self.assertTrue(result["request"].startswith("Latest request "))
        self.assertTrue(result["last_response"].startswith("Latest response "))
        self.assertLessEqual(len(result["request"]), 300)
        self.assertLessEqual(len(result["last_response"]), 300)
        self.assertLessEqual(len(result["title"]), 120)
        self.assertEqual(set(result), {
            "session_id", "model", "request", "last_response", "title", "updated_at",
            "transcript_path", "metadata_source",
        })

    def test_broken_database_does_not_hide_valid_direct_rollout(self) -> None:
        (self.home / "state_5.sqlite").write_bytes(b"incomplete sqlite file")
        path = self.jsonl("direct.jsonl", [
            record("session_meta", {"session_id": "direct", "git": {"branch": "direct-branch"}}),
            message("user", "Direct recorded request"),
        ])
        result = CODEX.collect("direct", path, self.home)
        self.assertEqual(result["git_branch"], "direct-branch")
        self.assertEqual(result["request"], "Direct recorded request")
        self.assertEqual(result["transcript_path"], str(path))


if __name__ == "__main__":
    unittest.main()
