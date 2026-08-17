# Calendar Dashboard

A personal clone of Omarchy's first-party clock. It keeps the stock bar and
month calendar, then adds a selected-day view with calendar events, direct
meeting links, and a compact Todoist list.

## Data sources

The UI reads `~/.local/state/omarchy/calendar-dashboard.json`. The bundled sync
service can combine:

- Google Calendar API accounts
- Microsoft Graph / Outlook accounts
- Evolution Data Server as an optional local adapter
- Todoist tasks due within the configured future window, plus overdue tasks

The default Todoist query follows `window.futureDays`, so selecting a future
calendar day shows tasks due on that day. Today continues to include overdue
tasks. The dashboard owns this date window so a stale or narrower
`todoist.filter` cannot make selected days incomplete.

The provider layer is independent of the QML. Evolution is useful as a working
fallback on this machine, but it is not required by the plugin.

## Install

From the dot-files repository:

```bash
./install-omarchy.sh
~/.config/omarchy/plugins/nfragakis.clock/sync/setup
```

The setup command creates a machine-local configuration when one does not
exist, installs a user systemd timer, and runs an initial sync. Credentials,
tokens, provider configuration, and generated state are never stored in this
repository.

See `sync/config.example.json` and `sync/AUTH.md` to add direct Google or
Microsoft accounts.
