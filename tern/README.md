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
(cockpit) and `Ctrl+S`, then `B` (flag tab) bindings, adds Claude Code lifecycle hooks, and adds Codex's `SessionStart`
identity hook. Codex's `features.hooks` is enabled without rewriting its TOML.
Existing settings, unrelated hooks, and conflicting plugin installations
are preserved or backed up under
`~/.local/state/dot-files/backups/tern-cockpit/`. Custom `TERN_CONFIG_DIR`,
`CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and XDG paths are respected.

The cockpit is a transient, centered model sheet—not a session tab:

- The picker shell opens immediately with a loading state and working Close /
  Escape controls. Agent discovery appears first; transcripts, usage, and
  repository details fill in afterward without waiting for every remote host.
  Window work is split across frame-spaced callbacks, with one agent's native
  transcript enrichment per step, rather than spending Tern's entire 50 ms
  callback budget inside the open command. Closing, reopening, changing the
  selection, or invalidating a session discards obsolete queued work.
- Agents grouped by Tern session on the left, with the session name on the
  left of each group header and its machine on the right; group headers are
  nonselectable and keyboard navigation visits agents only. Each card shows
  how long the agent has been in its current phase; agents idle for an hour
  or more are dimmed.
- All detected sessions in one continuous list, without hidden pagination.
  The larger sheet adapts to the window; native scrollbars appear only when
  the list or details actually overflow.
- The right-hand brief is a dashboard: title and phase, session and host,
  a usage strip (context, tokens, cost, subagents), one delivery line
  (branch, changes, ahead/behind, PR, CI), then Now / Asked / Said.
  Host and command facts and the exact provenance of every value are in
  collapsed sections underneath. The context meter appears only when the
  provider reports capacity (Codex); otherwise the token count is shown.
- Original omp, Claude Code, and Codex marks; native graphite colors, soft
  state pills, and a centered soft-focus entrance that respects reduced motion.
- `j` / `k` or arrow keys select and wrap past either end; `Enter` opens the exact pane, switching
  session or connected host as needed. `Escape` returns to the original
  screen. `Home` / `End`, `gg` / `G`, and Page Up / Page Down also navigate.
- No top header/counts and no raw terminal preview.

### Tab flags

Tab colours double as a to-do signal, whether or not the cockpit is open:

- **Red** is yours: `Ctrl+S`, then `B` toggles it on the focused pane's tab
  (or, inside the cockpit, the selected agent's tab). Flagged agents' cards
  get a red wash and a Revisit badge, in place.
- **Yellow** is automatic while any agent in the tab is waiting on you.
- **Green** is automatic when an agent finishes a turn you have not looked
  at; visiting the tab clears it.

Automatic colours only replace a colour the cockpit set itself. A red flag,
or any colour picked from the tab menu, is never overwritten. Claude Code
phases come from its lifecycle hooks; omp from Tern's native agent state.
Codex has no phase source yet (see below), so its tabs only colour yellow
when Tern itself reports an input wait.

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

Remote hosts are read by their own collector. The window runs the remote
host's installed `metadata.py` over ssh (`BatchMode`, one shared
ControlMaster connection per host, the address Tern itself connected to).
A remote pane's window id is `host.id × 2^44 +` the id its programs see as
`TERN_PANE`; this was checked against every live fw-dev agent. The mapping
only names a candidate: the remote collector still requires the pane's
foreground process, its `TERN_PANE`, daemon socket, PID and start time to
match before anything is attributed, exactly as for local panes. Host
`EffectCx:open()` is still not used for metadata, because it forwards with
the receiving window's focused pane. If ssh fails, the plugin is missing, or
the remote copy is older than the window's (a protocol number), the pane
says so instead of showing stale or borrowed data.

omp appends to its transcript without holding it open. Its session is the
one OMP records for the process's own terminal under
`~/.omp/agent/terminal-sessions/pts-N`, trusted only when written during
that process's lifetime, else the process's own `--resume` file. The
context window comes from OMP's own model catalog (`models.db`). Records
over 1 MiB (attachments, tool output) are skipped and disclosed rather than
voiding the session's totals.

Restart Claude Code and Codex after installing or changing their hooks;
pre-hook sessions cannot be retroactively attributed safely. Hook records
must match the pane, daemon socket, process ID, and process start time.
An unprompted session may have an identity but no transcript or model yet.
Recorded transcript metadata is not proof of live activity. Costs are the
provider's own estimates, not billing.

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
lua tests/test_tern_cockpit_view.lua
```

`cockpit-design-lab.html` is the offline component comparison used to select
S1 / P1 / I1 / L2 / D1 / T2 / F1 / M1. Publisher marks are embedded in
`plugins/agent-cockpit/branding.css`: [omp](https://omp.sh/favicon.svg),
[Claude Code](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code),
and [Codex](https://marketplace.visualstudio.com/items?itemName=openai.chatgpt).
