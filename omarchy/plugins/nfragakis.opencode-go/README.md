# OpenCode Go Usage

The Omarchy agents panel on this machine shows one subscription Omarchy does
not ship: **OpenCode Go**. This plugin is the whole of it — a headless service
that writes one usage record, and the collector that produces it.

```
collect-opencode-go.py   fetch limits, scan local sessions, write the record
Service.qml              run the collector on a timer while the shell is up
manifest.json            a `service` kind plugin; no UI of its own
```

## Why this is not an omarchy collector

Omarchy's own collectors live in `/usr/share/omarchy/bin/omarchy-agent-usage-*`
and are run by `omarchy-agent-usage-update`. That directory belongs to the
omarchy package, and the update command globs collectors only from there — so
a local collector cannot be added there without being deleted by the next
`omarchy update`.

The panel does not care. It watches `~/.local/state/omarchy/agents/usage/`
and draws every record it finds, whoever wrote it. This plugin writes one,
on its own timer, and the panel picks it up the moment the file changes.

## Data

**Limits** — `GET https://opencode.ai/zen/go/v1/usage`, the same first-party
route the omp harness polls, with the `x-opencode-session` header Go requires
(omp's install id, or an id of this plugin's own). The endpoint reports three
windows: the rolling 5-hour session, the weekly window, and the monthly
allowance, each as a percentage and a reset timestamp. The panel renders
percentages as fractions, so the collector divides by 100 on the way in.

**Local token history** — the pi/omp session transcripts under
`~/.omp/agent/sessions` and `~/.pi/agent/sessions` whose messages ran on an
`opencode-go` model. That is where a Go subscription's traffic lands here,
because this machine's omp model roles point at Go models. The scan is cached
for 15 minutes in `~/.cache/omarchy/agent-usage/opencode-go.json`; only the
limits call is made on every run.

**Credential** — the first key the endpoint accepts, from:

1. `$OPENCODE_GO_API_KEY`, then `$OPENCODE_API_KEY`
2. omp's credential store, `~/.omp/agent/agent.db` (`opencode-go` row)
3. `~/.local/share/opencode/auth.json`, providers `opencode-go` then `opencode`

Without a key the record still carries local stats, and the panel says which
step was missing instead of showing a stale meter.

## Files

| Path | What it is |
|---|---|
| `~/.local/state/omarchy/agents/usage/opencode-go.json` | the record the panel reads |
| `~/.cache/omarchy/agent-usage/opencode-go.json` | cached local scan |
| `~/.local/state/omarchy/agents/opencode-go-session-id` | session header id, when omp is absent |

## Configuring

`Service.qml` polls every 12 minutes (`intervalSeconds`) and retries a failed
run after a minute (`retrySeconds`), at most `maxRetries` times in a row before
waiting for the next interval. Go's windows refill on a 5-hour, weekly, and
monthly cadence, so a tighter interval buys nothing; edit the property in this
repository if a different cadence is wanted. The plugin is enabled by its
entry in `omarchy/shell.json`; saving either file reloads it.

The collector's exit code is the whole retry contract: `0` the record is
current, `2` the record was written but the endpoint was unreachable or
answered with an incomplete set of windows, `1` the record could not be
written (the record is printed to stdout instead). The panel's own
`retryAdvised` field is deliberately not set — it re-runs
`omarchy-agent-usage-update`, which has no collector for this agent and could
never refresh this file.

A response that decodes to fewer than three windows is treated as a failure
rather than written out, so a transient upstream shape change cannot replace a
complete set of meters with a shorter one. The record and the stats cache are
written `0600`, atomically, like the records Omarchy's own collectors leave in
the same directory.

## Checking it by hand

```bash
~/.config/omarchy/plugins/nfragakis.opencode-go/collect-opencode-go.py --print   # record, no file write
~/.config/omarchy/plugins/nfragakis.opencode-go/collect-opencode-go.py --force   # rescan sessions, write the record
omarchy-shell omarchy.agents open
```
