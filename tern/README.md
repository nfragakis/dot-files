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
binding, adds Claude Code lifecycle hooks, and adds Codex's `SessionStart`
identity hook. Codex's `features.hooks` is enabled without rewriting its TOML.
Existing settings, unrelated hooks, and conflicting plugin installations
are preserved or backed up under
`~/.local/state/dot-files/backups/tern-cockpit/`. Custom `TERN_CONFIG_DIR`,
`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and XDG paths are respected.

The cockpit is a transient, centered model sheet—not a session tab:

- Agents grouped by machine and Tern session on the left; group headers are
  nonselectable and keyboard navigation visits agents only.
- All detected sessions in one continuous list, without hidden pagination.
  The larger sheet adapts to the window; native scrollbars appear only when
  the list or details actually overflow.
- The right-hand brief separates current activity or permission waits from
  the latest request and response, with workspace/model context above and
  recorded metadata and attribution below.
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

omp lifecycle state comes from Tern's native agent API. Local Claude lifecycle
state comes from `UserPromptSubmit`, tool start/completion/failure,
`PermissionRequest`, permission/idle notifications, `Stop`, and `SessionEnd`
hooks. A failed tool remains working; it does not mark the session failed.
The activity preview is bounded and sanitized; tool inputs and results are
not persisted in lifecycle records.

Local metadata is read from the exact running process and its own session
records, never from the newest transcript in a shared working directory.
The collector uses bounded reads and runs outside the window's Lua callbacks.

Remote Claude sessions remain visible and navigable, but their live phase
is explicitly unknown. In the tested Tern 0.8.3 window / 0.8.2 remote setup,
host `EffectCx:open()` forwards URLs with the receiving window's focused
pane, not the originating pane. Native smoke testing caught a local Claude
update attributed to an unrelated remote pane. That transport is not used:
there is no exposed safe raw-host-to-window pane-ID mapping to repair it.
Remote enrichment needs a native source-preserving transport or mapping API;
no title/cwd matching, ID arithmetic, SSH polling, or hidden terminal surfaces
are used as substitutes. Hooks still record exact lifecycle state on each
host, and its local window can read those records.

Restart Claude Code and Codex after installing or changing their hooks;
pre-hook sessions cannot be retroactively attributed safely. Hook records
must match the pane, daemon socket, process ID, and process start time.
An unprompted session may have an identity but no transcript or model yet.
Recorded transcript metadata is not proof of live activity. Usage is the
latest provider response record, not a session total or cost estimate.

Codex's shared app-server cannot currently prove which TUI owns a session;
those records are deliberately rejected. Exact-pane Codex metadata was
verified with `codex --no-daemon` and an approved SessionStart hook. The
installer does not bypass provider hook trust or change how Codex launches.
Install the plugin and hooks on every connected Tern host. Disconnected
hosts have unknown activity; native terminal exits
take precedence over recorded lifecycle events. Discovery
covers hosts connected to this window, not arbitrary SSH hosts or detached
sessions outside Tern.

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
