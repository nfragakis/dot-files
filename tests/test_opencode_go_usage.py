from __future__ import annotations

import importlib.util
import io
import json
import os
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest
import urllib.error
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "omarchy/plugins/nfragakis.opencode-go"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load_module("collect_opencode_go", PLUGIN / "collect-opencode-go.py")


def usage_payload(**windows) -> dict:
    return {"usage": {key: value for key, value in windows.items()}}


class DecodeLimitsTest(unittest.TestCase):
    def test_percent_reaches_the_panel_as_a_fraction(self) -> None:
        # The endpoint reports 0-100 and the panel multiplies by 100 again;
        # dividing here is the whole conversion between the two.
        limits = collector.decode_limits(usage_payload(
            rolling={"status": "ok", "percent": 42, "resetsAt": "2026-09-16T18:25:27.000Z"},
            weekly={"status": "ok", "percent": 0, "resetsAt": "2026-09-21T00:00:00.000Z"},
            monthly={"status": "rate-limited", "percent": 100, "resetsAt": "2026-10-16T13:19:27.000Z"},
        ))
        self.assertEqual([entry["percent"] for entry in limits], [0.42, 0.0, 1.0])
        self.assertEqual([entry["label"] for entry in limits], ["Session (5-hour)", "Weekly (7-day)", "Monthly"])
        self.assertEqual(limits[0]["resetsAt"], "2026-09-16T18:25:27.000Z")

    def test_windows_the_endpoint_did_not_send_are_skipped_not_zeroed(self) -> None:
        # A shape change must not paint a 0% meter that hides real usage.
        limits = collector.decode_limits(usage_payload(
            rolling={"status": "ok", "percent": 7, "resetsAt": "2026-09-16T18:25:27.000Z"},
            weekly={"status": "ok", "percent": "12", "resetsAt": "2026-09-21T00:00:00.000Z"},
            monthly={"status": "ok", "percent": 140, "resetsAt": "2026-10-16T13:19:27.000Z"},
        ))
        self.assertEqual([entry["label"] for entry in limits], ["Session (5-hour)"])

    def test_a_payload_without_usage_is_not_an_error(self) -> None:
        self.assertEqual(collector.decode_limits({}), [])
        self.assertEqual(collector.decode_limits({"usage": []}), [])


class CredentialTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.environment = mock.patch.dict(os.environ, {
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / "share"),
            "XDG_STATE_HOME": str(self.home / "state"),
        }, clear=False)
        self.environment.start()
        for name in ("OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"):
            os.environ.pop(name, None)

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def write_auth(self, providers: dict) -> None:
        path = self.home / "share" / "opencode" / "auth.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(providers), encoding="utf-8")

    def write_omp_db(self, rows: list[str]) -> None:
        path = self.home / ".omp" / "agent" / "agent.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE auth_credentials (provider TEXT NOT NULL, data TEXT NOT NULL)")
        conn.executemany("INSERT INTO auth_credentials (provider, data) VALUES (?, ?)",
                         [("opencode-go", row) for row in rows])
        conn.commit()
        conn.close()

    def test_environment_beats_the_stores_and_the_go_provider_beats_zen(self) -> None:
        self.write_auth({
            "opencode": {"type": "api", "key": "zen-key"},
            "opencode-go": {"type": "api", "key": "go-key"},
        })
        self.write_omp_db([json.dumps({"key": "omp-key", "source": "login"})])
        self.assertEqual([key for _, key in collector.candidate_keys()], ["omp-key", "go-key", "zen-key"])

        os.environ["OPENCODE_API_KEY"] = "env-key"
        self.assertEqual([key for _, key in collector.candidate_keys()],
                         ["env-key", "omp-key", "go-key", "zen-key"])

    def test_credential_blobs_survive_the_store_changing_shape(self) -> None:
        self.assertEqual(collector.credential_strings('{"key": "a", "source": "login"}'), ["a"])
        self.assertEqual(collector.credential_strings('{"apiKey": "b"}'), ["b"])
        self.assertEqual(collector.credential_strings('"c"'), ["c"])
        self.assertEqual(collector.credential_strings('{"refresh": "r"}'), [])
        self.assertEqual(collector.credential_strings("not json"), [])


class ProbeLimitsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.environment = mock.patch.dict(os.environ, {
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.home / "state"),
            "XDG_DATA_HOME": str(self.home / "share"),
            "OPENCODE_API_KEY": "test-key",
        }, clear=False)
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def response(self, payload: dict):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(payload).encode()

        return Response()

    def test_a_rejected_key_names_the_source_instead_of_claiming_no_usage(self) -> None:
        error = urllib.error.HTTPError(collector.USAGE_ENDPOINT, 403, "Forbidden", {}, None)
        self.addCleanup(error.close)
        with mock.patch.object(collector.urllib.request, "urlopen", side_effect=error):
            result = collector.probe_limits()
        self.assertFalse(result["ready"])
        self.assertEqual(result["usageStatusText"], "OpenCode Go key was rejected.")
        self.assertIn("OPENCODE_API_KEY", result["authHelpText"])
        self.assertNotIn("retryAdvised", result)

    def test_an_unreachable_endpoint_asks_the_service_for_an_early_retry(self) -> None:
        with mock.patch.object(collector.urllib.request, "urlopen", side_effect=OSError("network is unreachable")):
            result = collector.probe_limits()
        self.assertFalse(result["ready"])
        self.assertEqual(result["usageStatusText"], "OpenCode Go limits unavailable.")
        # The retry signal is the collector's exit code, not a record field:
        # the panel's retryAdvised path re-runs omarchy-agent-usage-update,
        # which has no collector for this agent and could never refresh this
        # record.
        self.assertTrue(result["unreachable"])
        self.assertNotIn("retryAdvised", result)

    def test_accepted_key_returns_limits_and_no_complaint(self) -> None:
        payload = usage_payload(
            rolling={"status": "ok", "percent": 5, "resetsAt": "2026-09-16T18:25:27.000Z"},
            weekly={"status": "ok", "percent": 11, "resetsAt": "2026-09-21T00:00:00.000Z"},
            monthly={"status": "ok", "percent": 23, "resetsAt": "2026-10-16T13:19:27.000Z"},
        )
        with mock.patch.object(collector.urllib.request, "urlopen", return_value=self.response(payload)):
            result = collector.probe_limits()
        self.assertTrue(result["ready"])
        self.assertEqual(result["usageStatusText"], "")
        self.assertEqual([entry["percent"] for entry in result["limits"]], [0.05, 0.11, 0.23])

    def test_a_partial_window_set_is_a_failure_not_a_shorter_panel(self) -> None:
        # Replacing a complete record with one missing a meter would drop a
        # window the panel was showing, with nothing to say why.
        payload = usage_payload(rolling={"status": "ok", "percent": 5, "resetsAt": "2026-09-16T18:25:27.000Z"})
        with mock.patch.object(collector.urllib.request, "urlopen", return_value=self.response(payload)):
            result = collector.probe_limits()
        self.assertFalse(result["ready"])
        self.assertEqual(result["limits"], [])
        self.assertTrue(result["unreachable"])
        self.assertIn("incomplete", result["usageStatusText"])


class RecordWriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.record = Path(self.temporary.name) / "agents" / "usage" / "opencode-go.json"
        self.environment = mock.patch.dict(os.environ, {
            "HOME": self.temporary.name,
            "XDG_STATE_HOME": str(Path(self.temporary.name) / "state"),
        }, clear=False)
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def run_main(self, limits: dict) -> int:
        with mock.patch.object(collector, "usage_record_path", return_value=self.record), \
             mock.patch.object(collector, "local_stats", return_value={"todayPrompts": 0}), \
             mock.patch.object(collector, "probe_limits", return_value=limits), \
             mock.patch("sys.argv", ["collect-opencode-go.py"]), \
             mock.patch("sys.stdout", new=io.StringIO()):
            return collector.main()

    def test_the_retry_signal_is_an_exit_code_and_the_record_stays_clean(self) -> None:
        code = self.run_main({
            "limits": [],
            "ready": False,
            "unreachable": True,
            "usageStatusText": "OpenCode Go limits unavailable.",
            "authHelpText": "Could not reach the endpoint",
        })
        self.assertEqual(code, 2)
        record = json.loads(self.record.read_text(encoding="utf-8"))
        self.assertFalse(record["ready"])
        self.assertNotIn("retryAdvised", record)
        self.assertNotIn("unreachable", record)
        self.assertEqual(record["id"], "opencode-go")

    def test_the_record_is_user_only_like_the_other_agents(self) -> None:
        code = self.run_main({"limits": [], "ready": True, "usageStatusText": "", "authHelpText": ""})
        self.assertEqual(code, 0)
        self.assertEqual(self.record.stat().st_mode & 0o777, 0o600)


class SessionScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.environment = mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False)
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def write_session(self, lines: list[dict]) -> None:
        path = self.home / ".omp" / "agent" / "sessions" / "-work" / "session.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")

    def test_only_go_models_are_counted_and_their_tokens_land_in_today(self) -> None:
        now_ms = int(datetime.now().timestamp() * 1000)
        self.write_session([
            {"type": "message", "timestamp": now_ms, "message": {
                "role": "assistant", "provider": "opencode-go", "model": "deepseek-v4.1-flash",
                "usage": {"input": 100, "output": 20, "cacheRead": 30, "cacheWrite": 0,
                          "totalTokens": 150, "reasoningTokens": 5}}},
            {"type": "message", "timestamp": now_ms, "message": {
                "role": "assistant", "provider": "openai-codex", "model": "gpt-5.6-sol",
                "usage": {"input": 900, "output": 900}}},
            {"type": "message", "timestamp": now_ms, "message": {
                "role": "user", "provider": "opencode-go", "model": "deepseek-v4.1-flash",
                "usage": {"input": 500}}},
        ])
        stats = collector.scan_sessions()
        self.assertEqual(stats["totalPrompts"], 1)
        self.assertEqual(stats["todayPrompts"], 1)
        # reasoningTokens rides inside output; counting it again would make the
        # panel disagree with what the gateway charged for.
        self.assertEqual(stats["todayTotalTokens"], 150)
        self.assertEqual(stats["todayTokensByModel"], {"deepseek-v4.1-flash": 150})
        self.assertEqual(stats["modelUsage"], {"deepseek-v4.1-flash": {
            "inputTokens": 100, "outputTokens": 20, "cacheReadInputTokens": 30, "cacheCreationInputTokens": 0}})
        self.assertEqual(stats["recentDays"][-1]["messageCount"], 150)
        self.assertTrue(stats["hasLocalStats"])

    def test_machines_without_session_roots_report_no_local_stats(self) -> None:
        stats = collector.scan_sessions()
        self.assertEqual(stats["totalPrompts"], 0)
        self.assertFalse(stats["hasLocalStats"])


if __name__ == "__main__":
    unittest.main()
