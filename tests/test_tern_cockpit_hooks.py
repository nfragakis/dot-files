from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import stat
import tempfile
import threading
import tomllib
import unittest
from unittest import mock


PLUGIN = Path(__file__).resolve().parents[1] / "tern/plugins/agent-cockpit"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PLUGIN / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECORD = load("cockpit_hook_record", "hook_record.py")
SETTINGS = load("cockpit_hook_settings", "hook_settings.py")
SESSION = "11111111-1111-4111-8111-111111111111"


class HookRecorderTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.proc = self.root / "proc"
        self.state = self.root / "state"
        self.environment = {"HOME": str(self.root / "home"), "XDG_STATE_HOME": str(self.state),
                            "TERN_PANE": "00042", "TERN_PANE_SOCKET": str(self.root / "pane.sock"),
                            "ANTHROPIC_API_KEY": "must never be recorded",
                            "OPENAI_API_KEY": "must never be recorded"}
        self.payload = {"hook_event_name": "SessionStart", "session_id": SESSION,
                        "transcript_path": str(self.root / "transcript.jsonl"), "source": "startup"}
        self.process(100, 1, "/opt/claude", ["claude"], "123456", "claude (native) worker")
        self.process(200, 100, "/usr/bin/bash", ["bash", "-c", "python3 recorder.py claude"])

    def process(self, pid: int, parent: int, executable: str, argv: list[str],
                started: str = "123", comm: str = "process") -> None:
        directory = self.proc / str(pid)
        directory.mkdir(parents=True, exist_ok=True)
        fields = ["S", str(parent)] + ["0"] * 17 + [started] + ["0"] * 3
        (directory / "stat").write_text(f"{pid} ({comm}) {' '.join(fields)}\n")
        (directory / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in argv) + b"\0")
        executable_link = directory / "exe"
        if executable_link.is_symlink():
            executable_link.unlink()
        executable_link.symlink_to(executable)

    def record(self, provider: str = "claude", payload: dict | None = None,
               environment: dict | None = None) -> Path | None:
        return RECORD.record(provider, self.payload if payload is None else payload,
                             self.environment if environment is None else environment,
                             parent=200, proc=self.proc)

    def test_root_provider_not_hook_shell_and_exact_raw_pane_identity(self) -> None:
        result = self.record()
        self.assertEqual(result.parent, self.state / "tern/agent-cockpit/sessions")
        self.assertEqual(result.name, RECORD.record_filename("claude", "00042"))
        value = json.loads(result.read_text())
        lifecycle = value.pop("lifecycle")
        self.assertEqual(lifecycle["status"], "idle")
        self.assertEqual(lifecycle["activity"], "Ready")
        self.assertEqual(lifecycle["event"], "SessionStart")
        self.assertEqual(datetime.fromisoformat(lifecycle["observed_at"].replace("Z", "+00:00")).tzinfo,
                         timezone.utc)
        self.assertEqual(value, {"provider": "claude", "pane": "00042", "pid": 100,
                                "started": "123456", "session_id": SESSION,
                                "transcript_path": self.payload["transcript_path"],
                                "config_dir": str(self.root / "home/.claude"),
                                "socket": self.environment["TERN_PANE_SOCKET"]})
        self.assertNotIn("API_KEY", result.read_text())
        self.assertNotEqual(RECORD.record_filename("claude", "00042"),
                            RECORD.record_filename("claude", "42"))
        self.assertNotEqual(RECORD.record_filename("claude", "00042"),
                            RECORD.record_filename("codex", "00042"))

    def test_private_atomic_replacement_and_no_leftover_temporary_files(self) -> None:
        target = self.record()
        target.write_text("previous complete record")
        replacing = os.replace
        observations = []

        def replace(source, destination, **kwargs):
            directory = kwargs["src_dir_fd"]
            self.assertEqual(kwargs["dst_dir_fd"], directory)
            self.assertEqual(target.read_text(), "previous complete record")
            info = os.stat(source, dir_fd=directory, follow_symlinks=False)
            self.assertEqual(stat.S_IMODE(info.st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.fstat(directory).st_mode), 0o700)
            observations.append(json.loads((target.parent / source).read_text()))
            return replacing(source, destination, **kwargs)

        old_umask = os.umask(0)
        try:
            with mock.patch.object(RECORD.os, "replace", side_effect=replace):
                self.assertEqual(self.record(), target)
        finally:
            os.umask(old_umask)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["pid"], 100)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(list(target.parent.iterdir()), [target])

    def test_changed_process_start_does_not_publish_and_cleans_temporary(self) -> None:
        process_stat = RECORD.process_stat
        calls = 0

        def reused(pid, proc):
            nonlocal calls
            result = process_stat(pid, proc)
            if pid == 100:
                calls += 1
                if calls == 2:
                    return result[0], "999999"
            return result

        with mock.patch.object(RECORD, "process_stat", side_effect=reused):
            self.assertIsNone(self.record())
        self.assertEqual(calls, 2)
        self.assertEqual(list((self.state / "tern/agent-cockpit/sessions").iterdir()), [])

    def test_record_symlink_is_replaced_not_followed(self) -> None:
        target = self.record()
        outside = self.root / "do-not-change"
        outside.write_text("private unrelated contents")
        target.unlink()
        target.symlink_to(outside)
        self.record()
        self.assertFalse(target.is_symlink())
        self.assertEqual(outside.read_text(), "private unrelated contents")

    def test_symlinked_record_directory_is_refused(self) -> None:
        (self.state / "tern/agent-cockpit").mkdir(parents=True)
        outside = self.root / "outside"
        outside.mkdir()
        (self.state / "tern/agent-cockpit/sessions").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            self.record()
        self.assertEqual(list(outside.iterdir()), [])

    def test_selected_environment_only_and_config_and_socket_overrides(self) -> None:
        allowed = set(RECORD.ENV_KEYS)

        class SelectedOnly(dict):
            def get(self, key, default=None):
                if key not in allowed:
                    raise AssertionError(f"unsafe environment lookup: {key}")
                return super().get(key, default)

            def __iter__(self):
                raise AssertionError("must not enumerate inherited environment")

            def items(self):
                raise AssertionError("must not enumerate inherited environment")

        environment = SelectedOnly(self.environment)
        environment["CLAUDE_CONFIG_DIR"] = "~/custom-claude"
        environment.pop("TERN_PANE_SOCKET")
        environment["TERN_DAEMON_SOCKET"] = str(self.root / "daemon.sock")
        value = json.loads(self.record(environment=environment).read_text())
        self.assertEqual(value["config_dir"], str(self.root / "home/custom-claude"))
        self.assertEqual(value["socket"], environment["TERN_DAEMON_SOCKET"])

    def test_default_state_and_optional_transcript_do_not_require_auth_or_logs(self) -> None:
        environment = {key: value for key, value in self.environment.items() if key != "XDG_STATE_HOME"}
        payload = {"hook_event_name": "SessionStart", "session_id": SESSION}
        target = self.record(payload=payload, environment=environment)
        self.assertEqual(target.parent, self.root / "home/.local/state/tern/agent-cockpit/sessions")
        self.assertNotIn("transcript_path", json.loads(target.read_text()))
        self.assertFalse((self.root / "home/.claude").exists())
        self.assertFalse(Path(self.payload["transcript_path"]).exists())

    def test_absent_or_invalid_ownership_and_subagents_leave_no_record(self) -> None:
        for key in ("TERN_PANE", "TERN_PANE_SOCKET"):
            environment = dict(self.environment)
            environment.pop(key)
            with self.subTest(missing=key):
                self.assertIsNone(self.record(environment=environment))
        for change in ({"session_id": ""}, {"session_id": 9}, {"agent_id": "subagent-123"},
                       {"hook_event_name": "UnsupportedEvent"}, {"session_id": "bad\nidentity"},
                       {"transcript_path": "relative.jsonl"}):
            with self.subTest(payload=change):
                self.assertIsNone(self.record(payload={**self.payload, **change}))
        for key, value in (("TERN_PANE", "x" * 513), ("CODEX_HOME", "relative"),
                           ("XDG_STATE_HOME", "relative")):
            environment = {**self.environment, key: value}
            provider = "codex" if key == "CODEX_HOME" else "claude"
            with self.subTest(environment=key):
                self.assertIsNone(self.record(provider, environment=environment))
        self.assertFalse(self.state.exists())

    def test_record_size_is_bounded_after_json_escaping(self) -> None:
        payload = {**self.payload, "transcript_path": "/" + "\u2603" * 4000}
        self.assertIsNone(self.record(payload=payload))
        self.assertFalse(self.state.exists())

    def test_native_versioned_claude_and_node_package_ancestors(self) -> None:
        self.process(100, 1, "/home/user/.local/share/claude/versions/2.1.99", ["claude"], "234")
        self.assertEqual(json.loads(self.record().read_text())["started"], "234")
        self.process(100, 1, "/usr/bin/node", ["node", "/node_modules/@anthropic-ai/claude-code/cli.js"], "345")
        self.assertEqual(json.loads(self.record().read_text())["pid"], 100)

    def test_argv_mentions_or_spoofed_shell_name_are_not_provider_identity(self) -> None:
        self.process(100, 1, "/usr/bin/bash", ["claude", "--session", SESSION])
        self.assertIsNone(self.record())
        self.assertFalse(self.state.exists())

    def test_cyclic_ancestry_is_bounded(self) -> None:
        self.process(100, 200, "/usr/bin/bash", ["bash"])
        self.assertIsNone(self.record())
        self.assertFalse(self.state.exists())

    def test_direct_codex_session_has_exact_provider_owner(self) -> None:
        self.process(100, 1, "/vendor/codex/codex", ["codex", "resume", SESSION], "456")
        environment = {**self.environment, "CODEX_HOME": str(self.root / "custom-codex"),
                       "CODEX_THREAD_ID": SESSION}
        value = json.loads(self.record("codex", environment=environment).read_text())
        self.assertEqual(value["provider"], "codex")
        self.assertEqual(value["pid"], 100)
        self.assertEqual(value["started"], "456")
        self.assertEqual(value["config_dir"], str(self.root / "custom-codex"))

    def test_unrelated_systemd_ancestor_does_not_require_executable_access(self) -> None:
        self.process(50, 1, "/usr/lib/systemd/systemd", ["systemd", "--user"])
        self.process(100, 50, "/vendor/codex/codex", ["codex", "--no-daemon"], "456")
        original = os.readlink

        def protected(path, *args, **kwargs):
            if Path(path) == self.proc / "50/exe":
                raise PermissionError("user systemd executable is protected")
            return original(path, *args, **kwargs)

        with mock.patch.object(RECORD.os, "readlink", side_effect=protected):
            value = json.loads(self.record("codex").read_text())
        self.assertEqual(value["pid"], 100)
        self.assertEqual(value["started"], "456")

    def test_shared_app_server_never_claims_inherited_first_client_pane(self) -> None:
        self.process(100, 1, "/vendor/codex/codex",
                     ["codex", "app-server", "--listen", "unix:///shared.sock"], "456")
        for inherited in (SESSION, "", "different-thread"):
            environment = {**self.environment, "CODEX_THREAD_ID": inherited}
            with self.subTest(inherited_thread=inherited):
                self.assertIsNone(self.record("codex", environment=environment))
        self.assertFalse(self.state.exists())

    def test_codex_mismatched_thread_is_rejected_without_ancestry_guess(self) -> None:
        self.process(100, 1, "/vendor/codex/codex", ["codex"], "456")
        self.assertIsNone(self.record("codex", environment={**self.environment,
                                                            "CODEX_THREAD_ID": "another-thread"}))
        self.assertFalse(self.state.exists())

    def test_app_server_above_another_codex_process_is_still_unowned(self) -> None:
        self.process(50, 1, "/vendor/codex/codex", ["codex", "app-server"])
        self.process(100, 50, "/vendor/codex/codex", ["codex", "exec"], "456")
        self.assertIsNone(self.record("codex"))
        self.assertFalse(self.state.exists())

    def test_claude_root_lifecycle_tracks_real_events_without_tool_contents(self) -> None:
        target = self.record()
        cases = (
            ("UserPromptSubmit", {"prompt": "Please\n  fix\tthis\x1b[31m \u202ehidden"}, "working", "Prompt: "),
            ("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "SECRET input"}}, "working", "Using Bash"),
            ("PermissionRequest", {"tool_name": "Bash"}, "waiting_input", "Permission required: Bash"),
            ("Notification", {"notification_type": "permission_prompt", "message": "SECRET notification"},
             "waiting_input", "Permission required"),
            ("PostToolUse", {"tool_name": "Bash", "tool_response": "SECRET output"}, "working", "Finished Bash"),
            ("PostToolUseFailure", {"tool_name": "Read", "error": "SECRET tool error"},
             "working", "Read returned an error"),
            ("Stop", {"last_assistant_message": "SECRET answer"}, "idle", "Response complete"),
            ("Notification", {"notification_type": "idle_prompt"}, "idle", "Waiting for prompt"),
            ("SessionEnd", {"reason": "prompt_input_exit"}, "exited", "Session ended"),
        )
        for event, fields, status, activity in cases:
            with self.subTest(event=event, fields=fields):
                self.assertEqual(self.record(payload={**self.payload, **fields, "hook_event_name": event}), target)
                value = json.loads(target.read_text())
                lifecycle = value["lifecycle"]
                self.assertEqual(lifecycle["event"], event)
                self.assertEqual(lifecycle["status"], status)
                self.assertTrue(lifecycle["activity"].startswith(activity))
                self.assertLessEqual(len(lifecycle["activity"]), 160)
                self.assertFalse(any(ord(char) < 32 or ord(char) == 127 for char in lifecycle["activity"]))
                self.assertNotIn("\u202e", lifecycle["activity"])
                self.assertNotIn("SECRET", target.read_text())
                self.assertEqual(value["session_id"], SESSION)

    def test_multiline_prompt_activity_is_bounded_without_discarding_event(self) -> None:
        target = self.record()
        payload = {**self.payload, "hook_event_name": "UserPromptSubmit", "prompt": "A\n" * 10000}
        self.assertEqual(self.record(payload=payload), target)
        activity = json.loads(target.read_text())["lifecycle"]["activity"]
        self.assertTrue(activity.startswith("Prompt: A A A"))
        self.assertLessEqual(len(activity), 160)
        self.assertNotIn("\n", activity)

    def test_nonstart_events_cannot_create_or_reassign_an_owner(self) -> None:
        event = {**self.payload, "hook_event_name": "UserPromptSubmit", "prompt": "work"}
        self.assertIsNone(self.record(payload=event))
        target = self.record()
        before = target.read_bytes()
        for changed in ({"session_id": "foreign-session"}, {"agent_id": "subagent"}):
            self.assertIsNone(self.record(payload={**event, **changed}))
            self.assertEqual(target.read_bytes(), before)
        for changed in ({"TERN_PANE_SOCKET": "/foreign.sock"}, {"TERN_PANE": "42"}):
            self.assertIsNone(self.record(payload=event, environment={**self.environment, **changed}))
            self.assertEqual(target.read_bytes(), before)
        self.process(100, 1, "/opt/claude", ["claude"], "999999")
        self.assertIsNone(self.record(payload=event))
        self.assertEqual(target.read_bytes(), before)

    def test_new_owner_and_session_reject_old_owner_events_and_starts(self) -> None:
        target = self.record()
        self.process(300, 1, "/opt/claude", ["claude"], "999999")
        self.process(200, 300, "/usr/bin/bash", ["bash"])
        newer = {**self.payload, "session_id": "new-session"}
        self.assertEqual(self.record(payload=newer), target)
        before = target.read_bytes()
        self.process(200, 100, "/usr/bin/bash", ["bash"])
        for event in ("UserPromptSubmit", "Stop", "SessionEnd", "SessionStart"):
            self.assertIsNone(self.record(payload={**self.payload, "hook_event_name": event}))
            self.assertEqual(target.read_bytes(), before)
        self.process(200, 300, "/usr/bin/bash", ["bash"])
        self.assertIsNone(self.record(payload={**self.payload, "hook_event_name": "SessionEnd"}))
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.record(payload={**newer, "hook_event_name": "UserPromptSubmit"}), target)

    def test_exited_session_is_terminal_until_a_real_sessionstart(self) -> None:
        target = self.record()
        self.record(payload={**self.payload, "hook_event_name": "SessionEnd"})
        before = target.read_bytes()
        self.assertIsNone(self.record(payload={**self.payload, "hook_event_name": "PostToolUse", "tool_name": "Bash"}))
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.record(payload={**self.payload, "source": "resume"}), target)
        self.assertEqual(json.loads(target.read_text())["lifecycle"]["status"], "idle")

    def test_clear_claims_new_session_but_old_session_events_cannot_reclaim_it(self) -> None:
        target = self.record()
        cleared = {**self.payload, "session_id": "cleared-session", "source": "clear"}
        self.assertEqual(self.record(payload=cleared), target)
        before = target.read_bytes()
        for event in ("UserPromptSubmit", "PermissionRequest", "Stop", "SessionEnd"):
            self.assertIsNone(self.record(payload={**self.payload, "hook_event_name": event}))
            self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.record(payload={**cleared, "hook_event_name": "UserPromptSubmit"}), target)

    def test_existing_trusted_sessionstart_record_can_receive_lifecycle_events(self) -> None:
        target = self.record()
        previous = json.loads(target.read_text())
        previous.pop("lifecycle")
        target.write_text(json.dumps(previous))
        self.assertEqual(self.record(payload={**self.payload, "hook_event_name": "PreToolUse",
                                             "tool_name": "Read"}), target)
        self.assertEqual(json.loads(target.read_text())["lifecycle"]["activity"], "Using Read")

    def test_delayed_sessionstart_cannot_replace_a_newer_session_observation(self) -> None:
        target = self.record()
        with mock.patch.object(RECORD, "datetime") as clock:
            clock.now.return_value = datetime(2030, 1, 1, 0, 0, 2, tzinfo=timezone.utc)
            self.assertEqual(self.record(payload={**self.payload, "source": "clear",
                                                  "session_id": "new-session"}), target)
            before = target.read_bytes()
            clock.now.return_value = datetime(2030, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
            self.assertIsNone(self.record())
        self.assertEqual(target.read_bytes(), before)

    def test_earlier_concurrent_observation_cannot_overwrite_a_later_event(self) -> None:
        target = self.record()
        paused, release = threading.Event(), threading.Event()
        original_owner = RECORD.provider_owner
        results, errors = [], []

        def owner(*args, **kwargs):
            if threading.current_thread().name == "delayed-hook":
                paused.set()
                if not release.wait(5):
                    raise AssertionError("concurrent hook was not released")
            return original_owner(*args, **kwargs)

        def delayed():
            try:
                results.append(self.record(payload={**self.payload, "hook_event_name": "PreToolUse",
                                                    "tool_name": "Bash"}))
            except BaseException as error:
                errors.append(error)

        with mock.patch.object(RECORD, "provider_owner", side_effect=owner):
            worker = threading.Thread(target=delayed, name="delayed-hook")
            worker.start()
            try:
                self.assertTrue(paused.wait(5))
                self.record(payload={**self.payload, "hook_event_name": "Stop"})
                before = target.read_bytes()
            finally:
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(results, [None])
        self.assertEqual(target.read_bytes(), before)

    def test_unrelated_notifications_and_codex_events_leave_records_unchanged(self) -> None:
        target = self.record()
        before = target.read_bytes()
        for event in ({"hook_event_name": "Notification", "notification_type": "auth_success"},
                      {"hook_event_name": "SubagentStop"}, {"hook_event_name": "Stop", "agent_id": "child"}):
            self.assertIsNone(self.record(payload={**self.payload, **event}))
            self.assertEqual(target.read_bytes(), before)
        self.process(100, 1, "/vendor/codex/codex", ["codex"], "999999")
        codex = self.record("codex")
        self.assertNotIn("lifecycle", json.loads(codex.read_text()))
        self.assertIsNone(self.record("codex", payload={**self.payload, "hook_event_name": "Stop"}))

    def test_main_dispatches_ordinary_payload_with_only_selected_environment(self) -> None:
        with mock.patch.dict(RECORD.os.environ, self.environment, clear=True):
            with mock.patch.object(RECORD, "record") as record:
                self.assertEqual(RECORD.main(["claude"], io.BytesIO(json.dumps(self.payload).encode())), 0)
        provider, payload, selected = record.call_args.args
        self.assertEqual(provider, "claude")
        self.assertEqual(payload, self.payload)
        self.assertEqual(set(selected), set(RECORD.ENV_KEYS))
        self.assertNotIn("ANTHROPIC_API_KEY", selected)
        self.assertNotIn("OPENAI_API_KEY", selected)

    def test_main_bounds_input_and_is_silent_on_all_failures(self) -> None:
        for data in (b"not json", b"[]", b"null", b"x" * (RECORD.INPUT_LIMIT + 1)):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(data_size=len(data)), redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(RECORD.main(["claude"], io.BytesIO(data), {}), 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")
        for error in (OSError("gone"), TimeoutError("deadline"), ValueError("invalid")):
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.object(RECORD, "record", side_effect=error), redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(RECORD.main(["claude"], io.BytesIO(json.dumps(self.payload).encode()), {}), 0)
            self.assertEqual(stdout.getvalue() + stderr.getvalue(), "")
        with mock.patch.object(RECORD, "record") as record:
            self.assertEqual(RECORD.main(["not-a-provider"], io.BytesIO(b"{}"), {}), 0)
            self.assertEqual(RECORD.main(["claude", "unexpected"], io.BytesIO(b"{}"), {}), 0)
            record.assert_not_called()


class HookSettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.recorder = self.root / "path with spaces and 'quote/hook_record.py"
        self.claude = self.home / ".claude/settings.json"
        self.codex = self.home / ".codex/hooks.json"

    def fixture(self, path: Path, value: object, *, raw: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if raw else json.dumps(value))

    def test_plans_only_and_exact_provider_paths_commands_and_matchers(self) -> None:
        plans = SETTINGS.plans(self.home, self.recorder, {})
        self.assertEqual([path for path, _ in plans], [self.claude, self.codex])
        self.assertFalse(self.home.exists())
        for (path, value), provider in zip(plans, ("claude", "codex")):
            group = value["hooks"]["SessionStart"][0]
            hook = group["hooks"][0]
            self.assertEqual(shlex.split(hook["command"]), ["python3", str(self.recorder), provider])
            self.assertEqual(hook["type"], "command")
            self.assertEqual(hook["timeout"], 5)
            if provider == "claude":
                self.assertEqual(group["matcher"], "^(startup|resume|clear|compact|fork)$")
                self.assertEqual(set(value["hooks"]), {"SessionStart", "UserPromptSubmit", "PreToolUse",
                                                       "PostToolUse", "PostToolUseFailure", "PermissionRequest",
                                                       "Notification", "Stop", "SessionEnd"})
                for event, groups in value["hooks"].items():
                    self.assertEqual(groups[0]["hooks"], [hook])
                    if event == "Notification":
                        self.assertEqual(groups[0]["matcher"], "^(permission_prompt|idle_prompt)$")
                    elif event != "SessionStart":
                        self.assertNotIn("matcher", groups[0])
            else:
                self.assertNotIn("matcher", group)
                self.assertEqual(path.name, "hooks.json")
                self.assertEqual(set(value["hooks"]), {"SessionStart"})

    def test_preserves_unknown_fields_and_existing_hooks_and_is_idempotent(self) -> None:
        original = {"model": "personal", "future": {"enabled": True, "values": [None, 12.5]},
                    "hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "keep stop"}]}],
                              "SessionStart": [{"matcher": "startup", "future": "keep",
                                                "hooks": [{"type": "command", "command": "keep session", "other": 2},
                                                          {"type": "future-hook", "unknown": [1, 2]}]}]}}
        for path in (self.claude, self.codex):
            self.fixture(path, original)
        before = {path: path.read_bytes() for path in (self.claude, self.codex)}
        for path, value in SETTINGS.plans(self.home, self.recorder, {}):
            self.assertEqual(value["model"], original["model"])
            self.assertEqual(value["future"], original["future"])
            stop = value["hooks"]["Stop"][:-1] if path == self.claude else value["hooks"]["Stop"]
            self.assertEqual(stop, original["hooks"]["Stop"])
            self.assertEqual(value["hooks"]["SessionStart"][:-1], original["hooks"]["SessionStart"])
            self.assertEqual(path.read_bytes(), before[path])
            self.fixture(path, value)
        self.assertEqual(SETTINGS.plans(self.home, self.recorder, {}), [])

    def test_only_exact_own_command_counts_and_extended_own_entry_is_preserved(self) -> None:
        command = f"python3 {shlex.quote(str(self.recorder))} claude"
        existing = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": command + " --other"}]}]}}
        self.fixture(self.claude, existing)
        planned = dict(SETTINGS.plans(self.home, self.recorder, {}))[self.claude]
        self.assertEqual(len(planned["hooks"]["SessionStart"]), 2)
        planned["hooks"]["SessionStart"][-1]["hooks"][0]["future"] = "retain"
        self.fixture(self.claude, planned)
        self.assertNotIn(self.claude, dict(SETTINGS.plans(self.home, self.recorder, {})))
        self.assertEqual(json.loads(self.claude.read_text()), planned)

    def test_existing_sessionstart_installation_gets_additive_lifecycle_upgrade(self) -> None:
        command = f"python3 {shlex.quote(str(self.recorder))} claude"
        original = {"hooks": {"SessionStart": [{"matcher": SETTINGS.CLAUDE_MATCHER,
                                                "hooks": [{"type": "command", "command": command,
                                                           "timeout": 5, "future": "retain"}]}],
                              "Notification": [{"matcher": "auth_success",
                                                "hooks": [{"type": "command", "command": "keep auth"}]}]}}
        self.fixture(self.claude, original)
        planned = dict(SETTINGS.plans(self.home, self.recorder, {}))[self.claude]
        self.assertEqual(planned["hooks"]["SessionStart"], original["hooks"]["SessionStart"])
        self.assertEqual(planned["hooks"]["Notification"][:-1], original["hooks"]["Notification"])
        self.assertIn("PermissionRequest", planned["hooks"])
        self.assertIn("PostToolUseFailure", planned["hooks"])
        self.fixture(self.claude, planned)
        self.assertNotIn(self.claude, dict(SETTINGS.plans(self.home, self.recorder, {})))

    def test_restricted_own_hook_does_not_prevent_all_tool_lifecycle_installation(self) -> None:
        command = f"python3 {shlex.quote(str(self.recorder))} claude"
        original = {"hooks": {"PreToolUse": [{"matcher": "Read",
                                              "hooks": [{"type": "command", "command": command,
                                                         "future": "preserve"}]}]}}
        self.fixture(self.claude, original)
        planned = dict(SETTINGS.plans(self.home, self.recorder, {}))[self.claude]
        self.assertEqual(planned["hooks"]["PreToolUse"][:-1], original["hooks"]["PreToolUse"])
        self.assertNotIn("matcher", planned["hooks"]["PreToolUse"][-1])
        self.fixture(self.claude, planned)
        self.assertNotIn(self.claude, dict(SETTINGS.plans(self.home, self.recorder, {})))

    def test_custom_configuration_directories_and_tilde_use_supplied_home(self) -> None:
        environment = {"CLAUDE_CONFIG_DIR": "~/custom-claude", "CODEX_HOME": str(self.root / "custom-codex")}
        planned = SETTINGS.plans(self.home, self.recorder, environment)
        self.assertEqual([path for path, _ in planned],
                         [self.home / "custom-claude/settings.json", self.root / "custom-codex/hooks.json"])
        self.assertFalse(self.home.exists())

    def test_malformed_settings_fail_closed_without_mutation(self) -> None:
        malformed = ("[]", "null", "{", '{"hooks":null}', '{"hooks":{"SessionStart":{}}}',
                     '{"hooks":{"SessionStart":[null]}}', '{"hooks":{"SessionStart":[{"hooks":null}]}}',
                     '{"hooks":{"SessionStart":[{"matcher":9,"hooks":[]}]}}',
                     '{"hooks":{"SessionStart":[{"hooks":[9]}]}}',
                     '{"hooks":{"SessionStart":[{"hooks":[{"type":"command","command":9}]}]}}',
                     '{"same":1,"same":2}', '{"number":NaN}')
        malformed += ('{"hooks":{"PostToolUse":{}}}', '{"hooks":{"Notification":[{"matcher":5,"hooks":[]}]}}')
        for content in malformed:
            with self.subTest(content=content):
                self.fixture(self.claude, content, raw=True)
                with self.assertRaises(ValueError):
                    SETTINGS.plans(self.home, self.recorder, {})
                self.assertEqual(self.claude.read_text(), content)
                self.assertFalse(self.codex.exists())

    def test_malformed_codex_prevents_returning_partial_claude_plan(self) -> None:
        self.fixture(self.codex, '{"hooks":42}', raw=True)
        with self.assertRaises(ValueError):
            SETTINGS.plans(self.home, self.recorder, {})
        self.assertFalse(self.claude.exists())
        self.assertEqual(self.codex.read_text(), '{"hooks":42}')

    def test_regular_settings_symlink_supported_but_dangling_and_nonfiles_refused(self) -> None:
        destination = self.root / "linked-settings.json"
        self.fixture(destination, {"keep": "linked"})
        self.claude.parent.mkdir(parents=True)
        self.claude.symlink_to(destination)
        self.assertEqual(dict(SETTINGS.plans(self.home, self.recorder, {}))[self.claude]["keep"], "linked")
        self.assertTrue(self.claude.is_symlink())
        destination.unlink()
        with self.assertRaises(ValueError):
            SETTINGS.plans(self.home, self.recorder, {})
        self.claude.unlink()
        self.claude.mkdir()
        with self.assertRaises(ValueError):
            SETTINGS.plans(self.home, self.recorder, {})

    def test_oversized_config_and_relative_overrides_are_refused(self) -> None:
        self.fixture(self.claude, " " * (SETTINGS.CONFIG_LIMIT + 1), raw=True)
        with self.assertRaises(ValueError):
            SETTINGS.plans(self.home, self.recorder, {})
        self.claude.unlink()
        for environment in ({"CODEX_HOME": "relative"}, {"CLAUDE_CONFIG_DIR": "relative"}):
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                SETTINGS.plans(self.home, self.recorder, environment)
        with self.assertRaises(ValueError):
            SETTINGS.plans(self.home, Path("relative/recorder.py"), {})

    def test_codex_feature_merge_preserves_other_settings_and_comments(self) -> None:
        config = self.home / ".codex/config.toml"
        for text in ('[features]\nhooks = false # keep comment\njs_repl = false\n',
                     '[features]\ncodex_hooks = true\n',
                     '[profiles.work.features]\nhooks = true\n'):
            self.fixture(config, text, raw=True)
            path, updated = SETTINGS.codex_plan(self.home, {})
            expected = tomllib.loads(text)
            expected.setdefault("features", {})["hooks"] = True
            self.assertEqual(path, config)
            self.assertEqual(tomllib.loads(updated), expected)
            if "# keep comment" in text:
                self.assertIn("# keep comment", updated)
            self.assertEqual(config.read_text(), text)
            config.write_text(updated)
            self.assertIsNone(SETTINGS.codex_plan(self.home, {}))

    def test_custom_codex_feature_path_and_malformed_toml(self) -> None:
        environment = {"CODEX_HOME": str(self.root / "codex-custom")}
        config = self.root / "codex-custom/config.toml"
        path, updated = SETTINGS.codex_plan(self.home, environment)
        self.assertEqual(path, config)
        self.assertEqual(tomllib.loads(updated), {"features": {"hooks": True}})
        self.assertFalse(config.exists())
        for text in ('[features\n', 'features = "not a table"\n', 'features = {hooks = false}\n'):
            self.fixture(config, text, raw=True)
            with self.subTest(text=text), self.assertRaises(ValueError):
                SETTINGS.codex_plan(self.home, environment)
            self.assertEqual(config.read_text(), text)


if __name__ == "__main__":
    unittest.main()
