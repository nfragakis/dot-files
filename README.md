# Dot files

Setting this up on a new machine: read [AGENTS.md](AGENTS.md) first. It covers
what is linked and what merely resembles what is installed, the setup order,
and the steps no script can do — Evolution account consent, calendar dashboard
config, whisper model weights. [PACKAGES.md](PACKAGES.md) lists what has to be
installed before any of it works.

## Omarchy

The Omarchy configuration and locally developed shell plugins are kept in this
repository. Install them into the active user configuration with:

```bash
./install-omarchy.sh
```

The installer links these paths into `~/.config/omarchy`:

- `shell.json`
- `shell.toml`
- every plugin directory under `omarchy/plugins/`

It also installs the third-party plugins that `shell.json` places but this
repository does not carry, cloning each with `omarchy plugin add` when it is
absent. Currently that is the Todoist widget,
`io.github.aryan-techie.todoist`, from
<https://github.com/aryan-techie/omarchy-todoist>. Its API token is entered in
the widget's own Settings view, not kept here.

It is safe to run repeatedly. A conflicting file, directory, or link is moved
to `~/.local/state/dot-files/backups/omarchy/<timestamp>` before the repo path
is linked. Other user plugins and Omarchy configuration are left in place.

### Coding-agent workspace marks

The workspace widget can show a green dot when a Codex or Claude Code turn is
complete and an amber dot when an agent needs approval or other input. The
existing red Hyprland urgency dot remains unchanged. Install the machine-local
agent hooks after installing the Omarchy plugin:

```bash
./install-agent-attention.py
```

The installer adds hook entries alongside (and does not replace) existing
Codex and Claude Code hooks. It backs up both settings files under
`~/.local/state/dot-files/backups/agent-attention/`. Codex requires one final
interactive step: open `/hooks` and trust the newly added hooks. Visiting or
clicking a workspace clears its agent mark; submitting the next prompt clears
the corresponding session as well.

## Keyboard

Install the repo-managed Hyprland input settings and the system-wide `keyd`
configuration with:

```bash
./install-input.sh
```

This maps Caps Lock to Escape when tapped and Super/Meta when held. The
installer backs up the live Hyprland input file before replacing it.

## Tern remote trial

`tern/settings.json` preserves the existing tmux-style preset, Ctrl+S prefix,
Alt pane navigation, host switching, and herdr dashboard shortcuts. The trial
adds Ctrl+h/j/k/l through `tern/plugins/nvim-nav`. `tern/plugins/hostkeys`
preserves the existing custom commands. On the laptop, `nvim-nav` is linked
to this repo and `hostkeys` remains a copied installation. On `fwdesktop`,
both plugins are linked to `~/dot-files`. Settings and Neovim files remain
installed copies, not symlinks.

The trial initially opened `commercialize-app` on `fw-dev` in
`~/Work/commercialize/wt-onboarding`, with work, agent, and log-viewer tabs.
That was an initial layout, not a requirement: keep the user's current
checkout, tabs, editor, and agent rather than recreating the trial layout.
The trial did not start another app server or Supabase instance.

| Action | Keys |
| --- | --- |
| Go to fw-dev | Ctrl+S, Shift+D |
| Toggle local / fw-dev | Ctrl+S, Tab |
| Choose commercialize-app | Ctrl+S, S; select the session |
| Navigate Neovim splits, then adjacent Tern panes at the edge | Ctrl+h/j/k/l |
| Always navigate outer Tern panes using the existing behavior | Alt+h/j/k/l |
| Previous / next tab | Alt+Left / Alt+Right |
| Open the existing remote herdr dashboard | Ctrl+S, A |
| Previous / next named session, across hosts | Ctrl+S, Ctrl+K / Ctrl+J |
| Copy / paste through Omarchy's universal shortcuts | Super+C / Super+V, with Tern tagged as a terminal |

Omarchy's packaged terminal-class matcher does not include `so.stencil.tern`.
The user-only rule in `hypr/hyprland.lua` adds `terminal`, so the existing
universal clipboard bindings send Ctrl+Insert / Shift+Insert instead of
Ctrl+C / Ctrl+V. Install that rule in the live user config too; this file is
not symlinked. Do not edit packaged Omarchy defaults or bind away terminal
Ctrl+C. Direct Tern alternatives are Ctrl+Shift+C / Ctrl+Shift+V.

Ctrl navigation does not wrap at tiled-layout boundaries. In Neovim it
works in normal, insert, and terminal modes. Floating/PiP panes retain the
existing Alt controls. The bridge uses OSC title events over the remote
connection; only the currently focused pane may request edge navigation.
Do not replace the `nvim [tern-nav]` editor-title marker in a Tern session.

