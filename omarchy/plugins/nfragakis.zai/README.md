# Z.AI Coding Plan Usage

This headless Omarchy service adds the Z.AI Coding Plan to the generic agents
panel. It writes `~/.local/state/omarchy/agents/usage/zai.json`; no panel fork
or packaged Omarchy change is involved.

## Data and credentials

`collect-zai.py` runs `omp usage --json --provider zai --redact`. OMP owns the
Coding Plan credential and Z.AI's private quota adapter, so this plugin never
reads, stores, or logs the API key. The returned 5-hour and weekly windows are
normalized into the panel's fraction-and-reset format. A window with no
usage fraction makes the record unavailable instead of displaying a false
zero. A measured window that omits its reset is still shown; the countdown
is left blank.

Z.AI does not document the monitor endpoint as a public API. Its own usage
plugin and web console use it, but the schema may change. Keeping that boundary
behind OMP limits this plugin to one stable command interface.

Local token charts come from assistant messages under `~/.omp/agent/sessions`
and `~/.pi/agent/sessions` whose provider is exactly `zai`. The scan is cached
for 15 minutes; quota limits are refreshed every 12 minutes.

## Files

| Path | Purpose |
|---|---|
| `~/.local/state/omarchy/agents/usage/zai.json` | record watched by the panel |
| `~/.cache/omarchy/agent-usage/zai.json` | cached local transcript totals |

## Checking it

```bash
~/.config/omarchy/plugins/nfragakis.zai/collect-zai.py --print
~/.config/omarchy/plugins/nfragakis.zai/collect-zai.py --force
omarchy-shell omarchy.agents open
```

If the record says Z.AI is not signed in, add the Z.AI Coding Plan key in OMP
and confirm it with `omp usage --provider zai`.
