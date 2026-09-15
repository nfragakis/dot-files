from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


status = load_module(
    "agent_status",
    ROOT / "omarchy/plugins/nfragakis.workspaces/agent-status.py",
)
installer = load_module("install_agent_attention", ROOT / "install-agent-attention.py")


class AgentStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary.name) / "agent-attention.json"
        self.environment = mock.patch.dict(
            os.environ,
            {
                "AGENT_ATTENTION_STATE": str(self.state_path),
                "AGENT_ATTENTION_WORKSPACE": "3",
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def event(self, provider: str, name: str, **extra) -> None:
        status.handle_hook(provider, {"session_id": "session-1", "hook_event_name": name, **extra})

    def session(self):
        return status.load_state(self.state_path)["sessions"]["session-1"]

    def test_codex_turn_lifecycle_keeps_workspace_after_acknowledgement(self) -> None:
        self.event("codex", "SessionStart")
        self.event("codex", "Stop")
        self.assertEqual(self.session()["state"], "complete")
        status.clear_workspace(3)
        self.assertEqual(self.session()["state"], "")

        with mock.patch.dict(os.environ, {"AGENT_ATTENTION_WORKSPACE": "5"}):
            self.event("codex", "Stop")
        self.assertEqual(self.session()["workspace"], 3)
        self.assertEqual(self.session()["state"], "complete")

    def test_prompt_moves_session_and_permission_requests_attention(self) -> None:
        self.event("codex", "SessionStart")
        with mock.patch.dict(os.environ, {"AGENT_ATTENTION_WORKSPACE": "4"}):
            self.event("codex", "UserPromptSubmit")
        self.event("codex", "PermissionRequest")
        self.assertEqual(self.session()["workspace"], 4)
        self.assertEqual(self.session()["state"], "attention")

    def test_claude_notification_types_are_distinct(self) -> None:
        self.event("claude", "SessionStart")
        self.event("claude", "Notification", notification_type="idle_prompt")
        self.assertEqual(self.session()["state"], "complete")
        self.event("claude", "Notification", notification_type="permission_prompt")
        self.assertEqual(self.session()["state"], "attention")


class InstallerTest(unittest.TestCase):
    def test_add_hooks_preserves_existing_hooks_and_is_idempotent(self) -> None:
        existing = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "orca"}]}]}}
        command = "python3 '/plugin/nfragakis.workspaces/agent-status.py' hook codex"
        first = installer.add_hooks(existing, "codex", command)
        second = installer.add_hooks(first, "codex", command)
        self.assertEqual(len(second["hooks"]["Stop"]), 2)
        self.assertEqual(second["hooks"]["Stop"][0]["hooks"][0]["command"], "orca")
        for event in installer.EVENTS["codex"]:
            own_groups = [group for group in second["hooks"][event] if installer.is_ours(group)]
            self.assertEqual(len(own_groups), 1)


if __name__ == "__main__":
    unittest.main()
