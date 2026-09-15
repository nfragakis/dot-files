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
