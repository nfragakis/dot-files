"""Consumer-visible ownership and bounded-output regressions; no live providers."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "tern" / "plugins" / "agent-cockpit"
sys.path.insert(0, str(PLUGIN))
SPEC = importlib.util.spec_from_file_location("tern_cockpit_metadata", PLUGIN / "metadata.py")
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)
import metadata_omp


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.root / "cache")})
        environment.start()
        self.addCleanup(environment.stop)
        self.proc = self.root / "proc"
        self.home = self.root / "home"
        self.state = self.root / "state"
        self.pid = 321
        self.pane = "25769803778"
        self.socket = str(self.root / "isolated.sock")
        self.environment = {
            "HOME": str(self.home), "XDG_STATE_HOME": str(self.state),
            "TERN_DAEMON_SOCKET": self.socket,
        }
        self.target_environment = dict(self.environment, TERN_PANE=self.pane)
        self.payload = {"panes": [{"key": "local:codex", "provider": "omp", "pane": self.pane}]}
        self.snapshot = {"pane": int(self.pane), "child": {"pid": self.pid}, "foreground": {"pid": self.pid}}
        self.process("omp")
        self.query = patch.object(metadata, "_query_process", return_value=self.snapshot)
        self.query.start()
        self.addCleanup(self.query.stop)

    def process(self, provider, *, pid=None, started="1234", arguments=()):
        pid = self.pid if pid is None else pid
        path = self.proc / str(pid)
        (path / "fd").mkdir(parents=True, exist_ok=True)
        # stat's comm can itself contain spaces and closing parentheses.
        fields = ["S"] + ["0"] * 18 + [started] + ["0"] * 5
        (path / "stat").write_text(f"{pid} (provider ) worker) " + " ".join(fields))
        (path / "cmdline").write_bytes(b"\0".join(part.encode() for part in (provider, *arguments)) + b"\0")
        (path / "environ").write_bytes(b"\0".join(f"{key}={value}".encode() for key, value in self.target_environment.items()) + b"\0")

    def transcript(self, name, rows):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def attach(self, path, fd=44):
        (self.proc / str(self.pid) / "fd" / str(fd)).symlink_to(path)

    def root_session(self, name="current.jsonl", identity="root-session", **extra):
        return self.transcript(name, [
            {"type": "title", "title": "Live FD title"},
            {"type": "session", "id": identity, "cwd": "/same/project", **extra},
            {"type": "model_change", "model": "provider/recorded-model"},
            {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "Recorded request"}]}},
        ])

    def collect(self):
        return metadata.collect(self.payload, self.environment, self.proc)["rows"]

    def hook(self, provider_name="claude", **changes):
        provider = provider_name
        self.process(provider)
        self.payload["panes"][0]["provider"] = provider
        path = self.transcript("claude/session.jsonl", [
            {"type": "ai-title", "sessionId": "current-session", "aiTitle": "Correct conversation"},
            {"type": "assistant", "sessionId": "current-session", "message": {"model": "recorded-model", "content": [{"type": "text", "text": "Recorded response"}]}},
        ])
        record = {
            "provider": provider, "pane": self.pane, "pid": self.pid,
            "started": "1234", "session_id": "current-session", "socket": self.socket,
            "config_dir": str(self.home / ".claude"), "transcript_path": str(path),
        }
        record.update(changes)
        name = provider + "-" + hashlib.sha256(self.pane.encode()).hexdigest() + ".json"
        self.record_path = self.state / "tern" / "agent-cockpit" / "sessions" / name
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        self.record_path.write_text(json.dumps(record))
        return record

    def lifecycle(self, **changes):
        value = {
            "status": "working", "activity": "Running Read", "event": "PreToolUse",
            "observed_at": "2020-01-01T00:00:00.000000Z",
        }
        value.update(changes)
        return value

    @unittest.skipUnless(shutil.which("git"), "Git is required for workspace observations")
    def test_workspace_uses_native_process_cwd_not_requested_or_transcript_cwd(self):
        owned, decoy = self.root / "owned", self.root / "decoy"
        for directory, branch in ((owned, "owned-branch"), (decoy, "decoy-branch")):
            subprocess.run(["git", "init", "-q", "-b", branch, str(directory)], check=True, capture_output=True)
        (self.proc / str(self.pid) / "cwd").symlink_to(owned)
        item = self.payload["panes"][0]
        item.update(workspace=True, cwd=str(decoy))
        row = self.collect()[item["key"]]
        self.assertIn("owned-branch", row["workspace_branch"])
        self.assertNotIn("decoy-branch", row["workspace_branch"])

    @unittest.skipUnless(shutil.which("git"), "Git is required for workspace observations")
    def test_workspace_change_during_collection_drops_previous_repository_data(self):
        import metadata_workspace

        owned, replacement = self.root / "owned", self.root / "replacement"
        for directory in (owned, replacement):
            subprocess.run(["git", "init", "-q", "-b", "main", str(directory)], check=True, capture_output=True)
        cwd = self.proc / str(self.pid) / "cwd"
        cwd.symlink_to(owned)
        self.payload["panes"][0]["workspace"] = True
        collect = metadata_workspace.collect

        def changing(path, **kwargs):
            result = collect(path, **kwargs)
            cwd.unlink()
            cwd.symlink_to(replacement)
            return result

        with patch.object(metadata_workspace, "collect", side_effect=changing):
            self.assertEqual(self.collect(), {})

    def test_lifecycle_uses_exact_native_process_not_title_or_cwd(self):
        self.hook(lifecycle=self.lifecycle())
        self.payload.update(title="unrelated title", cwd="/different/project")
        row = self.collect()["local:codex"]
        self.assertEqual(row["session_id"], "current-session")
        self.assertEqual(row["lifecycle"], self.lifecycle())

    def test_hook_lifecycle_does_not_depend_on_transcript_creation_or_freshness(self):
        for status, event, activity in (
            ("working", "PostToolUseFailure", "Tool failed · continuing"),
            ("waiting_input", "PermissionRequest", "Permission required"),
            ("idle", "Stop", "Ready"),
            ("exited", "SessionEnd", "Session ended"),
        ):
            with self.subTest(status=status):
                phase = self.lifecycle(status=status, event=event, activity=activity)
                record = self.hook(lifecycle=phase)
                Path(record["transcript_path"]).unlink()
                row = self.collect()["local:codex"]
                self.assertEqual(row["lifecycle"], phase)
                self.assertEqual(row["session_id"], "current-session")
                self.assertNotIn("status", row)
                self.assertNotIn("failed", row["lifecycle"]["status"])

    def test_lifecycle_probe_returns_only_the_exact_phase(self):
        self.hook(lifecycle=self.lifecycle())
        self.payload["panes"][0]["lifecycle"] = True
        with patch.object(metadata.metadata_claude, "collect", side_effect=AssertionError("transcript read")):
            row = self.collect()["local:codex"]
        self.assertEqual(row, {"lifecycle": self.lifecycle()})
        self.hook(lifecycle=self.lifecycle(), pid=self.pid + 1)
        self.assertEqual(self.collect(), {}, "the probe keeps exact-owner attribution")

    def test_only_exact_hook_owner_exposes_lifecycle(self):
        for changes in (
            {"provider": "codex"}, {"pane": "another-pane"}, {"pid": self.pid + 1},
            {"started": "old-process"}, {"socket": "/other.sock"}, {"session_id": ""},
        ):
            with self.subTest(changes=changes):
                self.hook(lifecycle=self.lifecycle(), **changes)
                self.assertEqual(self.collect(), {})

    def test_invalid_lifecycle_cannot_override_recorded_metadata(self):
        for changes in (
            {"status": "failed"}, {"event": "TranscriptChanged"}, {"observed_at": "yesterday"},
            {"observed_at": "2026-01-01T00:00:00+01:00"}, {"activity": {"tool": "private"}},
            {"activity": "x" * 301},
        ):
            with self.subTest(changes=changes):
                self.hook(lifecycle=self.lifecycle(**changes))
                row = self.collect()["local:codex"]
                self.assertEqual(row["last_response"], "Recorded response")
                self.assertNotIn("lifecycle", row)

    def test_unhooked_process_has_no_fabricated_session_or_phase(self):
        self.process("claude")
        self.payload["panes"][0]["provider"] = "claude"
        self.assertEqual(self.collect(), {})

    def test_codex_hook_cannot_supply_claude_lifecycle(self):
        record = self.hook("codex", lifecycle=self.lifecycle())
        Path(record["transcript_path"]).unlink()
        row = self.collect()["local:codex"]
        self.assertEqual(row["session_id"], "current-session")
        self.assertNotIn("lifecycle", row)

    def test_hook_identifies_exact_live_codex_thread(self):
        record = self.hook("codex")
        path = Path(record["transcript_path"])
        rows = [
            {"type": "session_meta", "payload": {"id": "current-session", "session_id": "current-session", "cwd": "/same/project"}},
            {"type": "turn_context", "payload": {"model": "recorded-codex-model"}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Exact thread request"}]}},
        ]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        row = self.collect()["local:codex"]
        self.assertEqual(row["session_id"], "current-session")
        self.assertEqual(row["model"], "recorded-codex-model")
        self.assertEqual(row["request"], "Exact thread request")
        self.assertIn("recorded", row["metadata_source"])

    def test_unique_open_root_not_newer_same_cwd_conversation(self):
        current = self.root_session()
        self.root_session("newer.jsonl", "other-session")
        self.attach(current)
        row = self.collect()["local:codex"]
        self.assertEqual(row["session_id"], "root-session")
        self.assertEqual(row["title"], "Live FD title")
        self.assertEqual(row["request"], "Recorded request")
        self.assertIn("recorded", row["metadata_source"])
        self.assertNotIn("status", row)
        self.assertNotIn("cwd", row)

    def test_open_subagent_logs_cannot_replace_root(self):
        current = self.root_session()
        child = self.root_session("current/worker.jsonl", "child-session", parentSession=str(current))
        self.attach(current)
        self.attach(child, 45)
        self.assertEqual(self.collect()["local:codex"]["session_id"], "root-session")

    def test_subagent_only_and_no_open_transcript_are_unassociated(self):
        self.assertEqual(self.collect(), {})
        child = self.root_session("worker.jsonl", "child-session", parentSession="/missing/root.jsonl")
        self.attach(child)
        self.assertEqual(self.collect(), {})

    def test_two_open_roots_are_ambiguous(self):
        self.attach(self.root_session())
        self.attach(self.root_session("second.jsonl", "second-root"), 45)
        self.assertEqual(self.collect(), {})

    def test_root_switch_during_read_drops_recorded_metadata(self):
        current = self.root_session()
        self.attach(current)
        original = metadata_omp.records

        def switching(path):
            yield from original(path)
            (self.proc / str(self.pid) / "fd" / "44").unlink()

        with patch.object(metadata_omp, "records", switching):
            self.assertEqual(self.collect(), {})

    def test_hook_identifies_exact_live_claude_conversation(self):
        self.hook()
        row = self.collect()["local:codex"]
        self.assertEqual(row["session_id"], "current-session")
        self.assertEqual(row["title"], "Correct conversation")
        self.assertEqual(row["last_response"], "Recorded response")
        self.assertNotIn("argv", row)
        self.assertNotIn("environment", row)

    def test_session_start_identity_precedes_transcript_creation(self):
        for provider in ("claude", "codex"):
            with self.subTest(provider=provider):
                record = self.hook(provider)
                Path(record["transcript_path"]).unlink()
                row = self.collect()["local:codex"]
                self.assertEqual(row["session_id"], "current-session")
                self.assertIn("SessionStart hook", row["metadata_source"])
                self.assertEqual(set(row), {"session_id", "metadata_source"})

    def test_session_start_without_transcript_path_has_only_proven_identity(self):
        self.hook("codex")
        record = json.loads(self.record_path.read_text())
        record.pop("transcript_path")
        self.record_path.write_text(json.dumps(record))
        row = self.collect()["local:codex"]
        self.assertEqual(row["session_id"], "current-session")
        self.assertEqual(set(row), {"session_id", "metadata_source"})

    def test_model_record_crossing_adjacent_read_windows_is_not_lost(self):
        path = self.root_session()
        with path.open("a") as stream:
            stream.write(json.dumps({"type": "padding", "text": "x" * 400000}) + "\n")
            stream.write(json.dumps({"type": "model_change", "model": "latest-model", "padding": "x" * 200000}) + "\n")
        self.attach(path)
        self.assertEqual(self.collect()["local:codex"]["model"], "latest-model")

    def test_default_daemon_inherits_namespace_from_exact_process(self):
        self.hook()
        self.environment.pop("TERN_DAEMON_SOCKET")
        self.assertEqual(self.collect()["local:codex"]["session_id"], "current-session")
        self.hook(socket="/unrelated/daemon.sock")
        self.assertEqual(self.collect(), {})

    def test_hook_identity_guards_fail_closed(self):
        for changes in (
            {"provider": "codex"}, {"pane": "other-pane"}, {"pid": self.pid + 1},
            {"pid": True}, {"started": "old-start"}, {"socket": "/other/daemon.sock"},
        ):
            with self.subTest(changes=changes):
                self.hook(**changes)
                self.assertEqual(self.collect(), {})

    def test_hook_transcript_identity_must_agree(self):
        self.hook(session_id="different-session")
        self.assertEqual(self.collect(), {})

    def test_target_namespace_and_pane_must_agree(self):
        for key, value in (("TERN_PANE", "other-pane"), ("TERN_DAEMON_SOCKET", "/other.sock")):
            with self.subTest(key=key):
                self.hook()
                original = self.target_environment[key]
                self.target_environment[key] = value
                self.process("claude")
                self.assertEqual(self.collect(), {})
                self.target_environment[key] = original

    def test_shared_codex_daemon_never_owns_client_metadata(self):
        self.hook("codex")
        self.process("codex", arguments=("app-server", "--managed-daemon"))
        self.assertEqual(self.collect(), {})

    def test_multiple_matching_provider_processes_are_ambiguous(self):
        self.attach(self.root_session())
        self.process("omp", pid=self.pid + 1)
        self.snapshot["foreground"]["pid"] = self.pid + 1
        self.assertEqual(self.collect(), {})

    def test_process_reuse_during_adapter_read_drops_enrichment(self):
        self.hook()
        original = metadata.metadata_claude.collect

        def reused(*args):
            result = original(*args)
            self.process("claude", started="new-start")
            return result

        with patch.object(metadata.metadata_claude, "collect", reused):
            self.assertEqual(self.collect(), {})

    def test_record_switch_during_adapter_read_drops_enrichment(self):
        record = self.hook()
        original = metadata.metadata_claude.collect

        def switched(*args):
            result = original(*args)
            self.record_path.write_text(json.dumps(dict(record, session_id="new-session")))
            return result

        with patch.object(metadata.metadata_claude, "collect", switched):
            self.assertEqual(self.collect(), {})

    def test_text_bounds_and_no_tool_payload_or_partial_usage_totals(self):
        path = self.transcript("current.jsonl", [
            {"type": "session", "id": "root", "title": "t" * 1000},
            {"type": "message", "message": {"role": "assistant", "model": "m" * 200, "content": [{"type": "thinking", "thinking": "PRIVATE"}, {"type": "text", "text": "a\n" * 1000}], "usage": {"input": 11, "output": 7, "totalTokens": 999999}}},
            {"type": "message", "message": {"role": "toolResult", "content": "PRIVATE TOOL PAYLOAD"}},
        ])
        self.attach(path)
        row = self.collect()["local:codex"]
        self.assertLessEqual(len(row["title"]), 121)
        self.assertLessEqual(len(row["model"]), 101)
        self.assertLessEqual(len(row["last_response"]), 301)
        self.assertNotIn("\n", row["last_response"])
        self.assertNotIn("PRIVATE", json.dumps(row))
        self.assertIn("11 uncached input / 7 output", row["usage"])
        self.assertNotIn("999999", row["usage"])
        with path.open("a") as stream:
            stream.write(json.dumps({"type": "message", "message": {"role": "assistant", "content": "latest without counters"}}) + "\n")
        self.assertNotIn("usage", self.collect()["local:codex"])

    def test_incomplete_record_is_not_reported(self):
        path = self.root_session()
        with path.open("a") as stream:
            stream.write('{"type":"message","message":{"role":"user","content":"not committed"}}')
        self.attach(path)
        self.assertEqual(self.collect()["local:codex"]["request"], "Recorded request")

    def test_fd_and_pane_counts_are_bounded(self):
        path = self.root_session()
        self.attach(path)
        self.payload["panes"] = [dict(self.payload["panes"][0], key=str(i)) for i in range(100)]
        self.assertEqual(len(self.collect()), 32)
        for number in range(1000, 1512):
            self.attach(path, number)
        self.assertEqual(self.collect(), {})

    def test_oversized_proc_command_does_not_identify_provider(self):
        self.attach(self.root_session())
        (self.proc / str(self.pid) / "cmdline").write_bytes(b"omp\0" + b"x" * 20000)
        self.assertEqual(self.collect(), {})

    def test_isolated_daemon_socket_routes_exact_raw_pane(self):
        self.query.stop()
        current = self.root_session()
        self.attach(current)
        binary = self.root / "bin" / "tern"
        binary.parent.mkdir()
        binary.write_text(
            f"#!{sys.executable}\nimport json, os, sys\n"
            f"expected = {self.socket!r}\n"
            "if os.environ.get('TERN_PANE_SOCKET') != expected: sys.exit(1)\n"
            f"if sys.argv[1:] != ['process', {self.pane!r}, '--json']: sys.exit(2)\n"
            f"print(json.dumps({self.snapshot!r}))\n"
        )
        binary.chmod(0o700)
        self.environment["PATH"] = str(binary.parent)
        self.assertEqual(self.collect()["local:codex"]["session_id"], "root-session")
        binary.write_text(f"#!{sys.executable}\nprint('x' * 100000)\n")
        self.assertEqual(self.collect(), {})

    def test_executable_stdin_protocol_rejects_malformed_or_oversized_input(self):
        for value in (b"not json", b"[]", b'{"panes":[]}', b" " * 65537):
            with self.subTest(size=len(value)):
                result = subprocess.run([sys.executable, str(PLUGIN / "metadata.py")], input=value, capture_output=True, check=True, timeout=5)
                self.assertEqual(json.loads(result.stdout), {"rows": {}, "protocol": metadata.PROTOCOL})
                self.assertEqual(result.stderr, b"")


if __name__ == "__main__":
    unittest.main()
