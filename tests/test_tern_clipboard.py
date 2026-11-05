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


    def test_client_stages_resolvable_entry_and_preserves_upstream_and_bindings(self) -> None:
        bindings = self.config / "hypr/bindings.lua"
        bindings.parent.mkdir(parents=True)
        bindings.write_text('o.bind("SUPER + X", "Personal", "personal")\n')
        forge = self.home / "src/forge/omarchy"
        (forge / "hypr").mkdir(parents=True)
        (forge / "lib").mkdir()
        (forge / "bin").mkdir()
        (forge / "hypr/tern-nav.lua").write_text("-- upstream compositor bindings\n")
        (forge / "plugin.toml").write_text('id = "omarchy"\nwindow = "window.luau"\n')
        (forge / "LICENSE").write_text("upstream license\n")
        upstream_entry = forge / "window.luau"
        upstream_entry.write_text("-- upstream entry must stay untouched\n")
        binaries = self.home / "bin"
        binaries.mkdir()
        tern = binaries / "tern"
        tern.write_text('#!/bin/sh\nif [ "$1" = plugin ] && [ "$2" = dir ]; then printf "%s/tern/plugins\\n" "$XDG_CONFIG_HOME"; fi\n')
        tern.chmod(0o755)
        self.environment["PATH"] = str(binaries) + os.pathsep + self.environment.get("PATH", "")

        result = self.install("--client")
        self.assertEqual(result.returncode, 0, result.stderr)
        packages = [path for path in (self.state / "dot-files/tern-omarchy").iterdir() if (path / "plugin.toml").is_file()]
        self.assertEqual(len(packages), 1)
        package = packages[0]
        entry_context = (package / "window.luau").resolve().parent
        self.assertTrue((entry_context / "lib").is_dir(), "canonical entry context cannot resolve its relative imports")
        self.assertEqual(upstream_entry.read_text(), "-- upstream entry must stay untouched\n")
        self.assertIn('"Personal"', bindings.read_text())
        self.assertEqual(bindings.read_text().count('require("hypr.tern-omarchy")'), 1)
        self.assertEqual(self.install("--client").returncode, 0)
        self.assertEqual(bindings.read_text().count('require("hypr.tern-omarchy")'), 1)

if __name__ == "__main__":
    unittest.main()
