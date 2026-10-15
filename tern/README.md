# Default terminal

The repository's root `xdg-terminals.list` selects Tern, with Ghostty as a
fallback. Tern must be installed with its `so.stencil.tern.desktop` entry.

From the repository root, install the preference on each machine:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}"
cp --backup=numbered xdg-terminals.list "${XDG_CONFIG_HOME:-$HOME/.config}/xdg-terminals.list"
xdg-terminal-exec --print-id
```

The expected selected entry is `so.stencil.tern.desktop`. Omarchy's existing
Super+Enter binding launches `omarchy launch terminal`, which uses
`xdg-terminal-exec`; no separate keybinding override or restart is needed.
This file is copied manually, not installed by `install-omarchy.sh`.

## Omarchy integration

Run `./install-tern-clipboard.py --client` from the repository root on each
Omarchy desktop. It clones `Moti-Velz/tern-forge` into `~/src/forge` if absent,
links the `omarchy` Tern plugin, and installs the repo's Hyprland adapter.
Existing upstream checkouts are left at their current revision.

The adapter loads upstream's pane-aware Super bindings and preserves the
personal Super+Shift+P Screenshot fallback outside Tern. It supersedes the
old terminal-tag clipboard rule: Super+C/V now send Ctrl+Shift+C/V to Tern.
Agent notifications are included; Forge Projects and agent-desktop are optional
and are not installed. Super+B requires the separate Forge Projects plugin.

Keep both repositories in place. After pulling dotfiles, rerun the installer;
it preserves unrelated bindings and backs up conflicts. Validate on a running
desktop with `tern plugin list --json`, `hyprctl reload`, and
`hyprctl configerrors`.
