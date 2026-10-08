from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "native_usage", ROOT / "omarchy/plugins/nfragakis.agents/collect-native.py"
)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class CodexRpcTest(unittest.TestCase):
    def test_notification_and_response_in_one_write_do_not_timeout(self):
        # A real pipe and TextIOWrapper reproduce app-server's coalesced output.
        server = """
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    sys.stdout.write(json.dumps({'method': 'account/updated', 'params': {}}) + '\\n'
        + json.dumps({'id': request['id'], 'result': {'ok': True}}) + '\\n'
        + json.dumps({'method': 'configWarning', 'params': {}}) + '\\n')
    sys.stdout.flush()
"""
        with subprocess.Popen([sys.executable, "-u", "-c", server],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as proc:
            try:
                for request_id, method in ((1, "initialize"), (2, "account/read"), (3, "account/rateLimits/read")):
                    response = native.codex_rpc_request(proc, request_id, method, timeout=0.5)
                    self.assertEqual(response, {"id": request_id, "result": {"ok": True}})
            finally:
                proc.terminate()

    def test_closed_server_reports_the_failing_method(self):
        with subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.readline()"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as proc:
            with self.assertRaisesRegex(RuntimeError, "account/read"):
                native.codex_rpc_request(proc, 2, "account/read", timeout=1)


class ClaudeRenewTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.expired = ("expired-access", 1, "Max 20x")
        self.fresh = ("fresh-access", int((time.time() + 3600) * 1000), "Max 20x")

    def test_expired_login_uses_cli_initialization_and_rereads_credentials(self):
        read = mock.Mock(side_effect=[self.expired, self.expired, self.fresh])
        with mock.patch.object(native.shutil, "which", return_value="/bin/claude"), \
             mock.patch.object(native.subprocess, "run") as run:
            self.assertEqual(native.claude_login(read, self.root / "cache", self.root / "config"), self.fresh)
        command = run.call_args.args[0]
        self.assertIn("--init-only", command)
        self.assertIn('{"disableAllHooks":true}', command)
        self.assertIn("--strict-mcp-config", command)
        self.assertEqual(run.call_args.kwargs["env"]["CLAUDE_CONFIG_DIR"], str(self.root / "config"))
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertTrue(run.call_args.kwargs["check"])

    def test_fresh_and_missing_login_never_start_cli(self):
        for login in (self.fresh, ("", 0, "")):
            with self.subTest(login=login), mock.patch.object(native.subprocess, "run") as run:
                self.assertEqual(native.claude_login(lambda _: login, self.root, self.root), login)
                run.assert_not_called()

    def test_login_refreshed_while_waiting_for_lock_never_starts_cli(self):
        read = mock.Mock(side_effect=[self.expired, self.fresh])
        with mock.patch.object(native.shutil, "which", return_value="/bin/claude"), \
             mock.patch.object(native.subprocess, "run") as run:
            self.assertEqual(native.claude_login(read, self.root, self.root), self.fresh)
            run.assert_not_called()

    def test_failed_renewal_preserves_expired_state_for_upstream_fallback(self):
        with mock.patch.object(native.shutil, "which", return_value="/bin/claude"), \
             mock.patch.object(native.subprocess, "run", side_effect=subprocess.TimeoutExpired("claude", 25)):
            self.assertEqual(native.claude_login(lambda _: self.expired, self.root, self.root), self.expired)


if __name__ == "__main__":
    unittest.main()
