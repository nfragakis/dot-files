from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "omarchy/plugins/nfragakis.agents"


@unittest.skipUnless(shutil.which("quickshell"), "Quickshell is required")
class AgentVisibilityTest(unittest.TestCase):
    def test_period_activity_and_expiring_limits_drive_provider_visibility(self):
        cases = [
            ("lifetime-only", {"totalPrompts": 100, "totalSessions": 10, "activeDays": 5}, False),
            ("unused-subscription", {"ready": True, "limits": [{"label": "Weekly", "percent": 0, "resetsAt": "2026-11-09T12:00:00Z"}], "balance": {"remaining": 10}}, False),
            ("recent-tokens", {"recentDays": [{"date": "2026-10-30", "messageCount": 5}]}, True),
            ("expired-history", {"recentDays": [{"date": "2026-10-29", "messageCount": 5}]}, False),
            ("future-history", {"recentDays": [{"date": "2026-11-06", "messageCount": 5}]}, False),
            ("dated-session", {"activeDates": ["2026-11-02"]}, True),
            ("today-prompts", {"todayPrompts": 1, "updatedAt": "2026-11-05T10:00:00Z"}, True),
            ("stale-today", {"todayPrompts": 1, "updatedAt": "2026-10-29T10:00:00Z"}, False),
            ("weekly-quota", {"limits": [{"label": "Weekly (7-day)", "percent": 0.01, "resetsAt": "2026-11-09T12:00:00Z"}]}, True),
            ("expired-quota", {"limits": [{"label": "Weekly", "percent": 0.5, "resetsAt": "2026-11-05T12:00:00Z"}]}, False),
            ("monthly-quota", {"limits": [{"label": "Monthly", "percent": 0.5, "resetsAt": "2026-11-16T12:00:00Z"}]}, False),
            ("outside-period-quota", {"limits": [{"label": "Weekly", "percent": 0.5, "resetsAt": "2026-11-05T13:00:00Z"}]}, False),
            ("unknown-quota-window", {"limits": [{"label": "Credits", "percent": 0.5, "resetsAt": "2026-11-09T12:00:00Z"}]}, False),
            ("invalid-quota-reset", {"limits": [{"label": "Weekly", "percent": 0.5, "resetsAt": "invalid"}]}, False),
            ("grok", {"recentDays": [{"date": "2026-11-05", "messageCount": 500}]}, False),
        ]
        records = [dict(id=name, **fields) for name, fields, _ in cases]
        qml = '''import QtQuick
import Quickshell
import "%s" as Agents
ShellRoot {
  Agents.Main {
    id: usage
    settings: ({ providers: { grok: { enabled: false } }, usageWindowDays: 7 })
    visibilityNowMs: Date.parse("2026-11-05T12:00:00Z")
  }
  Timer {
    interval: 100
    running: true
    onTriggered: {
      var records = %s
      usage.agents = records.map(function(record) { return { record: record } })
      var weekly = usage.enabledProviders.map(function(p) { return p.providerId })
      usage.settings = { providers: { grok: { enabled: false } }, usageWindowDays: 1 }
      var today = usage.enabledProviders.map(function(p) { return p.providerId })
      usage.settings = { providers: { grok: { enabled: false } }, usageWindowDays: 7 }
      usage.visibilityNowMs = Date.parse("2026-11-13T12:00:00Z")
      var later = usage.enabledProviders.map(function(p) { return p.providerId })
      usage.visibilityNowMs = Date.parse("2026-11-05T12:00:00Z")
      var aggregate = usage.aggregateSnapshots([{
        deviceId: "laptop", updatedAt: "2026-11-05T12:00:00Z",
        providers: {
          old: usage.providerSnapshot({ id: "old", updatedAt: "2026-10-29T10:00:00Z", todayPrompts: 1 }),
          current: usage.providerSnapshot({ id: "current", updatedAt: "2026-11-05T10:00:00Z", todayPrompts: 1 })
        }
      }])
      var synced = [usage.providerHasData(aggregate.providers.old), usage.providerHasData(aggregate.providers.current)]
      console.log("VISIBILITY_RESULTS:" + JSON.stringify({weekly: weekly, today: today, later: later, synced: synced}))
      Qt.quit()
    }
  }
}
''' % (PLUGIN.as_uri(), json.dumps(records))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "shell.qml").write_text(qml)
            environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", TZ="UTC",
                               XDG_STATE_HOME=directory, OMARCHY_PATH=directory)
            result = subprocess.run(["quickshell", "--no-color", "-p", str(path / "shell.qml")],
                                    env=environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout + result.stderr
        line = next(line for line in output.splitlines() if "VISIBILITY_RESULTS:" in line)
        actual = json.loads(line.split("VISIBILITY_RESULTS:", 1)[1])
        for name, _, expected in cases:
            with self.subTest(provider=name):
                self.assertEqual(name in actual["weekly"], expected)
        self.assertEqual(actual["today"], ["today-prompts"])
        self.assertEqual(actual["later"], [])
        self.assertEqual(actual["synced"], [False, True])


if __name__ == "__main__":
    unittest.main()