Neovim loads `config.tern_navigation` from `lua/config/keymaps.lua`; setup
is gated on TERM_PROGRAM=tern, TERN_PANE, and the absence of TMUX. Ordinary
Neovim/tmux use outside Tern is unchanged. Keep the established Ghostty +
tmux/herdr workflow as the independent fallback rather than nesting it to
evaluate native Tern navigation.

The laptop checkout is `~/Work/personal/dot-files`; `fwdesktop` uses
`~/dot-files`. Pulling the repo updates linked plugin code:

```bash
git -C ~/dot-files pull --ff-only
tern plugin link ~/dot-files/tern/plugins/hostkeys
tern plugin link ~/dot-files/tern/plugins/nvim-nav
```

For a new installation, merge the snapshot's custom keybinds into the live
Tern settings rather than overwriting machine-specific appearance options.
The desktop keeps its Dark/dark-copper theme, copy-on-select, and scroll
preferences. Future settings changes still need this merge; Git does not
update the live settings copy automatically.

Copy `nvim/lua/config/tern_navigation.lua` into the live Neovim configuration,
and add `require("config.tern_navigation").setup()` to its keymaps entrypoint.
For remote editing, install those Neovim pieces on the dev host too. Start
a new Neovim process, and reload Tern's config/plugins in the target window
or reopen the window. Host registrations, private keys, and account state
are deliberately not stored here. The desktop's existing `fw-dev` alias
uses `nfragakis@fw-dev.taildd43c0.ts.net`.

Keep both clients and the dev-host service on the same Tern release.
The trial aligned all three to 0.6.3 with `tern remote update fw-dev`;
the remote daemon's handoff preserved the running editor and agent.

### Tailscale access and shared-session status

`tern/access.toml` is the dev-host policy: only the Tailscale login
`nafragakis@gmail.com` may act as `nfragakis`. The live copy is
`~/.config/tern/access.toml` on `fw-dev`. Its user service explicitly passes
`--access /home/nfragakis/.config/tern/access.toml`; without that flag,
user mode still uses its built-in SSH-key policy. No SSH keys or tailnet ACLs
were changed. A fresh desktop client with no SSH agent authenticated with
method `tailscale`; the laptop reconnected with the same identity.

**Cross-machine persistence works; arbitrary-window discovery is not accepted.**
A disposable native remote session created by a headless laptop client was
visible to a fresh headless desktop client, with the same session and pane
IDs. It remained accessible on the desktop after laptop disconnection, and
the laptop reattached to those same IDs. The probe was then removed.
`tern-remote.service` is enabled and the dev user's linger is enabled.
This proves two clients can share a remote session, not that every GUI window
automatically joins the same catalog.

In 0.6.3, a fresh GUI window can lack sessions another window shows. Merging
saved catalogs did not fix this. No supported window-key rebinding control
was found in the installed settings or public plugin APIs. `--window`
selects a CLI command's window; it is not a proven GUI sharing fix.
`share_sessions` controls permission to serve sessions, not the catalog
selected by a remote client. Use named sessions/tabs within one established
workspace rather than additional windows, and explicitly disconnect the
remote host before closing its window. That avoids the demonstrated risky
path but is not a guarantee for unverified GUI attachments.

The pre-merge layouts and original listener unit are backed up on `fw-dev`
under `~/.local/state/tern-trial/backups/20261008-namespace-merge/`.
Restoring saved layout metadata cannot restore a program that has exited.

The trial verified native remote navigation, normal/insert/terminal modes,
non-wrapping boundaries, background-focus protection, and a real
disconnect/reconnect of the trial window's remote link. Neovim, omp, and
the log viewer retained their PIDs; an unsaved Neovim scratch buffer survived.
This was not a Wi-Fi outage or machine-reboot test. Do not generalize that
proof to closing arbitrary windows: on 0.6.3, closing one of several windows
produced `window closed for good` and ended its seven remote panes.
Use explicit host disconnection for the proven detach path; closing a pane
or session is destructive. Normal window closing is not accepted as safe.

Backups from setup are under `~/.local/state/tern-trial/backups/20261008`
on the local machine and `fw-dev`; the desktop's installation backup is
`~/.local/state/tern-trial/backups/20261008T223643.218884523Z`.
To undo the bridge, restore the backed-up
Tern settings and Neovim keymaps on their respective machines, unlink
`nvim-nav` with `tern plugin unlink nvim-nav`, and restart Neovim/reload Tern.
The original hostkeys, tmux, and herdr configurations were not changed.
