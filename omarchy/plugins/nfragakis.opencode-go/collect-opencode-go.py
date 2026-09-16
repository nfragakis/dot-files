#!/usr/bin/python3
"""Collect OpenCode Go usage into one display-ready JSON record.

Limits are authoritative: they come from OpenCode's own Go endpoint,
`GET https://opencode.ai/zen/go/v1/usage`, the first-party route the omp
harness polls. Local token history comes from the pi/omp session transcripts
on disk that ran on an `opencode-go` model.

The record is written to
`~/.local/state/omarchy/agents/usage/opencode-go.json`. The Omarchy agents
panel draws whatever records appear in that directory, whoever wrote them,
so the directory — not this script — is the interface between the two.

This cannot live in `$OMARCHY_PATH/bin/omarchy-agent-usage-*`: that directory
belongs to the omarchy package and `omarchy-agent-usage-update` only globs
collectors from there. A `service` plugin runs it instead; see README.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterator

AGENT_ID = "opencode-go"
AGENT_NAME = "OpenCode Go"
TIER_LABEL = "Go · $10/month"
USAGE_ENDPOINT = "https://opencode.ai/zen/go/v1/usage"
# Identifies this client to the gateway, which asks Go traffic to carry its own
# user agent rather than a generic HTTP-library one.
USER_AGENT = "omarchy-agents-opencode-go/1.0"
AUTH_HELP = "Sign in: `omp` login, or `opencode providers` → OpenCode Go."

# Every window the endpoint reports, in the order the panel should show them.
# The rolling and weekly windows carry fixed spans; the monthly window anchors
# on the subscription anniversary, which is why the panel labels it bare.
WINDOWS = (
  ("rolling", "Session (5-hour)"),
  ("weekly", "Weekly (7-day)"),
  ("monthly", "Monthly"),
)

REQUEST_TIMEOUT_SECONDS = 20
# Local stats are a walk over session transcripts, not a network call: a
# scan this recent is reused so the service's timer cannot turn into a
# treadmill of disk scans. The limits are always fresh.
LOCAL_SCAN_REUSE_SECONDS = 900


def expand_path(value: str) -> Path:
  return Path(os.path.expandvars(os.path.expanduser(value)))


def state_root() -> Path:
  return Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))


def cache_root() -> Path:
  return Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")) / "omarchy" / "agent-usage"


def usage_record_path() -> Path:
  return state_root() / "omarchy" / "agents" / "usage" / f"{AGENT_ID}.json"


def stats_cache_path() -> Path:
  return cache_root() / f"{AGENT_ID}.json"


def data_root() -> Path:
  return Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))


# --------------------------------------------------------------- credentials


def credential_strings(raw: Any) -> list[str]:
  """API keys out of one credential blob.

  omp writes `{"key": "...", "source": "login"}` today; earlier shapes used
  apiKey or a bare string. Read defensively rather than pinning a private
  format that may move.
  """
  try:
    parsed = json.loads(raw)
  except Exception:
    parsed = None
  if isinstance(parsed, str):
    parsed = {"key": parsed}
  if not isinstance(parsed, dict):
    return []
  for field in ("key", "apiKey", "api_key", "token", "access_token"):
    value = parsed.get(field)
    if isinstance(value, str) and value.strip():
      return [value]
  return []


def omp_credentials() -> list[tuple[str, str]]:
  db = expand_path("~/.omp/agent/agent.db")
  if not db.is_file():
    return []
  try:
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
  except sqlite3.Error:
    return []
  try:
    conn.execute("PRAGMA query_only = ON")
    rows = list(conn.execute("SELECT data FROM auth_credentials WHERE provider = ?", (AGENT_ID,)))
  except sqlite3.Error:
    return []
  finally:
    conn.close()
  found = []
  for (raw,) in rows:
    for key in credential_strings(raw):
      found.append((f"omp credential store ({db})", key))
  return found


def opencode_credentials() -> list[tuple[str, str]]:
  """Keys opencode itself is signed in with.

  The Go subscription is the `opencode-go` provider; a key connected through
  the Zen console lands under `opencode`. Both are candidates, most specific
  first.
  """
  path = data_root() / "opencode" / "auth.json"
  try:
    parsed = json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return []
  found = []
  for provider in (AGENT_ID, "opencode"):
    entry = parsed.get(provider) if isinstance(parsed, dict) else None
    if not isinstance(entry, dict):
      continue
    for field in ("key", "accessToken", "apiKey"):
      value = entry.get(field)
      if isinstance(value, str) and value.strip():
        found.append((f"opencode auth.json ({provider})", value))
        break
  return found


def candidate_keys() -> list[tuple[str, str]]:
  """Every place the Go key may live, most authoritative first."""
  found: list[tuple[str, str]] = []
  seen: set[str] = set()

  def add(source: str, value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in seen:
      seen.add(text)
      found.append((source, text))

  for name in ("OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"):
    add(name, os.environ.get(name))
  try:
    for source, value in omp_credentials():
      add(source, value)
  except Exception as exc:
    print(f"collect-opencode-go: omp credential lookup failed ({exc})", file=sys.stderr)
  try:
    for source, value in opencode_credentials():
      add(source, value)
  except Exception as exc:
    print(f"collect-opencode-go: opencode credential lookup failed ({exc})", file=sys.stderr)
  return found


def session_id() -> str:
  """Stable value for the `x-opencode-session` header Go requires.

  omp sends its own install id; a machine that has never run omp gets an id of
  its own, persisted so background polls stay attributable across runs.
  """
  install = expand_path("~/.omp/install-id")
  try:
    value = install.read_text(encoding="utf-8").strip()
    if value:
      return value
  except OSError:
    pass

  path = state_root() / "omarchy" / "agents" / f"{AGENT_ID}-session-id"
  try:
    value = path.read_text(encoding="utf-8").strip()
    if value:
      return value
  except OSError:
    pass

  value = str(uuid.uuid4())
  try:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    path.chmod(0o600)
  except OSError:
    pass
  return value


# -------------------------------------------------------------------- limits


def decode_limits(payload: Any) -> list[dict[str, Any]]:
  """The endpoint's windows as panel limits.

  Per window, `percent` is a floored, clamped integer 0-100 and `resetsAt` an
  ISO timestamp. The panel speaks fractions, so every window is normalized
  here; a window that is missing or malformed is skipped rather than allowed
  to fail the record.
  """
  usage = payload.get("usage") if isinstance(payload, dict) else None
  if not isinstance(usage, dict):
    return []
  limits = []
  for key, label in WINDOWS:
    window = usage.get(key)
    if not isinstance(window, dict):
      continue
    percent = window.get("percent")
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
      continue
    if not math.isfinite(percent) or not 0 <= percent <= 100:
      continue
    resets_at = window.get("resetsAt")
    limits.append({
      "label": label,
      "percent": round(float(percent) / 100.0, 4),
      "resetsAt": resets_at if isinstance(resets_at, str) else "",
    })
  return limits


def probe_limits() -> dict[str, Any]:
  """Ask the Go endpoint, trying each credential until one is accepted."""
  keys = candidate_keys()
  if not keys:
    return {
      "limits": [],
      "ready": False,
      "usageStatusText": "OpenCode Go is not signed in.",
      "authHelpText": AUTH_HELP,
    }

  rejected = []
  unreachable = ""
  for source, key in keys:
    request = urllib.request.Request(USAGE_ENDPOINT, headers={
      "accept": "application/json",
      "authorization": f"Bearer {key}",
      "user-agent": USER_AGENT,
      "x-opencode-session": session_id(),
    })
    try:
      with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
      if exc.code in (401, 403):
        rejected.append(f"{source} (HTTP {exc.code})")
        continue
      unreachable = f"HTTP {exc.code}"
      break
    except Exception as exc:
      unreachable = str(exc)
      break

    limits = decode_limits(payload)
    if not limits:
      return {
        "limits": [],
        "ready": False,
        "unreachable": True,
        "usageStatusText": "OpenCode's usage endpoint returned no limits.",
        "authHelpText": "Local OpenCode Go token history is still shown.",
      }
    # All or nothing. A partial response would replace a complete record with
    # one carrying fewer meters and no hint that anything is missing, so it is
    # treated like a failure and the next run gets another try. The same rule
    # upstream applies before letting a report replace its last-good cache.
    if len(limits) != len(WINDOWS):
      return {
        "limits": [],
        "ready": False,
        "unreachable": True,
        "usageStatusText": "OpenCode Go returned an incomplete set of usage windows.",
        "authHelpText": f"Decoded {len(limits)} of {len(WINDOWS)} windows from {USAGE_ENDPOINT}.",
      }
    return {"limits": limits, "ready": True, "usageStatusText": "", "authHelpText": ""}

  if unreachable:
    # The record still lands with the local stats and a reason; the *exit
    # code* is what asks for a sooner retry (see main), because the panel's
    # own `retryAdvised` machinery re-runs omarchy-agent-usage-update, which
    # has no collector for this agent and could never refresh this file.
    return {
      "limits": [],
      "ready": False,
      "unreachable": True,
      "usageStatusText": "OpenCode Go limits unavailable.",
      "authHelpText": f"Could not reach {USAGE_ENDPOINT}: {unreachable}",
    }
  return {
    "limits": [],
    "ready": False,
    "usageStatusText": "OpenCode Go key was rejected.",
    "authHelpText": AUTH_HELP + " Rejected: " + ", ".join(rejected),
  }


# --------------------------------------------------------------- local stats


def number(value: Any) -> int:
  try:
    return int(value or 0)
  except Exception:
    return 0


def local_day(value: Any) -> str:
  if value is None:
    return dt.datetime.now().strftime("%Y-%m-%d")
  if isinstance(value, (int, float)):
    # pi message timestamps are milliseconds.
    if value > 10_000_000_000:
      value = value / 1000
    return dt.datetime.fromtimestamp(value).strftime("%Y-%m-%d")
  text = str(value)
  try:
    parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    if parsed.tzinfo is not None:
      parsed = parsed.astimezone()
    return parsed.strftime("%Y-%m-%d")
  except Exception:
    return dt.datetime.now().strftime("%Y-%m-%d")


def session_roots() -> list[Path]:
  return [
    Path.home() / ".pi" / "agent" / "sessions",
    Path.home() / ".omp" / "agent" / "sessions",
  ]


class Stats:
  """Local usage rolling up the same fields the other collectors report."""

  def __init__(self) -> None:
    now = dt.datetime.now()
    self.today = now.strftime("%Y-%m-%d")
    self.recent_dates = [(now - dt.timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(6, -1, -1)]
    self.recent = {day: {"date": day, "messageCount": 0} for day in self.recent_dates}
    self.model_usage: dict[str, dict[str, int]] = {}
    self.today_tokens_by_model: dict[str, int] = {}
    self.today_sessions: set[str] = set()
    self.active_days: set[str] = set()
    self.seen_lines: set[str] = set()
    self.today_prompts = 0
    self.today_total_tokens = 0
    self.total_prompts = 0
    self.total_sessions: set[str] = set()

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
      "recentDays": [self.recent[day] for day in self.recent_dates],
      "totalPrompts": self.total_prompts,
      "totalSessions": len(self.total_sessions),
      "activeDays": len(self.active_days),
      "activeDates": sorted(self.active_days),
      "modelUsage": self.model_usage,
    }


def scan_sessions() -> dict[str, Any]:
  """Token history from the pi/omp transcripts that ran on opencode-go.

  omp's default model roles point at `opencode-go` models, so most of a Go
  subscription's traffic lands here. Reading the files directly beats shelling
  out to rg: the corpus is transcript text, and the substring gate below skips
  every line that cannot be one of ours before any JSON is parsed.
  """
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
          if '"opencode-go"' not in raw or not raw.lstrip().startswith("{"):
            continue
          try:
            entry = json.loads(raw)
          except Exception:
            continue
          if not isinstance(entry, dict) or entry.get("type") != "message":
            continue
          message = entry.get("message")
          if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
          provider = str(message.get("provider") or "")
          api = str(message.get("api") or "")
          if provider != AGENT_ID and not api.startswith(AGENT_ID):
            continue
          usage = message.get("usage")
          if not isinstance(usage, dict):
            continue
          # omp writes totalTokens = input + output + cacheRead + cacheWrite;
          # reasoningTokens is informational and already inside output, so
          # adding it here would count thinking twice.
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
          model = str(message.get("model") or AGENT_ID)
          stats.add(local_day(entry.get("timestamp") or message.get("timestamp")), str(path), model, tokens)

  return stats.record(bool(roots))


# --------------------------------------------------------------------- cache


def read_cached_stats(max_age_seconds: int, today: str) -> dict[str, Any] | None:
  try:
    cached = json.loads(stats_cache_path().read_text(encoding="utf-8"))
  except Exception:
    return None
  if not isinstance(cached, dict) or cached.get("schemaVersion") != 1:
    return None
  # today* fields only mean "today" on the day they were scanned.
  if cached.get("scanDate") != today:
    return None
  scanned_at = cached.get("scannedAt")
  if not isinstance(scanned_at, (int, float)) or not math.isfinite(scanned_at):
    return None
  if max_age_seconds >= 0 and (dt.datetime.now().timestamp() - scanned_at) > max_age_seconds:
    return None
  stats = cached.get("stats")
  if not isinstance(stats, dict):
    return None
  if not all(key in stats for key in ("todayPrompts", "todayTotalTokens", "recentDays", "activeDates", "modelUsage")):
    return None
  return stats


def write_json(path: Path, payload: Any) -> None:
  """Write atomically, 0600.

  Every other record in the usage directory is user-only, and these numbers
  describe an account's allowance rather than the machine's. The temporary
  file carries the mode so the rename cannot widen it.
  """
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
  descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
  with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, separators=(",", ":")) + "\n")
  os.chmod(tmp, 0o600)
  os.replace(tmp, path)


def local_stats(force: bool) -> dict[str, Any]:
  """Local stats, with the cache as a pure optimization.

  A cache-layer failure (unwritable cache root, disk full) degrades to a
  direct scan and a warning on stderr: the usage record is the contract,
  the cache is not.
  """
  today = dt.datetime.now().strftime("%Y-%m-%d")
  if not force:
    try:
      cached = read_cached_stats(LOCAL_SCAN_REUSE_SECONDS, today)
      if cached is not None:
        return cached
    except Exception as exc:
      print(f"collect-opencode-go: cache unavailable ({exc}); scanning directly", file=sys.stderr)

  stats = scan_sessions()
  try:
    write_json(stats_cache_path(), {
      "schemaVersion": 1,
      "scanDate": today,
      "scannedAt": dt.datetime.now().timestamp(),
      "stats": stats,
    })
  except Exception as exc:
    print(f"collect-opencode-go: could not write usage cache ({exc})", file=sys.stderr)
  return stats


# ---------------------------------------------------------------------- main


def build_record(stats: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
  record: dict[str, Any] = {
    "schemaVersion": 1,
    "id": AGENT_ID,
    "name": AGENT_NAME,
    "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    "ready": bool(limits.get("ready")),
    "tierLabel": TIER_LABEL,
    "usageStatusText": str(limits.get("usageStatusText") or ""),
    "authHelpText": str(limits.get("authHelpText") or ""),
    "limits": limits.get("limits") or [],
  }
  record.update(stats)
  return record


def main() -> int:
  parser = argparse.ArgumentParser(description="Print and store the OpenCode Go usage record.")
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
    print(f"collect-opencode-go: could not write {usage_record_path()} ({exc})", file=sys.stderr)
    print(output)
    return 1
  print(output)
  # The record is written either way; the exit code only tells the service
  # whether asking again sooner than the next interval is worth it.
  return 2 if limits.get("unreachable") else 0


if __name__ == "__main__":
  sys.exit(main())
