# Tern sessions, catalogs, and CLI cleanup

Verified with Tern **0.7.0 (`9ca00e4`)** on Linux. The installed and running
clients/daemons on `fw13pro` and `fwdesktop`, and the remote service/daemon on
`fw-dev`, were aligned to this version. This is a recorded verification, not
an automatic update policy or a claim that future releases behave identically.

## Required workflow and current limitation

The goal is to open multiple native Tern windows on either client and see the
same persistent `fw-dev` sessions. **That workflow is not yet verified or fixed.**

Tern stores session lists and layouts under window keys, referred to here as
catalogs. The primary catalog's key is the empty string (`''`); additional
catalogs can have keys such as `2` or `3`. A new window reaching the same host
and account can select a different catalog and show only `Default`, while the
original sessions remain alive elsewhere.

An isolated 0.7.0 native-window check reproduced this with no settings file or
plugins: window 1 showed a named session, while window 2, using the same
disposable daemon, showed only `Default`. In-app **New window** also created a
separate catalog in the investigation. Neither launch path is a verified way
to attach another viewer to an existing catalog.

`share_sessions` is **not** a shared-catalog selector. Its installed setting
description says it permits this user's sessions to be served to other machines
and browsers. Turning it off prevents new `tern remote serve --user` and
`tern web serve` processes from starting; it does not control outgoing remote
connections, and an already-running service continues until stopped.

## Inspect before changing anything

Run commands **on the machine that owns the sessions**. For remote work, that
means `fw-dev`, not merely a laptop window currently displaying `fw-dev`.

Inside a Tern terminal, inspect the inherited window key:

```bash
printf 'Catalog key: <%s>\n' "${TERN_WINDOW_KEY-UNSET}"
```

- `<>`: the variable is set to the empty primary key.
- `<2>`: this terminal belongs to catalog `2`.
- `<UNSET>`: the environment does not identify a Tern catalog; do not interpret
  this as proof that the terminal belongs to the primary catalog.

List sessions, tabs, blocks, and their IDs in a selected catalog:

```bash
# Primary catalog. Preserve the quoted empty argument.
tern ls --json --window ''

# Another catalog, if its actual key is 2.
tern ls --json --window 2

# More detail, including live pane and client information.
tern inspect --json --window 2
```

`--window KEY` selects a catalog for a CLI operation. Without it, commands use
`$TERN_WINDOW_KEY` when available, otherwise the first window. These commands
inspect one catalog; `tern ls` is not a verified all-catalog discovery command.
Do not assume the example key `2` still exists or still contains unwanted work.

For this Linux setup, an ordinary SSH shell can explicitly address the remote
daemon when it has not inherited Tern's pane environment:

```bash
ssh fw-dev
export TERN_PANE_SOCKET="/run/user/$(id -u)/tern/daemon.sock"
~/.local/bin/tern ls --json --window ''
```

The socket path above is the runtime-socket convention verified on these
machines, not a portable path for every Tern installation.

## Delete an unwanted session

First inspect the chosen catalog and identify the exact session ID. Then:

```bash
# Replace SESSION_ID with the ID from the preceding inspection.
tern kill session SESSION_ID --window 2
```

**This ends the session's programs. It is not a detach operation.** Never run it
against a working session merely because another window cannot find that session.
Use an ID rather than relying on repeated names such as `Default`.

To close just one block instead, inspect its ID and use:

```bash
# Replace BLOCK_ID with the block ID from the chosen catalog.
tern close BLOCK_ID --window 2
```

This is also destructive to that block's running program. For authoritative
syntax in the currently installed release:

```bash
tern ls --help
tern inspect --help
tern kill --help
tern close --help
```

## Session cleanup is not catalog cleanup

Closing the final session can leave an empty `Default` container. Killing
sessions is therefore **not a verified way to remove the saved window/catalog
record** or prevent that window from reopening.

The investigation did not find a supported CLI operation to:

- delete one saved window catalog independently of its sessions; or
- open another native GUI window attached to an explicitly selected catalog.

`tern --window 2` is not a supported GUI attach command: GUI launch rejected the
flag in the checks. Setting `TERN_WINDOW_KEY` for a new GUI process also did not
make it join the primary catalog. The selector documented for CLI commands must
not be presented as a GUI attachment feature.

The earlier manual catalog merge was not a valid fix. Copying pane references
between layouts did not create a shared catalog and made lifecycle behavior
unsafe. Do not repeat it, edit the binary state file, or delete
`~/.local/state/tern/daemon.state` as a way to clean one catalog. A whole-state
reset affects the host's saved sessions and windows; it requires a separate,
explicitly approved recovery plan outside the Tern processes being stopped.

## Why one launch can reopen many windows

Saved catalogs accumulated during repeated launches and earlier verification
work. A later startup restored multiple saved windows, each with its own remote
connection.

Closing unwanted restored windows through Tern subsequently removed their saved
catalogs in another observation. That cleanup **did not fix shared-session
discovery**.
Do not generalize this into a safe detach workflow: closing a window has also
ended its remote panes during the trial. Preserve windows containing real work
until the relevant lifecycle behavior is established.

## Keep versions aligned

Check both the installed binaries and the actual running GUI, daemon, and remote
service. A new binary on disk does not prove an old process has upgraded.

After updating the clients through Tern's updater, the native remote update path
used successfully for `fw-dev` was:

```bash
tern remote update fw-dev
```

The 0.7.0 update performed an in-place listener/daemon handoff, and both clients
reconnected over Tailscale. Version alignment alone did not resolve the native
multi-window catalog limitation.

## Upstream references and next acceptance check

Related open reports when checked:

- [#6: Relaunch orphans sessions under new window keys](https://github.com/stencil-hq/tern-sdk/issues/6)
- [#9: Relaunch restores multiple unwanted windows and remote connections](https://github.com/stencil-hq/tern-sdk/issues/9)
- [CLI window-selector documentation](https://docs.stencil.so/tern/reference/cli.md)
- [Tern's advertised shared-session model](https://stencil.so/tern)

No new issue or comment was posted from this investigation.

Before declaring the desired workflow fixed, verify a maintainer-supported
attachment mechanism or corrected build against all of these:

1. Multiple native windows on one client see the same remote session IDs.
2. Windows on both `fw13pro` and `fwdesktop` see those same host-side IDs.
3. Changes are visible across attached windows without copying layout metadata.
4. Closing a viewer leaves the intended remote programs running, with their PIDs
   preserved and another viewer still able to use them.
5. Relaunching restores only the intended windows, not accumulated test catalogs.

Keep experiments on isolated configuration, state, and daemon sockets. Do not
create verification catalogs or reset state on the working daemons.
