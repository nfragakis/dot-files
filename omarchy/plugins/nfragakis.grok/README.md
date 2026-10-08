# SuperGrok Usage

This headless Omarchy service adds SuperGrok to the generic agents panel. It
writes `~/.local/state/omarchy/agents/usage/xai-oauth.json`; no panel fork or
packaged Omarchy change is involved.

## Data and credentials

`collect-grok.py` runs `omp usage --json --provider xai-oauth --redact`. OMP
owns the SuperGrok OAuth credential, token refresh, and the billing adapter,
so this plugin never reads, stores, or logs the access token. Limits OMP
decodes are copied as a fraction and a reset time. A limit OMP did not return
is omitted. OMP itself may infer 0% when xAI omits `creditUsagePercent`; a
lone weekly window at exactly 0% is therefore marked unreported instead of
drawn as a measured empty meter. A 0% that arrives with any other window is
shown as measured.

Local token charts come from assistant messages under `~/.omp/agent/sessions`
and `~/.pi/agent/sessions` whose provider is exactly `xai-oauth`. The scan is
cached for 15 minutes; quota limits are refreshed every 12 minutes.

## Files

| Path | Purpose |
|---|---|
| `~/.local/state/omarchy/agents/usage/xai-oauth.json` | record watched by the panel |
| `~/.cache/omarchy/agent-usage/xai-oauth.json` | cached local transcript totals |

## Checking it

```bash
~/.config/omarchy/plugins/nfragakis.grok/collect-grok.py --print
~/.config/omarchy/plugins/nfragakis.grok/collect-grok.py --force
omarchy-shell omarchy.agents open
```

If the record says SuperGrok is not signed in, run `/login xai-oauth` in OMP
and confirm it with `omp usage --provider xai-oauth`.
