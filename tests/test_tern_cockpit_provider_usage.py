"""Provider accounting boundaries using the installed providers' recorded schemas."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "tern/plugins/agent-cockpit"
sys.path.insert(0, str(PLUGIN))
import metadata_claude as claude
import metadata_codex as codex
import metadata_omp as omp
import metadata_usage as usage

SESSION = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
METRICS = ("session_tokens", "session_cost", "context_usage", "subagents", "usage_source")


def claude_response(identity, incoming, outgoing, **extra):
    return {"type": "assistant", "sessionId": SESSION, "message": {
        "id": identity, "model": "claude-opus-5-5", "content": "Private response text",
        "usage": {"input_tokens": incoming, "output_tokens": outgoing,
                  "cache_read_input_tokens": 20, "cache_creation_input_tokens": 5},
    }, **extra}


def codex_count(incoming, outgoing, *, prompt=40, capacity=100):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": incoming, "output_tokens": outgoing,
                              "cached_input_tokens": 20, "cache_write_input_tokens": 0},
        "last_token_usage": {"input_tokens": prompt, "output_tokens": 3},
        "model_context_window": capacity,
    }}}


class ProviderUsageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache")})
        environment.start()
        self.addCleanup(environment.stop)

    def transcript(self, records, name="session.jsonl"):
        path = self.root / name
        path.write_text("".join(json.dumps(record) + "\n" for record in records))
        return path

    def append(self, path, *records):
        with path.open("a") as stream:
            stream.write("".join(json.dumps(record) + "\n" for record in records))

    def collect_claude(self, path):
        return claude.collect(SESSION, path, self.root)

    def collect_codex(self, path):
        return codex.collect(SESSION, path, self.root)

    def codex_transcript(self, *records):
        return self.transcript([{"type": "session_meta", "payload": {"id": SESSION}}, *records])

    def test_claude_streaming_blocks_deduplicate_by_message_id_across_polls(self):
        path = self.transcript([
            claude_response("msg-first", 10, 1),
            claude_response("msg-first", 10, 8),
            claude_response("msg-second", 12, 3),
        ])
        result = self.collect_claude(path)
        self.assertIn("22 input / 11 output", result["session_tokens"])
        self.assertIn("40 cache read; 10 cache write", result["session_tokens"])
        self.assertIn("37 input tokens", result["context_usage"])
        self.append(path, claude_response("msg-second", 12, 7))
        self.assertIn("22 input / 15 output", self.collect_claude(path)["session_tokens"])
        self.assertEqual(self.collect_claude(path)["session_tokens"], self.collect_claude(path)["session_tokens"])

    def test_claude_cost_state_is_latest_reported_estimate_not_summed(self):
        path = self.transcript([
            claude_response("msg-one", 100, 8),
            {"type": "cost-state", "sessionId": SESSION, "totalCostUSD": 10.0},
            {"type": "cost-state", "sessionId": SESSION, "totalCostUSD": 2.5,
             "hasUnknownModelCost": True, "modelUsage": {"reported-model": {
                 "inputTokens": 300, "outputTokens": 50,
                 "cacheReadInputTokens": 100, "cacheCreationInputTokens": 20}}},
        ])
        result = self.collect_claude(path)
        self.assertIn("$2.500000", result["session_cost"])
        self.assertIn("not billing", result["session_cost"])
        self.assertIn("unknown model cost", result["session_cost"])
        self.assertIn("Provider session snapshot: 300 input / 50 output", result["session_tokens"])

    def test_claude_records_unique_agent_results_not_tool_calls_or_nested_files(self):
        path = self.transcript([
            claude_response("msg", 1, 1),
            {"type": "user", "sessionId": SESSION, "toolUseResult": {"agentId": "agent-a"}},
            {"type": "user", "sessionId": SESSION, "toolUseResult": {"agentId": "agent-a"}},
            {"type": "user", "sessionId": SESSION, "toolUseResult": {"agentId": "agent-b"}},
            claude_response("other", 9999, 999, isSidechain=True),
        ])
        self.transcript([{"agentId": "unrelated", "sessionId": OTHER}], "unrelated.jsonl")
        result = self.collect_claude(path)
        self.assertEqual(result["subagents"], "2 recorded unique agents (not live)")
        self.assertIn("1 input / 1 output", result["session_tokens"])

    def test_missing_identity_or_usage_is_unavailable_not_zero(self):
        missing = claude_response("msg", 2, 1)
        del missing["message"]["id"]
        path = self.transcript([missing])
        result = self.collect_claude(path)
        self.assertIn("Unavailable", result["session_tokens"])
        self.assertIn("no Claude cost-state", result["session_cost"])
        self.assertIn("no recorded agent identities", result["subagents"])
        self.assertNotIn("0 recorded", result["subagents"])

    def test_codex_snapshots_are_not_added_and_context_uses_last_request(self):
        snapshot = codex_count(200, 10)
        path = self.codex_transcript(codex_count(100, 5), snapshot, snapshot)
        result = self.collect_codex(path)
        self.assertIn("Provider cumulative snapshot: 200 input / 10 output", result["session_tokens"])
        self.assertIn("40 input tokens / 100 capacity (40.0%)", result["context_usage"])
        self.assertIn("does not report monetary cost", result["session_cost"])
        self.append(path, codex_count(250, 15))
        self.assertIn("250 input / 15 output", self.collect_codex(path)["session_tokens"])

    def test_codex_reset_is_not_fabricated_lifetime_total(self):
        path = self.codex_transcript(codex_count(200, 10), codex_count(20, 2))
        result = self.collect_codex(path)
        self.assertIn("20 input / 2 output", result["session_tokens"])
        self.assertIn("counter reset/rebase observed, not full session", result["session_tokens"])
        self.assertNotIn("220 input", result["session_tokens"])

    def test_codex_agents_require_exact_sender_and_unique_spawned_thread(self):
        def spawn(sender, child):
            return {"type": "event_msg", "payload": {"type": "collab_agent_spawn_end",
                    "sender_thread_id": sender, "new_thread_id": child}}
        path = self.codex_transcript(spawn(SESSION, "one"), spawn(SESSION, "one"),
                                     spawn(OTHER, "foreign"), spawn(SESSION, SESSION))
        self.assertEqual(self.collect_codex(path)["subagents"], "1 recorded unique agents (not live)")

    def test_omp_owned_advisors_without_parent_header_do_not_hide_root(self):
        root = self.transcript([{"type": "session", "id": SESSION},
                                {"type": "title", "title": "Root conversation"}], "session.2026.jsonl")
        directory = root.with_suffix("")
        directory.mkdir()
        proc = self.root / "proc/55/fd"
        proc.mkdir(parents=True)
        (proc / "44").symlink_to(root)
        for index, name in enumerate(("__advisor.jsonl", "__advisor.security.jsonl")):
            advisor = directory / name
            advisor.write_text(json.dumps({"type": "session", "id": f"advisor-{index}"}) + "\n")
            (proc / str(45 + index)).symlink_to(advisor)
        result = omp.collect(55, self.root / "proc")
        self.assertEqual(result["session_id"], SESSION)
        self.assertEqual(result["title"], "Root conversation")
        self.assertEqual(result["transcript_path"], str(root))
        # Owned advisors alone cannot become the attributed pane conversation.
        (proc / "44").unlink()
        self.assertEqual(omp.collect(55, self.root / "proc"), {})

    def test_omp_advisor_name_without_owner_layout_is_not_blindly_ignored(self):
        root = self.transcript([{"type": "session", "id": SESSION}])
        unrelated = self.transcript([{"type": "session", "id": OTHER}], "__advisor.jsonl")
        proc = self.root / "proc/55/fd"
        proc.mkdir(parents=True)
        (proc / "44").symlink_to(root)
        (proc / "45").symlink_to(unrelated)
        self.assertEqual(omp.collect(55, self.root / "proc"), {})

    def test_omp_owned_advisor_does_not_relax_independent_root_ambiguity(self):
        root = self.transcript([{"type": "session", "id": SESSION}])
        directory = root.with_suffix("")
        directory.mkdir()
        advisor = directory / "__advisor.jsonl"
        advisor.write_text(json.dumps({"type": "session", "id": "advisor"}) + "\n")
        other = self.transcript([{"type": "session", "id": OTHER}], "independent.jsonl")
        proc = self.root / "proc/55/fd"
        proc.mkdir(parents=True)
        for index, path in enumerate((root, advisor, other)):
            (proc / str(44 + index)).symlink_to(path)
        self.assertEqual(omp.collect(55, self.root / "proc"), {})

    def test_omp_async_progress_and_results_share_unique_recorded_agent_ids(self):
        def task(details, name="task"):
            return {"type": "message", "message": {
                "role": "toolResult", "toolName": name, "details": details}}
        path = self.transcript([
            {"type": "session", "id": SESSION},
            task({"results": [], "progress": [{"id": "worker-a", "status": "running"},
                                             {"id": "worker-b", "status": "pending"}],
                  "async": {"state": "running", "type": "task", "jobId": "bg-1"}}),
            task({"results": [{"id": "worker-a"}], "progress": [{"id": "worker-a", "status": "completed"}]}),
            task({"results": [{"id": "not-a-task-agent"}], "progress": [{"id": "unrelated"}]}, name="read"),
        ])
        proc = self.root / "proc/55/fd"
        proc.mkdir(parents=True)
        (proc / "44").symlink_to(path)
        result = omp.collect(55, self.root / "proc")
        self.assertEqual(result["subagents"], "2 recorded unique agents (not live)")
        self.append(path, task({"results": [{"id": "worker-b"}], "progress": []}))
        self.assertEqual(omp.collect(55, self.root / "proc")["subagents"], result["subagents"])

    def test_omp_root_and_auxiliary_usage_are_deduplicated_without_task_spend(self):
        def response(entry, incoming, outgoing):
            return {"type": "message", "id": entry, "message": {"role": "assistant",
                    "content": [], "usage": {"input": incoming, "output": outgoing,
                    "cacheRead": 30, "cacheWrite": 4, "cost": {"total": 0.25}},
                    "contextSnapshot": {"promptTokens": 123}}}
        first = response("first", 10, 2)
        path = self.transcript([
            {"type": "session", "id": SESSION}, first, first, response("second", 20, 3),
            {"type": "model_usage", "id": "auxiliary", "usage": {"input": 5, "output": 1,
                "cacheRead": 0, "cacheWrite": 0, "cost": {"total": 0.1}}},
            {"type": "message", "id": "tool", "message": {"role": "toolResult", "toolName": "task",
                "details": {"usage": {"input": 9999}, "results": [{"id": "worker"}, {"id": "worker"}]}}},
        ])
        proc = self.root / "proc/55/fd"
        proc.mkdir(parents=True)
        (proc / "44").symlink_to(path)
        result = omp.collect(55, self.root / "proc")
        self.assertIn("35 input / 6 output", result["session_tokens"])
        self.assertIn("$0.600000", result["session_cost"])
        self.assertIn("Provider estimate:", result["session_cost"])
        self.assertIn("not billing", result["session_cost"])
        self.assertIn("123 input tokens", result["context_usage"])
        self.assertEqual(result["subagents"], "1 recorded unique agents (not live)")
        self.assertIn("excludes child usage", result["usage_source"])

    def test_incremental_index_does_not_publish_partial_total_or_store_text(self):
        path = self.transcript([claude_response(f"msg-{index}", 10, 2) for index in range(12)])
        with patch.object(usage, "READ_BUDGET", 1024):
            first = self.collect_claude(path)
            self.assertIn("Unavailable:", first["session_tokens"])
            self.assertNotIn("complete recorded file", first["usage_source"])
            for _ in range(12):
                result = self.collect_claude(path)
                if "complete recorded file" in result["usage_source"]:
                    break
            self.assertIn("120 input / 24 output", result["session_tokens"])
        for cache in (self.root / "cache").rglob("*.json"):
            encoded = cache.read_text()
            self.assertNotIn("Private response text", encoded)
            self.assertNotIn("msg-", encoded)
            self.assertNotIn(SESSION, encoded)

    def test_partial_final_record_is_retried_once_complete(self):
        path = self.transcript([claude_response("one", 10, 2)])
        self.assertIn("10 input", self.collect_claude(path)["session_tokens"])
        partial = json.dumps(claude_response("two", 20, 3))
        with path.open("a") as stream:
            stream.write(partial[:80])
        self.assertIn("Unavailable:", self.collect_claude(path)["session_tokens"])
        with path.open("a") as stream:
            stream.write(partial[80:] + "\n")
        self.assertIn("30 input / 5 output", self.collect_claude(path)["session_tokens"])

    def test_truncation_replacement_and_same_size_rewrite_discard_cached_totals(self):
        path = self.transcript([claude_response("one", 80, 2), claude_response("two", 20, 3)])
        self.assertIn("100 input", self.collect_claude(path)["session_tokens"])
        path.write_text(json.dumps(claude_response("new", 10, 1)) + "\n")
        self.assertIn("10 input / 1 output", self.collect_claude(path)["session_tokens"])
        replacement = self.transcript([claude_response("new", 30, 1)], "replacement.jsonl")
        replacement.replace(path)
        self.assertIn("30 input / 1 output", self.collect_claude(path)["session_tokens"])
        old_size = path.stat().st_size
        path.write_text(json.dumps(claude_response("new", 70, 1)) + "\n")
        self.assertEqual(path.stat().st_size, old_size)
        self.assertIn("70 input / 1 output", self.collect_claude(path)["session_tokens"])

    def test_malformed_records_never_claim_complete_totals_and_oversized_are_disclosed(self):
        path = self.transcript([claude_response("one", 10, 2)])
        with path.open("a") as stream:
            stream.write("not-json\n")
        self.assertIn("incomplete", self.collect_claude(path)["usage_source"])
        path = self.transcript([claude_response("one", 10, 2)], "oversized.jsonl")
        with path.open("a") as stream:
            stream.write(json.dumps({"padding": "x" * (usage.MAX_LINE + 10)}) + "\n")
            stream.write(json.dumps(claude_response("two", 20, 3)) + "\n")
        result = self.collect_claude(path)
        # Attachments over 1 MiB are not usage records; totals stay, and the skip is disclosed.
        self.assertIn("30 input / 5 output", result["session_tokens"])
        self.assertIn("1 oversized records (>1 MiB) skipped", result["usage_source"])

    def test_other_session_in_unsampled_middle_cannot_contribute_totals(self):
        path = self.transcript([claude_response("one", 10, 2),
                                {"padding": "x" * 700000},
                                claude_response("foreign", 9999, 999, sessionId=OTHER),
                                {"padding": "x" * 700000},
                                claude_response("last", 1, 1)])
        self.assertEqual(self.collect_claude(path), {})
        different = self.transcript([claude_response("one", 200, 2)], "different.jsonl")
        isolated = self.transcript([claude_response("one", 10, 2)], "isolated.jsonl")
        self.assertIn("200 input", self.collect_claude(different)["session_tokens"])
        self.assertIn("10 input", self.collect_claude(isolated)["session_tokens"])

    def test_metric_strings_are_bounded_and_single_line(self):
        path = self.codex_transcript(codex_count(10**15, 10**12, prompt=999999, capacity=1000000))
        result = self.collect_codex(path)
        for key in METRICS:
            self.assertIsInstance(result[key], str)
            self.assertLessEqual(len(result[key]), 300)
            self.assertNotIn("\n", result[key])


if __name__ == "__main__":
    unittest.main()
