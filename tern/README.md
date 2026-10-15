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

## Agent cockpit

Run `./install-tern-cockpit.py` from this checkout on each machine running
Tern. It links `agent-cockpit` and `hostkeys`, merges the `Ctrl+S`, then `A`
binding, and adds Claude Code and Codex `SessionStart` hooks. Codex's
`features.hooks` is enabled without rewriting the rest of its TOML.
Existing settings, unrelated hooks, and conflicting plugin installations
are preserved or backed up under
`~/.local/state/dot-files/backups/tern-cockpit/`. Custom `TERN_CONFIG_DIR`,
`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and XDG paths are respected.

The cockpit is a transient, centered model sheet—not a session tab:

- Sessions on the left, a structured session brief on the right.
- All detected sessions in one continuous list, without hidden pagination.
  The larger sheet adapts to the window; a persistent scroll rail and native
  draggable thumb make overflow discoverable.
- Original omp, Claude Code, and Codex marks; native graphite colors, soft
  state pills, and a centered soft-focus entrance that respects reduced motion.
- `j` / `k` or arrow keys select; `Enter` opens the exact pane, switching
  session or connected host as needed. `Escape` returns to the original
  screen. `Home` / `End`, `gg` / `G`, and Page Up / Page Down also navigate.
- No top header/counts and no raw terminal preview.

Discovery covers this window's connected sessions and hosts, including
parked and exited agent panes. The brief shows available model, branch,
session identity, recorded usage, current activity, latest request, and
last response. Missing observations stay explicitly unknown.

### Metadata boundaries

omp lifecycle state comes from Tern's native agent API. Local metadata is
read from the exact running process and its own session records, never
from the newest transcript in a shared working directory. The collector
uses bounded reads and runs outside the window's Lua callbacks.

Restart Claude Code and Codex after installing their hooks; existing
pre-hook sessions cannot be retroactively attributed safely. Hook records
must match the pane, daemon socket, process ID, and process start time.
An unprompted session may have an identity but no transcript or model yet.
Recorded metadata is not proof that a provider is currently working or idle.

Codex's shared app-server cannot currently prove which TUI owns a session;
those records are deliberately rejected. Exact-pane Codex metadata was
verified with `codex --no-daemon` and an approved SessionStart hook. The
installer does not bypass provider hook trust or change how Codex launches.
Remote hosts retain Tern's native observations; local transcript enrichment
does not read remote transcript files.

After pulling updates, rerun the installer. Use **Reload plugins** in an
already-open Tern window if it retains the previous styling.
`tern plugin list --json` checks the host catalog; opening the cockpit checks
the window half too. Regression checks:

```bash
python3 -m unittest discover -s tests -p 'test_tern_cockpit*.py'
lua tests/test_tern_cockpit_selection.lua
```

`cockpit-design-lab.html` is the offline component comparison used to select
S1 / P1 / I1 / L2 / D1 / T2 / F1 / M1. Publisher marks are embedded in
`plugins/agent-cockpit/branding.css`: [omp](https://omp.sh/favicon.svg),
[Claude Code](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code),
and [Codex](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt).
