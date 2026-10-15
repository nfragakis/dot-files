"""Numeric usage stats for the cockpit's meters, and the pure Lua models."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tern/plugins/agent-cockpit"))
import json
import os
import tempfile
from unittest.mock import patch

import metadata
import metadata_codex as codex
import metadata_usage as usage


class UsageStatsTest(unittest.TestCase):
    def test_complete_ledger_sums_counts_and_costs(self) -> None:
        state = {"ledger": {"a": [[10, 5, 100, 1], 0.25], "b": [[2, 3, None, 4], 0.5]},
                 "prompt": 140, "capacity": 200, "agents": {"x": True, "y": True}}
        self.assertEqual(usage.stats(state), {
            "input": 12, "output": 8, "cache_write": 5, "cost": 0.75,
            "context": 140, "capacity": 200, "agents": 2,
        })

    def test_unattributable_usage_reports_no_totals(self) -> None:
        state = {"ledger": {"a": [[1, 1, 0, 0], None]}, "missing_usage": True, "prompt": 9}
        self.assertEqual(usage.stats(state), {"context": 9})

    def test_partial_cost_is_not_a_total(self) -> None:
        state = {"ledger": {"a": [[1, 1, 0, 0], 0.1], "b": [[1, 1, 0, 0], None]}}
        self.assertNotIn("cost", usage.stats(state))

    def test_incomplete_coverage_has_no_stats(self) -> None:
        self.assertNotIn("usage_stats", usage.fields({"ledger": {}}, "indexing: 1/2 bytes", "test"))

    def test_collector_admits_only_expected_finite_numbers(self) -> None:
        self.assertEqual(metadata._stats({
            "input": 3, "output": -1, "cache_read": 1.5, "context": True, "capacity": "200",
            "cost": float("nan"), "agents": 2, "extra": 7,
        }), {"input": 3, "agents": 2})
        self.assertEqual(metadata._stats({"cost": 2}), {"cost": 2.0})
        self.assertEqual(metadata._stats([1, 2]), {})


    def test_codex_input_excludes_cache_like_other_providers(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"XDG_CACHE_HOME": temp}):
            path = Path(temp) / "rollout.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in (
                {"type": "session_meta", "payload": {"id": "thread"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": 1000, "output_tokens": 50, "cached_input_tokens": 800},
                    "last_token_usage": {"input_tokens": 400}, "model_context_window": 2000,
                }}},
            )))
            numbers = codex._session_usage(path, "thread")["usage_stats"]
        self.assertEqual(numbers["input"], 200)
        self.assertEqual(numbers["cache_read"], 800)
        self.assertEqual((numbers["context"], numbers["capacity"]), (400, 2000))


@unittest.skipUnless(shutil.which("lua"), "Lua is required for the pure cockpit models")
class LuaModelsTest(unittest.TestCase):
    def test_lua_suites(self) -> None:
        for name in ("test_tern_cockpit_selection.lua", "test_tern_cockpit_marks.lua", "test_tern_cockpit_view.lua", "test_tern_cockpit_age.lua"):
            with self.subTest(name):
                result = subprocess.run(["lua", str(ROOT / "tests" / name)], cwd=ROOT,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
