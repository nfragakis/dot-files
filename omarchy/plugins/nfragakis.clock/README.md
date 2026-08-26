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

The default Todoist query follows `window.futureDays`. A selected calendar day
acts as a cutoff: its list includes every incomplete task due on or before that
day and excludes anything due later. The dashboard owns this date window so a
stale or narrower `todoist.filter` cannot make selected days incomplete.

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

## Move an existing setup to another machine

The default provider configuration is portable and is tracked as
`sync/config.example.json`. The setup script installs that file when the local
configuration does not exist. To reuse an existing machine's provider choices
instead, copy its machine-local configuration before running setup:

```bash
mkdir -p ~/.config/omarchy
scp user@old-machine:.config/omarchy/calendar-dashboard.json \
  ~/.config/omarchy/calendar-dashboard.json
chmod 600 ~/.config/omarchy/calendar-dashboard.json
```

Todoist's API token is a credential and must remain outside this repository.
Transfer it directly between machines, then restrict its permissions:

```bash
mkdir -p ~/.config/todoist
scp user@old-machine:.config/todoist/api_key ~/.config/todoist/api_key
chmod 600 ~/.config/todoist/api_key
```

Finish by installing the timer and performing the initial sync:

```bash
~/.config/omarchy/plugins/nfragakis.clock/sync/setup
```

Evolution account definitions can be copied separately, but their Google
refresh tokens live in the login keyring and do not transfer this way. Complete
browser consent in Evolution on the new machine when required.
