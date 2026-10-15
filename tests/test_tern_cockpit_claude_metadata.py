from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / "tern/plugins/agent-cockpit"
sys.path.insert(0, str(PLUGIN))
SPEC = importlib.util.spec_from_file_location("cockpit_claude_metadata", PLUGIN / "metadata_claude.py")
CLAUDE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLAUDE)
sys.path.pop(0)

SESSION = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def record(kind: str, **values: object) -> dict:
    return {"type": kind, "sessionId": SESSION, **values}


def assistant(text: object, model: str = "claude-sonnet-4-6", **values: object) -> dict:
    message = {"model": model, "content": text, **values}
    return record("assistant", message=message)


class ClaudeMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "claude"

    def transcript(self, entries: list[dict], session: str = SESSION, project: str = "workspace") -> Path:
        path = self.config / "projects" / project / f"{session}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        return path

    def collect(self, path: Path | None = None, session: str = SESSION) -> dict:
        return CLAUDE.collect(session, path, self.config)

    def test_exact_uuid_not_newest_or_same_cwd(self) -> None:
        wanted = self.transcript([
            record("user", cwd="/same", message={"content": "My request"}),
            record("ai-title", aiTitle="My session"),
        ])
        self.transcript([
            {"type": "ai-title", "sessionId": OTHER, "cwd": "/same", "aiTitle": "Wrong session"},
        ], session=OTHER)
        result = self.collect()
        self.assertEqual(result["title"], "My session")
        self.assertEqual(result["request"], "My request")
        self.assertEqual(result["session_id"], SESSION)
        self.assertEqual(result["transcript_path"], str(wanted))
        self.assertNotIn("status", result)
        self.assertNotIn("cwd", result)

    def test_hook_path_is_exact_and_need_not_be_under_projects(self) -> None:
        self.transcript([record("ai-title", aiTitle="Not selected")])
        hook = self.root / "hook-selected.jsonl"
        hook.write_text(json.dumps(record("ai-title", aiTitle="Hook selected")) + "\n")
        self.assertEqual(self.collect(hook)["title"], "Hook selected")

    def test_wrong_internal_identity_cannot_use_hook_or_uuid_filename(self) -> None:
        path = self.transcript([{"type": "ai-title", "sessionId": OTHER, "aiTitle": "Wrong"}])
        self.assertEqual(self.collect(path), {})
        self.assertEqual(self.collect(), {})

    def test_missing_hook_does_not_fall_back_to_other_transcript(self) -> None:
        self.transcript([record("ai-title", aiTitle="Exists elsewhere")])
        self.assertEqual(self.collect(self.root / "missing.jsonl"), {})

    def test_duplicate_exact_uuid_paths_are_ambiguous_without_hook(self) -> None:
        first = self.transcript([record("ai-title", aiTitle="First")], project="one")
        self.transcript([record("ai-title", aiTitle="Second")], project="two")
        self.assertEqual(self.collect(), {})
        self.assertEqual(self.collect(first)["title"], "First")

    def test_non_uuid_lookup_cannot_escape_projects(self) -> None:
        self.assertEqual(self.collect(session="../../outside"), {})
        self.assertEqual(self.collect(session="*"), {})
        self.assertEqual(self.collect(session=""), {})

    def test_unidentified_and_mixed_identity_records_are_not_metadata(self) -> None:
        missing = self.transcript([{"type": "ai-title", "aiTitle": "No identity"}])
        self.assertEqual(self.collect(missing), {})
        mixed = self.transcript([
            record("ai-title", aiTitle="Matching"),
            {"type": "ai-title", "sessionId": OTHER, "aiTitle": "Other"},
        ])
        self.assertEqual(self.collect(mixed), {})

    def test_sidechains_are_ignored_before_identity_or_field_extraction(self) -> None:
        path = self.transcript([
            record("ai-title", aiTitle="Main title"),
            assistant("Main response", usage={"input_tokens": 12, "output_tokens": 8}),
            record("assistant", sessionId=OTHER, isSidechain=True,
                   timestamp="2099-01-01T00:00:00Z", gitBranch="wrong",
                   message={"model": "wrong", "content": "Sidechain text"}),
            record("custom-title", isSidechain=True, customTitle="Wrong title"),
        ])
        result = self.collect(path)
        self.assertEqual(result["title"], "Main title")
        self.assertEqual(result["last_response"], "Main response")
        self.assertEqual(result["model"], "claude-sonnet-4-6")
        self.assertNotIn("git_branch", result)
        self.assertNotIn("updated_at", result)
        only_sidechain = self.transcript([record("ai-title", isSidechain=True, aiTitle="Hidden")])
        self.assertEqual(self.collect(only_sidechain), {})

    def test_actual_ai_title_rename_and_custom_title_precedence(self) -> None:
        path = self.transcript([
            record("ai-title", aiTitle="Initial suggestion"),
            record("custom-title", customTitle="First manual name"),
            record("custom-title", customTitle="My chosen name"),
            record("ai-title", aiTitle="Later AI suggestion"),
            record("custom-title", customTitle=None),
        ])
        self.assertEqual(self.collect(path)["title"], "My chosen name")
        path = self.transcript([
            record("ai-title", aiTitle="Old AI title"),
            record("ai-title", aiTitle="Latest AI title"),
        ])
        self.assertEqual(self.collect(path)["title"], "Latest AI title")

    def test_latest_plain_text_model_branch_and_recorded_timestamp(self) -> None:
        path = self.transcript([
            record("user", message={"content": "Earlier request"}),
            assistant("Earlier response", model="claude-opus-4-6"),
            record("user", message={"content": [
                {"type": "text", "text": "Latest"},
                {"type": "image", "source": {"data": "not text"}},
                {"type": "text", "text": "request"},
            ]}),
            assistant([
                {"type": "thinking", "thinking": "Private reasoning"},
                {"type": "text", "text": "Latest"},
                {"type": "text", "text": "answer"},
            ], model="claude-opus-5-5"),
            record("user", isMeta=True, message={"content": "Internal context"}),
            record("user", message={"content": [
                {"type": "tool_result", "content": "Tool output is not a request"},
            ]}),
            record("assistant", timestamp="2026-10-14T10:20:30Z", gitBranch="feature/metadata",
                   message={"model": "claude-sonnet-5", "content": [
                       {"type": "tool_use", "name": "bash", "input": {"command": "secret"}},
                   ]}),
        ])
        result = self.collect(path)
        self.assertEqual(result["request"], "Latest request")
        self.assertEqual(result["last_response"], "Latest answer")
        self.assertEqual(result["model"], "claude-sonnet-5")
        self.assertEqual(result["git_branch"], "feature/metadata")
        self.assertEqual(result["updated_at"], "2026-10-14T10:20:30Z")

    def test_local_slash_command_is_not_a_model_request(self) -> None:
        command = record("user", message={"content": (
            "<command-name>/clear</command-name>\n"
            "  <command-message>clear</command-message>\n"
            "  <command-args></command-args>"
        )})
        path = self.transcript([command])
        self.assertNotIn("request", self.collect(path))
        path = self.transcript([
            record("user", message={"content": "Actual model request"}),
            command,
        ])
        self.assertEqual(self.collect(path)["request"], "Actual model request")

    def test_latest_usage_is_not_a_partial_session_total_or_cache_omission(self) -> None:
        path = self.transcript([
            assistant("First", usage={"input_tokens": 1000, "output_tokens": 300}),
            assistant("Latest", usage={"input_tokens": 12, "output_tokens": 7,
                                       "cache_read_input_tokens": 200, "cache_creation_input_tokens": 50}),
            record("cost-state", totalCostUSD=12.5, modelUsage={"other": {"inputTokens": 9999}}),
        ])
        self.assertEqual(
            self.collect(path)["usage"],
            "Latest provider response record: 12 uncached input / 7 output tokens; 200 cache read; 50 cache write",
        )

    def test_missing_or_invalid_latest_usage_does_not_relabel_older_counters(self) -> None:
        for invalid in (None, {}, {"input_tokens": 5}, {"input_tokens": True, "output_tokens": 2},
                        {"input_tokens": -1, "output_tokens": 3}, {"input_tokens": "5", "output_tokens": 3}):
            with self.subTest(usage=invalid):
                path = self.transcript([
                    assistant("Old", usage={"input_tokens": 1000, "output_tokens": 300}),
                    assistant("New", usage=invalid),
                ])
                result = self.collect(path)
                self.assertEqual(result["last_response"], "New")
                self.assertNotIn("usage", result)

    def test_synthetic_model_is_not_a_recorded_provider_model(self) -> None:
        path = self.transcript([
            assistant("Reply", model="claude-opus-5-5", usage={"input_tokens": 20, "output_tokens": 4}),
            assistant("Local API error", model="<synthetic>", usage={"input_tokens": 0, "output_tokens": 0}),
        ])
        result = self.collect(path)
        self.assertEqual(result["model"], "claude-opus-5-5")
        self.assertEqual(result["last_response"], "Local API error")
        self.assertIn("20 uncached input / 4 output", result["usage"])

    def test_partial_malformed_and_missing_fields_keep_only_validated_data(self) -> None:
        path = self.transcript([
            record("mode", mode="default"),
            record("user", message=None),
            assistant([None, {"type": "text", "text": 123}, {"type": "text", "text": "Useful"}]),
            {"type": "ai-title", "aiTitle": "Unidentified title"},
        ])
        with path.open("a") as stream:
            stream.write('not json\n{"type":"assistant","sessionId":')
        result = self.collect(path)
        self.assertEqual(result["session_id"], SESSION)
        self.assertEqual(result["last_response"], "Useful")
        self.assertNotIn("title", result)
        self.assertNotIn("request", result)
        self.assertNotIn("usage", result)

    def test_human_fields_are_bounded_and_single_line(self) -> None:
        path = self.transcript([
            record("ai-title", aiTitle="Title\n" + "x" * 500),
            record("user", message={"content": "Request\n" + "x" * 800}),
            assistant("Response\n" + "y" * 800, model="Model\n" + "z" * 300),
        ])
        result = self.collect(path)
        for field, limit in (("title", 120), ("request", 300), ("last_response", 300), ("model", 100)):
            self.assertLessEqual(len(result[field]), limit)
            self.assertNotIn("\n", result[field])


if __name__ == "__main__":
    unittest.main()
