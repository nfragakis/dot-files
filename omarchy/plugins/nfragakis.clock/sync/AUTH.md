# Direct provider authentication

The default machine-local configuration uses Evolution Data Server, because it
can show the calendars already connected on an Omarchy desktop. Direct provider
accounts can be added without changing the QML or its data contract.

## Install direct-provider dependencies

```bash
~/.config/omarchy/plugins/nfragakis.clock/sync/setup --direct-deps
```

This creates a virtual environment under
`~/.local/share/nfragakis-calendar-dashboard/venv`. Nothing is installed into the
dot-files checkout or the system Python.

## Google Calendar

Create a Google Cloud Desktop OAuth client with the Calendar API enabled, then
download its client JSON. Authenticate each Google identity separately:

```bash
calendar-dashboard-auth google \
  --account personal \
  --client-secrets ~/Downloads/google-client.json
```

Add the printed provider object to
`~/.config/omarchy/calendar-dashboard.json`. The token file is stored with mode
0600 under `~/.local/share/nfragakis-calendar-dashboard/auth/`.

## Microsoft / Outlook

Register a public client in Microsoft Entra, enable desktop/mobile public-client
flows, and grant delegated `Calendars.Read`. Then authenticate:

```bash
calendar-dashboard-auth microsoft \
  --account work \
  --client-id YOUR_CLIENT_ID \
  --tenant organizations
```

The command uses browser-based MSAL authentication with PKCE, serializes the
MSAL cache with mode 0600, and prints the provider object to add to the local
configuration.
