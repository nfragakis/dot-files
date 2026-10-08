from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import unittest


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "omarchy/plugins/nfragakis.zai/collect-zai.py"


def limit(window_id: str, duration_ms: int, used_fraction: float, resets_at: int) -> dict:
    return {
        "id": f"zai:credits:{window_id}",
        "label": f"ZAI {window_id} Credit Quota",
        "scope": {"provider": "zai", "windowId": window_id, "shared": True},
        "window": {
            "id": window_id,
            "label": window_id,
            "durationMs": duration_ms,
            "resetsAt": resets_at,
        },
        "amount": {
            "usedFraction": used_fraction,
            "remainingFraction": 1 - used_fraction,
            "unit": "credits",
        },
        "status": "ok",
    }


def usage_payload(*limits: dict) -> dict:
    return {
        "generatedAt": 1790006221882,
        "reports": [{
            "provider": "zai",
            "fetchedAt": 1790006001124,
            "limits": list(limits),
            "metadata": {"planType": "pro"},
        }],
        "accountsWithoutUsage": [],
        "disabledCredentials": [],
    }


class CollectorCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.state = self.home / "state"
        self.cache = self.home / "cache"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def install_fake_omp(self, payload: dict, exit_code: int = 0) -> None:
        executable = self.bin / "omp"
        executable.write_text(
            "#!/usr/bin/python3\n"
            "import json, sys\n"
            f"print(json.dumps({payload!r}))\n"
            f"raise SystemExit({exit_code})\n",
            encoding="utf-8",
        )
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update({
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state),
            "XDG_CACHE_HOME": str(self.cache),
            "PATH": str(self.bin),
        })
        return env

    def run_collector(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(COLLECTOR), *arguments],
            check=False,
            capture_output=True,
            text=True,
            env=self.environment(),
            timeout=10,
        )

    def test_live_shaped_usage_becomes_two_panel_meters(self) -> None:
        five_hour_reset = 1790023981005
        weekly_reset = 1790610717982
        self.install_fake_omp(usage_payload(
            limit("5h", 5 * 60 * 60 * 1000, 0.25, five_hour_reset),
            limit("1w", 7 * 24 * 60 * 60 * 1000, 0.40, weekly_reset),
        ))

        result = self.run_collector("--print")

        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertTrue(record["ready"])
        self.assertEqual(record["tierLabel"], "Pro")
        self.assertEqual(record["usageStatusText"], "")
        self.assertEqual(record["limits"], [
            {
                "label": "Session (5-hour)",
                "percent": 0.25,
                "resetsAt": "2026-09-21T20:53:01.005Z",
            },
            {
                "label": "Weekly (7-day)",
                "percent": 0.4,
                "resetsAt": "2026-09-28T15:51:57.982Z",
            },
        ])

    def test_partial_quota_response_writes_unavailable_not_a_zero_meter(self) -> None:
        self.install_fake_omp(usage_payload(
            limit("5h", 5 * 60 * 60 * 1000, 0.0, 1790023981005),
        ))

        result = self.run_collector()

        self.assertEqual(result.returncode, 2, result.stderr)
        record_path = self.state / "omarchy/agents/usage/zai.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertFalse(record["ready"])
        self.assertEqual(record["limits"], [])
        self.assertIn("incomplete", record["usageStatusText"].lower())
        self.assertEqual(record_path.stat().st_mode & 0o777, 0o600)

    def test_only_zai_assistant_messages_contribute_local_tokens(self) -> None:
        self.install_fake_omp(usage_payload(
            limit("5h", 5 * 60 * 60 * 1000, 0.01, 1790023981005),
            limit("1w", 7 * 24 * 60 * 60 * 1000, 0.02, 1790610717982),
        ))
        session = self.home / ".omp/agent/sessions/-work/session.jsonl"
        session.parent.mkdir(parents=True)
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        messages = [
            {"type": "message", "timestamp": timestamp, "message": {
                "role": "assistant", "provider": "zai", "api": "anthropic-messages",
                "model": "glm-5.3", "usage": {
                    "input": 100, "output": 20, "cacheRead": 30, "cacheWrite": 0,
                    "totalTokens": 150,
                },
            }},
            {"type": "message", "timestamp": timestamp, "message": {
                "role": "assistant", "provider": "opencode-go", "model": "glm-5.3",
                "usage": {"input": 900, "output": 900},
            }},
            {"type": "message", "timestamp": timestamp, "message": {
                "role": "user", "provider": "zai", "model": "glm-5.3",
                "usage": {"input": 500},
            }},
        ]
        session.write_text(
            "".join(json.dumps(message) + "\n" for message in messages),
            encoding="utf-8",
        )

        result = self.run_collector("--force", "--print")

        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["todayPrompts"], 1)
        self.assertEqual(record["todayTotalTokens"], 150)
        self.assertEqual(record["todayTokensByModel"], {"glm-5.3": 150})
        self.assertEqual(record["modelUsage"], {"glm-5.3": {
            "inputTokens": 100,
            "outputTokens": 20,
            "cacheReadInputTokens": 30,
            "cacheCreationInputTokens": 0,
        }})

    def test_truncated_local_cache_is_rescanned_instead_of_becoming_zero(self) -> None:
        self.install_fake_omp(usage_payload(
            limit("5h", 5 * 60 * 60 * 1000, 0.01, 1790023981005),
            limit("1w", 7 * 24 * 60 * 60 * 1000, 0.02, 1790610717982),
        ))
        cache = self.cache / "omarchy/agent-usage/zai.json"
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({
            "schemaVersion": 1,
            "scanDate": datetime.now().strftime("%Y-%m-%d"),
            "scannedAt": datetime.now().timestamp(),
            "stats": {},
        }), encoding="utf-8")
        session = self.home / ".omp/agent/sessions/-work/session.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text(json.dumps({
            "type": "message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": {
                "role": "assistant",
                "provider": "zai",
                "model": "glm-5.3",
                "usage": {"input": 10, "output": 5},
            },
        }) + "\n", encoding="utf-8")

        result = self.run_collector("--print")

        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["todayPrompts"], 1)
        self.assertEqual(record["todayTotalTokens"], 15)


if __name__ == "__main__":
    unittest.main()
