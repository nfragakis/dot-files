#!/usr/bin/python3
"""Collect SuperGrok usage into an Omarchy agents record.

OMP owns the xai-oauth credential, token refresh, and the billing adapter.
This collector asks OMP for its normalized usage report, then adds
machine-local token history from pi/OMP session transcripts. It never reads
or stores the OAuth token.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


PROVIDER = "xai-oauth"
AGENT_ID = "xai-oauth"
AGENT_NAME = "SuperGrok"
AUTH_HELP = "Sign in to SuperGrok in `omp` (`/login xai-oauth`), then run `omp usage --provider xai-oauth`."
LOCAL_SCAN_REUSE_SECONDS = 900
OMP_TIMEOUT_SECONDS = 30


def state_root() -> Path:
  return Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))


def cache_root() -> Path:
  return Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")) / "omarchy" / "agent-usage"


def usage_record_path() -> Path:
  return state_root() / "omarchy" / "agents" / "usage" / f"{AGENT_ID}.json"


def stats_cache_path() -> Path:
  return cache_root() / f"{AGENT_ID}.json"


def runtime_env() -> dict[str, str]:
  home = str(Path.home())
  env = os.environ.copy()
  candidates = (
    env.get("PATH", ""),
    f"{home}/.bun/bin",
    f"{home}/.local/bin",
    f"{home}/.npm-global/bin",
    f"{home}/.local/share/mise/shims",
  )
  env["PATH"] = os.pathsep.join(value for value in candidates if value)
  return env


# -------------------------------------------------------------------- limits


def finite_number(value: Any) -> float | None:
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return None
  result = float(value)
  return result if math.isfinite(result) else None


def used_fraction(entry: dict[str, Any]) -> float | None:
  amount = entry.get("amount")
  if not isinstance(amount, dict):
    return None
  fraction = finite_number(amount.get("usedFraction"))
  if fraction is not None and 0 <= fraction <= 1:
    return fraction
  used = finite_number(amount.get("used"))
  limit = finite_number(amount.get("limit"))
  if used is None or limit is None or limit <= 0 or not 0 <= used <= limit:
    return None
  return used / limit


def reset_time(entry: dict[str, Any]) -> str | None:
  """ISO reset, empty when the limit has no window, None when the window is malformed."""
  window = entry.get("window")
  if not isinstance(window, dict):
    return ""
  value = window.get("resetsAt")
  if value is None or value == "":
    return None
  if isinstance(value, str) and value.strip():
    try:
      parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
      return None
    if parsed.tzinfo is None:
      parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
  timestamp = finite_number(value)
  if timestamp is None or timestamp <= 0:
    return None
  if timestamp > 10_000_000_000:
    timestamp /= 1000
  try:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
  except (OverflowError, OSError, ValueError):
    return None


def limit_title(entry: dict[str, Any]) -> str:
  """Row title the panel will not collapse into a single 'Weekly'."""
  limit_id = str(entry.get("id") or "")
  label = str(entry.get("label") or "").strip()
  if limit_id.endswith(":credits:1w"):
    return "Weekly"
  if ":included:" in limit_id:
    return "Monthly"
  if limit_id.endswith(":on-demand"):
    return "On-demand"
  if ":product:" in limit_id:
    short = label.split(" (", 1)[0].strip()
    return short or "Product"
  if label:
    return label.split(" (", 1)[0].strip()
  return "Limit"


def tier_label(report: dict[str, Any]) -> str:
  metadata = report.get("metadata")
  if isinstance(metadata, dict):
    plan = str(metadata.get("planType") or "").strip()
    if plan:
      return plan
  return "SuperGrok"


def decode_limits(report: Any) -> tuple[list[dict[str, Any]], str]:
  if not isinstance(report, dict) or report.get("provider") != PROVIDER:
    return [], "SuperGrok"
  tier = tier_label(report)
  raw_limits = report.get("limits")
  if not isinstance(raw_limits, list):
    return [], tier

  decoded: list[dict[str, Any]] = []
  seen: set[str] = set()
  for entry in raw_limits:
    if not isinstance(entry, dict):
      continue
    limit_id = str(entry.get("id") or "")
    if limit_id and limit_id in seen:
      continue
    fraction = used_fraction(entry)
    reset = reset_time(entry)
    if fraction is None or reset is None:
      continue
    if limit_id:
      seen.add(limit_id)
    label = str(entry.get("label") or "").strip() or limit_title(entry)
    decoded.append({
      "label": label,
      "title": limit_title(entry),
      "percent": round(fraction, 6),
      "resetsAt": reset,
    })
  return decoded, tier


def inferred_zero(limits: list[dict[str, Any]]) -> bool:
  """OMP synthesizes 0% when xAI omits creditUsagePercent.

  A lone weekly-credits window at exactly 0 is that shape: no product,
  monthly, or on-demand window came back with it. A measured 0% alongside
  any other window is left alone.
  """
  if len(limits) != 1 or limits[0].get("title") != "Weekly":
    return False
  percent = limits[0].get("percent")
  return isinstance(percent, (int, float)) and not isinstance(percent, bool) and percent == 0


def unavailable(text: str, help_text: str, *, unreachable: bool = False, tier: str = "SuperGrok") -> dict[str, Any]:
  result: dict[str, Any] = {
    "limits": [],
    "ready": False,
    "usageStatusText": text,
    "authHelpText": help_text,
    "tierLabel": tier,
  }
  if unreachable:
    result["unreachable"] = True
  return result


def probe_limits() -> dict[str, Any]:
  env = runtime_env()
  omp = shutil.which("omp", path=env.get("PATH"))
  if not omp:
    return unavailable("SuperGrok usage needs OMP.", AUTH_HELP)

  try:
    result = subprocess.run(
      [omp, "usage", "--json", "--provider", PROVIDER, "--redact"],
      check=False,
      capture_output=True,
      text=True,
      timeout=OMP_TIMEOUT_SECONDS,
      env=env,
    )
  except (OSError, subprocess.SubprocessError) as exc:
    return unavailable("SuperGrok limits unavailable.", f"OMP usage query failed: {exc}", unreachable=True)

  if result.returncode != 0:
    detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else f"exit {result.returncode}"
    return unavailable("SuperGrok limits unavailable.", f"OMP usage query failed: {detail}", unreachable=True)
  try:
    payload = json.loads(result.stdout)
  except json.JSONDecodeError:
    return unavailable("SuperGrok limits unavailable.", "OMP returned an invalid usage report.", unreachable=True)

  reports = payload.get("reports") if isinstance(payload, dict) else None
  if not isinstance(reports, list):
    reports = []
  report = next((value for value in reports if isinstance(value, dict) and value.get("provider") == PROVIDER), None)
  if report is None:
    return unavailable("SuperGrok is not signed in.", AUTH_HELP)

  limits, tier = decode_limits(report)
  if inferred_zero(limits):
    return unavailable(
      "Weekly usage was not reported.",
      "OMP may infer 0% when xAI omits weekly usage. That is not a measured empty window. Local token history is still shown.",
      tier=tier,
    )
  if not limits:
    return unavailable(
      "SuperGrok returned no usage windows.",
      "Expected at least one decoded limit from `omp usage --provider xai-oauth`.",
      unreachable=True,
      tier=tier,
    )
  return {
    "limits": limits,
    "ready": True,
    "usageStatusText": "",
    "authHelpText": "",
    "tierLabel": tier,
  }


# --------------------------------------------------------------- local stats


def number(value: Any) -> int:
  try:
    return int(value or 0)
  except (TypeError, ValueError):
    return 0


def local_day(value: Any) -> str:
  if value is None:
    return dt.datetime.now().strftime("%Y-%m-%d")
  if isinstance(value, (int, float)):
    if value > 10_000_000_000:
      value /= 1000
    return dt.datetime.fromtimestamp(value).strftime("%Y-%m-%d")
  text = str(value)
  try:
    parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    if parsed.tzinfo is not None:
      parsed = parsed.astimezone()
    return parsed.strftime("%Y-%m-%d")
  except ValueError:
    return dt.datetime.now().strftime("%Y-%m-%d")


def session_roots() -> list[Path]:
  return [
    Path.home() / ".pi" / "agent" / "sessions",
    Path.home() / ".omp" / "agent" / "sessions",
  ]


class Stats:
  def __init__(self) -> None:
    now = dt.datetime.now()
    self.today = now.strftime("%Y-%m-%d")
    dates = [(now - dt.timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(6, -1, -1)]
    self.recent = {day: {"date": day, "messageCount": 0} for day in dates}
    self.model_usage: dict[str, dict[str, int]] = {}
    self.today_tokens_by_model: dict[str, int] = {}
    self.today_sessions: set[str] = set()
    self.total_sessions: set[str] = set()
    self.active_days: set[str] = set()
    self.today_prompts = 0
    self.today_total_tokens = 0
    self.total_prompts = 0

  def add(self, day: str, session_key: str, model: str, tokens: dict[str, int]) -> None:
    total = sum(tokens.values())
    if total <= 0:
      return
    self.total_prompts += 1
    self.total_sessions.add(session_key)
    self.active_days.add(day)
    bucket = self.model_usage.setdefault(model, {
      "inputTokens": 0,
      "outputTokens": 0,
      "cacheReadInputTokens": 0,
      "cacheCreationInputTokens": 0,
    })
    bucket["inputTokens"] += tokens["input"]
    bucket["outputTokens"] += tokens["output"]
    bucket["cacheReadInputTokens"] += tokens["cacheRead"]
    bucket["cacheCreationInputTokens"] += tokens["cacheWrite"]
    if day in self.recent:
      self.recent[day]["messageCount"] += total
    if day == self.today:
      self.today_prompts += 1
      self.today_sessions.add(session_key)
      self.today_total_tokens += total
      self.today_tokens_by_model[model] = self.today_tokens_by_model.get(model, 0) + total

  def record(self, has_local_stats: bool) -> dict[str, Any]:
    return {
      "hasLocalStats": has_local_stats,
      "hasPromptStats": has_local_stats,
      "todayPrompts": self.today_prompts,
      "todaySessions": len(self.today_sessions),
      "todayTotalTokens": self.today_total_tokens,
      "todayTokensByModel": self.today_tokens_by_model,
      "recentDays": list(self.recent.values()),
      "totalPrompts": self.total_prompts,
      "totalSessions": len(self.total_sessions),
      "activeDays": len(self.active_days),
      "activeDates": sorted(self.active_days),
      "modelUsage": self.model_usage,
    }


def scan_sessions() -> dict[str, Any]:
  stats = Stats()
  roots = [root for root in session_roots() if root.exists()]
  for root in roots:
    for path in sorted(root.rglob("*.jsonl")):
      try:
        handle = path.open("r", encoding="utf-8", errors="replace")
      except OSError:
        continue
      with handle:
        for raw in handle:
          if '"xai-oauth"' not in raw or not raw.lstrip().startswith("{"):
            continue
          try:
            entry = json.loads(raw)
          except json.JSONDecodeError:
            continue
          if not isinstance(entry, dict) or entry.get("type") != "message":
            continue
          message = entry.get("message")
          if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
          if message.get("provider") != PROVIDER:
            continue
          usage = message.get("usage")
          if not isinstance(usage, dict):
            continue
          tokens = {
            "input": number(usage.get("input")),
            "output": number(usage.get("output")),
            "cacheRead": number(usage.get("cacheRead")),
            "cacheWrite": number(usage.get("cacheWrite")),
          }
          total = number(usage.get("totalTokens"))
          if total and not any(tokens.values()):
            tokens["input"] = total
          if not any(tokens.values()):
            continue
          model = str(message.get("model") or AGENT_NAME)
          stats.add(
            local_day(entry.get("timestamp") or message.get("timestamp")),
            str(path),
            model,
            tokens,
          )
  return stats.record(bool(roots))


# --------------------------------------------------------------------- cache


def write_json(path: Path, payload: Any) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
  descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
  with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
  os.chmod(temporary, 0o600)
  os.replace(temporary, path)


def read_cached_stats(max_age_seconds: int, today: str) -> dict[str, Any] | None:
  try:
    cached = json.loads(stats_cache_path().read_text(encoding="utf-8"))
  except (OSError, json.JSONDecodeError):
    return None
  if not isinstance(cached, dict) or cached.get("schemaVersion") != 1 or cached.get("scanDate") != today:
    return None
  scanned_at = finite_number(cached.get("scannedAt"))
  if scanned_at is None or dt.datetime.now().timestamp() - scanned_at > max_age_seconds:
    return None
  stats = cached.get("stats")
  if not isinstance(stats, dict):
    return None
  required = (
    "hasLocalStats",
    "todayPrompts",
    "todaySessions",
    "todayTotalTokens",
    "todayTokensByModel",
    "recentDays",
    "totalPrompts",
    "totalSessions",
    "activeDays",
    "activeDates",
    "modelUsage",
  )
  return stats if all(key in stats for key in required) else None


def local_stats(force: bool) -> dict[str, Any]:
  today = dt.datetime.now().strftime("%Y-%m-%d")
  if not force:
    cached = read_cached_stats(LOCAL_SCAN_REUSE_SECONDS, today)
    if cached is not None:
      return cached
  stats = scan_sessions()
  try:
    write_json(stats_cache_path(), {
      "schemaVersion": 1,
      "scanDate": today,
      "scannedAt": dt.datetime.now().timestamp(),
      "stats": stats,
    })
  except OSError as exc:
    print(f"collect-grok: could not write usage cache ({exc})", file=sys.stderr)
  return stats


# ---------------------------------------------------------------------- main


def build_record(stats: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
  record: dict[str, Any] = {
    "schemaVersion": 1,
    "id": AGENT_ID,
    "name": AGENT_NAME,
    "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    "ready": bool(limits.get("ready")),
    "tierLabel": str(limits.get("tierLabel") or "SuperGrok"),
    "usageStatusText": str(limits.get("usageStatusText") or ""),
    "authHelpText": str(limits.get("authHelpText") or ""),
    "limits": limits.get("limits") or [],
  }
  record.update(stats)
  return record


def main() -> int:
  parser = argparse.ArgumentParser(description="Print and store the SuperGrok usage record.")
  parser.add_argument("--force", action="store_true", help="rescan local sessions instead of using the cache")
  parser.add_argument("--print", dest="print_only", action="store_true", help="print the record without writing it")
  args = parser.parse_args()

  limits = probe_limits()
  record = build_record(local_stats(args.force), limits)
  output = json.dumps(record, indent=2)
  if args.print_only:
    print(output)
    return 0
  try:
    write_json(usage_record_path(), record)
  except OSError as exc:
    print(f"collect-grok: could not write {usage_record_path()} ({exc})", file=sys.stderr)
    print(output)
    return 1
  print(output)
  return 2 if limits.get("unreachable") else 0


if __name__ == "__main__":
  raise SystemExit(main())
