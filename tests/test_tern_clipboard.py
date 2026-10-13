from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TernClipboardInstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.config = self.home / "config"
        self.agent = self.home / "agent"
        self.state = self.home / "state"
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.state),
            "PI_CODING_AGENT_DIR": str(self.agent),
        }
        self.environment.pop("HYPRLAND_INSTANCE_SIGNATURE", None)

    def install(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "install-tern-clipboard.py"), *args],
            env=self.environment, capture_output=True, text=True,
        )

    def test_host_only_preserves_other_extensions_and_backs_up_conflict_once(self) -> None:
        extensions = self.agent / "extensions"
        extensions.mkdir(parents=True)
        sibling = extensions / "personal.ts"
        sibling.write_text("personal extension\n")
        target = extensions / "tern-enhanced-paste.ts"
        target.write_text("previous local extension\n")
        self.assertEqual(self.install("--host").returncode, 0)
        first_backups = list(self.state.rglob("tern-enhanced-paste.ts"))
        self.assertEqual([p.read_text() for p in first_backups], ["previous local extension\n"])
        self.assertEqual(self.install("--host").returncode, 0)
        self.assertEqual(list(self.state.rglob("tern-enhanced-paste.ts")), first_backups)
        self.assertEqual(sibling.read_text(), "personal extension\n")
        self.assertFalse(self.config.exists())

    def test_client_requires_existing_lua_config_before_changing_anything(self) -> None:
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.agent.exists())
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
