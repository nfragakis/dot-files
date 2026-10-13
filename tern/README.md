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
