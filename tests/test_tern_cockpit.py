from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ACTION = "plugin.agent-cockpit.open"

# Exercise the installer as an executable against a filesystem-backed CLI fixture.
# The real Tern CLI is the production boundary; this fixture implements its registry
# operations and refuses removal unless the original is already safely backed up.
TERN_CLI = r'''
import os
from pathlib import Path
import shutil
import sys

args = sys.argv[1:]
plugins = Path(os.environ["TEST_PLUGIN_DIR"])
state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
assert args[:1] == ["plugin"], args
if args[1] == "dir":
    print(plugins)
elif args[1] == "reload":
    print("tern plugin: no daemon running", file=sys.stderr)
    sys.exit(1)
elif args[1] in ("remove", "unlink"):
    if args[1] == "remove":
        assert not (plugins / (args[2] + ".path")).exists(), "Linked plugins require unlink"
    targets = [plugins / (args[2] + ".path")] if args[1] == "unlink" else [plugins / args[2]]
    for target in targets:
        if not target.exists() and not target.is_symlink():
            continue
        copies = list((state / "dot-files/backups/tern-cockpit").glob("*/plugins/" + target.name))
        if target.is_symlink():
            assert any(copy.is_symlink() and os.readlink(copy) == os.readlink(target) for copy in copies)
            target.unlink()
        elif target.is_dir():
            assert any((copy / "personal.luau").read_bytes() == (target / "personal.luau").read_bytes()
                       for copy in copies), "Copied plugin must be backed up BEFORE removal"
            shutil.rmtree(target)
        else:
            assert any(copy.read_bytes() == target.read_bytes() for copy in copies)
            target.unlink()
elif args[1] == "link":
    source = Path(args[2])
    target = plugins / (source.name + ".path")
    assert not (plugins / source.name).exists(), "Copied plugin conflicts with link"
    assert not target.exists(), "Existing link must be removed before replacement"
    plugins.mkdir(parents=True, exist_ok=True)
    target.write_text(str(source) + "\n")
else:
    raise AssertionError(args)
'''


class TernCockpitInstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.repo = self.home / "checkout"
        self.repo.mkdir()
        shutil.copy2(ROOT / "install-tern-cockpit.py", self.repo / "install-tern-cockpit.py")
        self.sources = {}
        for name in ("hostkeys", "agent-cockpit"):
            source = self.repo / "tern/plugins" / name
            source.mkdir(parents=True)
            (source / "plugin.toml").write_text(f'id = "{name}"\nwindow = "window.luau"\n')
            (source / "window.luau").write_text("-- fixture window entrypoint\n")
            self.sources[name] = source
        for filename in ("hook_settings.py", "hook_record.py"):
            shutil.copy2(ROOT / "tern/plugins/agent-cockpit" / filename, self.sources["agent-cockpit"] / filename)
        self.config = self.home / "config"
        self.state = self.home / "state"
        # Deliberately not the conventional config/tern/plugins: the installer
        # must respect the CLI's answer rather than inventing the registry path.
        self.plugins = self.home / "daemon-plugin-registry"
        binaries = self.home / "bin"
        binaries.mkdir()
        cli = binaries / "tern"
        cli.write_text(f"#!{sys.executable}\n" + TERN_CLI)
        cli.chmod(0o755)
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config),
            "XDG_STATE_HOME": str(self.state),
            "PATH": str(binaries) + os.pathsep + os.environ.get("PATH", ""),
            "TEST_PLUGIN_DIR": str(self.plugins),
        }
        self.environment.pop("TERN_CONFIG_DIR", None)
        self.environment.pop("CLAUDE_CONFIG_DIR", None)
        self.environment.pop("CODEX_HOME", None)
        self.settings = self.config / "tern/settings.json"

    def install(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.repo / "install-tern-cockpit.py")], env=self.environment,
            capture_output=True, text=True,
        )

    def save_settings(self, content: str) -> None:
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(content)


    def backups(self) -> list[Path]:
        root = self.state / "dot-files/backups/tern-cockpit"
        return sorted(root.rglob("*")) if root.exists() else []

    def assert_success(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_copied_plugins_and_settings_are_preserved_once_before_migration(self) -> None:
        original = '{"theme":"my-theme", "keymap":"custom", "auth":{"token":"private"}, "keybinds":{"ctrl+s>a":"personal.action", "ctrl+s>tab":"plugin.hostkeys.toggle_host", "alt+x":"personal.other"}}\n'
        self.save_settings(original)
        self.settings.chmod(0o640)
        for name in self.sources:
            copied = self.plugins / name
            copied.mkdir(parents=True)
            (copied / "personal.luau").write_text(name + " local changes\n")
        unrelated = self.plugins / "unrelated"
        unrelated.mkdir()
        (unrelated / "personal.luau").write_text("keep unrelated plugin\n")
        self.assert_success(self.install())
        expected = json.loads(original)
        expected["keybinds"]["ctrl+s>a"] = ACTION
        self.assertEqual(json.loads(self.settings.read_text()), expected)
        self.assertEqual(stat.S_IMODE(self.settings.stat().st_mode), 0o640)
        saved_settings = list(self.state.rglob("settings.json"))
        self.assertEqual([path.read_text() for path in saved_settings], [original])
        for name, source in self.sources.items():
            self.assertEqual((self.plugins / f"{name}.path").read_text().strip(), str(source))
            self.assertFalse((self.plugins / name).exists())
            copies = list(self.state.glob(f"dot-files/backups/tern-cockpit/*/plugins/{name}/personal.luau"))
            self.assertEqual([path.read_text() for path in copies], [name + " local changes\n"])
        self.assertEqual((unrelated / "personal.luau").read_text(), "keep unrelated plugin\n")
        first_backups = self.backups()
        first_bytes = self.settings.read_bytes()
        first_stat = self.settings.stat()
        self.assert_success(self.install())
        self.assertEqual(self.backups(), first_backups)
        self.assertEqual(self.settings.read_bytes(), first_bytes)
        self.assertEqual(self.settings.stat().st_mtime_ns, first_stat.st_mtime_ns)
        self.assertFalse((self.config / "tern/plugins").exists())

    def test_existing_correct_links_and_binding_are_not_rewritten_or_backed_up(self) -> None:
        original = '{ "keybinds": {"ctrl+s>a": "plugin.agent-cockpit.open"}, "font_size": 17 }\n'
        self.save_settings(original)
        self.plugins.mkdir()
        for name, source in self.sources.items():
            (self.plugins / f"{name}.path").write_text(str(source) + "\n")
        self.assert_success(self.install())
        self.assertEqual(self.settings.read_text(), original)
        self.assertFalse(self.state.exists())

    def test_conflicting_link_backs_up_only_pointer_not_external_checkout(self) -> None:
        self.plugins.mkdir()
        outside = self.home / "external-hostkeys"
        outside.mkdir()
        (outside / "personal.luau").write_text("external source must not be changed\n")
        pointer = str(outside) + "\n"
        (self.plugins / "hostkeys.path").write_text(pointer)
        self.assert_success(self.install())
        saved = list(self.state.rglob("hostkeys.path"))
        self.assertEqual([path.read_text() for path in saved], [pointer])
        self.assertEqual((outside / "personal.luau").read_text(), "external source must not be changed\n")
        self.assertFalse(any(path.name == "personal.luau" for path in self.backups()))
        self.assertEqual(json.loads(self.settings.read_text()), {"keybinds": {"ctrl+s>a": ACTION}})
        self.assertFalse(any(path.name == "settings.json" for path in self.backups()))
        first = self.backups()
        self.assert_success(self.install())
        self.assertEqual(self.backups(), first)

    def test_custom_config_dir_and_symlinked_settings_keep_link_and_target_content(self) -> None:
        self.settings = self.home / "custom-tern/settings.json"
        self.environment["TERN_CONFIG_DIR"] = str(self.settings.parent)
        self.settings.parent.mkdir()
        target = self.home / "personal-settings.json"
        original = '{"theme":"personal", "keybinds":{"ctrl+s>v":"split_right"}}\n'
        target.write_text(original)
        self.settings.symlink_to(target)
        self.assert_success(self.install())
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(self.settings.resolve(), target)
        expected = json.loads(original)
        expected["keybinds"]["ctrl+s>a"] = ACTION
        self.assertEqual(json.loads(target.read_text()), expected)
        self.assertEqual([path.read_text() for path in self.state.rglob("settings.json")], [original])
        self.assertFalse(self.config.exists())
        first = self.backups()
        self.assert_success(self.install())
        self.assertEqual(self.backups(), first)

    def test_invalid_settings_fail_without_mutating_settings_plugins_or_backups(self) -> None:
        for original in ('{bad json\n', '[]\n', 'null\n', '42\n', '{"keybinds":[]}\n',
                         '{"keybinds":null}\n', '{"theme":"one","theme":"two"}\n', '{"font_size":NaN}\n'):
            with self.subTest(original=original):
                self.save_settings(original)
                result = self.install()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.settings.read_text(), original)
                self.assertFalse(self.plugins.exists())
                self.assertFalse(self.state.exists())

    def test_all_sources_are_validated_before_any_plugin_is_linked(self) -> None:
        self.save_settings('{"theme":"keep"}\n')
        (self.sources["hostkeys"] / "window.luau").unlink()
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.settings.read_text(), '{"theme":"keep"}\n')
        self.assertFalse(self.plugins.exists())
        self.assertFalse(self.state.exists())

    def test_legacy_directory_symlink_is_backed_up_without_copying_or_deleting_source(self) -> None:
        self.plugins.mkdir()
        outside = self.home / "legacy-hostkeys"
        outside.mkdir()
        (outside / "personal.luau").write_text("do not delete this source\n")
        (self.plugins / "hostkeys").symlink_to(outside, target_is_directory=True)
        self.assert_success(self.install())
        saved = list(self.state.glob("dot-files/backups/tern-cockpit/*/plugins/hostkeys"))
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].is_symlink())
        self.assertEqual(os.readlink(saved[0]), str(outside))
        self.assertEqual((outside / "personal.luau").read_text(), "do not delete this source\n")
        self.assertEqual((self.plugins / "hostkeys.path").read_text().strip(), str(self.sources["hostkeys"]))

    def test_invalid_second_plugin_registry_entry_does_not_partially_install_first(self) -> None:
        self.save_settings('{"theme":"keep"}\n')
        invalid = self.plugins / "hostkeys.path"
        invalid.mkdir(parents=True)
        sentinel = invalid / "personal-data"
        sentinel.write_text("not a plugin pointer\n")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.settings.read_text(), '{"theme":"keep"}\n')
        self.assertEqual(sentinel.read_text(), "not a plugin pointer\n")
        self.assertFalse((self.plugins / "agent-cockpit.path").exists())
        self.assertFalse(self.state.exists())

    def test_home_defaults_create_only_settings_and_requested_links(self) -> None:
        self.environment.pop("XDG_CONFIG_HOME")
        self.environment.pop("XDG_STATE_HOME")
        self.assert_success(self.install())
        settings = self.home / ".config/tern/settings.json"
        self.assertEqual(json.loads(settings.read_text()), {"keybinds": {"ctrl+s>a": ACTION}})
        self.assertFalse((self.home / ".local/state").exists())
        self.assertFalse((self.home / ".config/tern/plugins").exists())


if __name__ == "__main__":
    unittest.main()
