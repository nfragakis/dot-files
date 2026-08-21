# Evolution Data Server accounts

How a Gmail mailbox in this checkout gets its OAuth token from Evolution Data
Server instead of from a Google Cloud client you made yourself, why that needed
a patch to the setup page, and what still bites.

Written after wiring three Gmail accounts onto a fresh machine.

## What the integration actually covers

`scripts/evolution-token.py` asks EDS for a live access token for one address.
It matches an enabled source whose `[Authentication]` block has `Method=Google`
and a `User=` equal to the address, preferring one that also carries a mail
account, then calls `get_oauth2_access_token_sync`. Evolution owns the refresh
token and refreshes it through its own verified client; nothing here reads or
stores that refresh token.

`AuthManager.startBrokerLookup()` is the only caller. On success it sets
`systemBrokerAvailable`, which `MailAccount.setupState` reads as
`credentialsPresent`, and the account is ready with no client ID anywhere.

The scope EDS hands out is `https://mail.google.com/`. That covers the Gmail
REST API this plugin calls, not only IMAP — verified against
`users/me/profile`, which returns HTTP 200.

## The chicken-and-egg, and how the setup page escapes it

Fixed here — this section is why the fix exists, and what to preserve if the
setup page is ever rewritten against upstream.

`startBrokerLookup()` returns early unless `accountId` is non-empty:

```qml
if (systemBrokerSuppressed || accountId === "" || pluginDir === "") {
  startStoredSession(purpose)   // no stored credentials -> asks for a client ID
  return
}
```

For Gmail, `accountId` is the address, and `account/Accounts.js` says where the
address comes from:

> The address arrives with the first successful sign-in for Gmail, and is typed
> by hand for IMAP, so an account exists for a while with no id at all.

So a new Gmail row has no address until a Google sign-in supplies one — and
that sign-in is what needs the client ID the broker was meant to replace.
Upstream's setup page has no Evolution branch and no address field, so the
account sits at "Connect your mailbox" asking for a client ID while a perfectly
good EDS grant goes unused.

**The cycle breaks by handing the row an address from outside the sign-in.**
That is all it takes: `accountId` is derived from the address, and an account
with an id is one `AuthManager` will ask Evolution about.

`SetupPage.qml` now does that itself. `scripts/evolution-accounts.py` lists the
Google addresses EDS holds a grant for, `Evolution.parseAccounts()` decodes it,
`Service.unusedEvolutionAccounts()` subtracts the ones already added, and the
page offers what is left above the Cloud walkthrough. Clicking one calls
`configureCurrentAccount({ email })` — a function that already existed for
exactly this, addressing the row by index *because* it has no address yet — and
sign-in happens without anybody pressing sign in.

The list is probed when the page opens rather than watched, so an account added
in Evolution mid-session appears on reopening the page.

### Seeding by hand

Still worth knowing: it is the fallback when the panel will not open, and it is
how several accounts get added at once. `Accounts.load()` recomputes `id` from
`email` rather than trusting the file, and its comments anticipate hand-editing.
Only `email` and `provider` are load-bearing.

## The running shell overwrites the file

`Service.qml` watches `accounts.json` with `watchChanges: true`, so a write is
picked up without a restart. But the shell also *writes* that file from its
in-memory model, and clicking **Add a mailbox** creates an empty pending row
(`{"id":"","email":"", ...}`) and saves it — wiping a hand-seeded file.

- Write the file, then open the panel. Do not click Add a mailbox afterwards.
- Do not try to stop the shell first. `omarchy-launch-shell` respawns
  `quickshell` immediately, so `pkill` gains nothing and briefly kills the bar.
  Writing against the live shell is fine; the UI is what clobbers, not the
  watcher.
- After writing, confirm it held before touching the panel:

```bash
python3 -c "import json;d=json.load(open('$HOME/.config/omamail/accounts.json'));print([a['id'] for a in d['accounts']], d['activeId'])"
```

## Seeding accounts.json

`~/.config/omamail/accounts.json`, mode 0600, **one line** — `config-store.sh`
reads it with `read -r`, so an embedded newline truncates the account list.

```json
{"version":1,"accounts":[{"id":"you@gmail.com","email":"you@gmail.com","provider":"gmail","clientId":"","clientSecret":"","imap":{"imapHost":"","imapPort":993,"smtpHost":"","smtpPort":465,"username":"","insecure":false},"label":"","inboxQuery":""}],"activeId":"you@gmail.com"}
```

Leave `clientId` and `clientSecret` empty — that is the point. `version` must
be `1` or `load()` discards the whole file and returns an empty list.

### Workspace accounts need an inboxQuery override

A bar-wide `defaultQuery` of `in:inbox category:primary` shows an empty inbox on
a Workspace account with no category tabs. Set that account's `inboxQuery` to
`in:inbox`; per-account values win over the widget default.

## The OAuth-only stub source

An address you want in Omamail but *not* as a full Evolution mail account needs
only a bare source — no mail account, no transport, no identity. Drop this at
`~/.config/evolution/sources/omamail-google-<name>.source`, mode 0600:

```ini
[Data Source]
DisplayName=Omamail OAuth — you@gmail.com
Enabled=true
Parent=

[Authentication]
Host=
Method=Google
Port=0
ProxyUid=system-proxy
RememberPassword=true
User=you@gmail.com
CredentialName=
IsExternal=false
```

Caveat: nothing will ever trigger its authentication on its own, because no
mail account hangs off it to attempt a connection. Authorize it by adding the
address in Evolution once, or by calling `e_source_invoke_authenticate_sync()`
on the UID. There is no standalone credentials prompter on Arch — Evolution's
GUI *is* the prompter and must be running for the consent flow to appear.

## Moving accounts between machines

Source definitions under `~/.config/evolution/sources/` are plain config and
copy cleanly. Keep the UIDs: children reference the collection by UID
(`Parent=`, `TransportUid=`, `IdentityUid=`), so renaming breaks the set. Check
for collisions first, and confirm the only outside references — usually
`system-proxy` and `folder://local/...` — exist on the target. Restart with
`systemctl --user restart evolution-source-registry`.

**The refresh tokens do not travel.** They live in the login keyring, which a
`BatchMode` ssh session cannot reach: no session D-Bus, keyring locked, so
`secret-tool lookup` returns nothing. Copy the sources, then authorize once per
account in Evolution on the target machine. Plan for the browser step rather
than trying to route around it.

## Verifying

```bash
# EDS brokers a token for this address
/usr/bin/python3 scripts/evolution-token.py you@gmail.com

# ...and that token reaches the Gmail REST API
TOK=$(/usr/bin/python3 scripts/evolution-token.py you@gmail.com | python3 -c 'import json,sys;print(json.load(sys.stdin)["accessToken"])')
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOK" \
  https://gmail.googleapis.com/gmail/v1/users/me/profile
```

`OAuth2 secret not found` means the source exists but has never been
authorized — config present, grant absent. Authorize it in Evolution.

The shebang is `#!/usr/bin/python3` deliberately. A mise- or venv-managed
`python3` on `PATH` has no `gi` module; the absolute path dodges it. Do not
"fix" it to `env python3`.

## The fallback is a trap that looks like a regression

With `clientId` empty, a broker failure — revoked grant, EDS not running —
falls through `startStoredSession()`, finds no stored credentials, and drops
you back to the client-ID page. That means *re-authorize in Evolution*, not
*go make a Google Cloud project*.
