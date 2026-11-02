# Tern Diff

A native, read-only diff workbench for Tern. File rail, full-width focus mode, fuzzy file preview, Vim navigation, native split/unified syntax and word highlighting, and persistent viewed marks.

## Install and open

Requirements on the repository host: **Tern, Python 3.10+, Git**. GitHub comparisons also require **GitHub CLI (`gh`) authenticated on that host**. No Python packages or Node build step.

Use the latest Tern release; this project follows the current [official SDK](https://github.com/stencil-hq/tern-sdk). Tern updates are managed separately from the plugin.

The canonical source is `tern/plugins/diff/` in the personal **dot-files** repository. Install from the same repository on **FW Dev, fwdesktop, and the laptop**. The host runs the block; each desktop runs its own palette commands and keyboard bindings.

From the dot-files repository root on FW Dev:

```sh
python3 install-tern-diff.py --host
```

From the dot-files repository root on fwdesktop and the laptop:

```sh
python3 install-tern-diff.py
```

The installer links the package and writes the explicit user binding **Ctrl+Shift+D → `plugin.diff.open`**. It preserves other settings, follows an existing settings-file symlink, saves an existing settings file as `settings.json.before-tern-diff`, and refuses a concurrent preferences edit. Re-running it leaves an already-correct keymap unchanged.
Restart the Tern window after installation to load the user keymap; reloading plugins alone does not guarantee a preferences reload.

**Shortcut tradeoff:** this chord replaces Tern's existing editor “add next occurrence,” Markdown “duplicate block,” and “split right” bindings. A plugin default cannot override those built-ins, so a plain `tern.bind` would be silently left out with a log warning. Other pane/editor bindings and native Git are untouched.

Open the command palette and choose **Open diff viewer**, or **Open pull request diff…**. The manifest also registers the **Diff** block. Search the palette for **Diff**; do not depend on a particular “New block” menu label, which can differ between Tern versions. A block inherits its originating pane's directory.

For subsequent updates, run these commands from each machine's dot-files checkout:

```sh
git pull --ff-only
python3 install-tern-diff.py
```

Use `--host` on FW Dev to leave its keyboard settings unchanged. Keep each checkout in place: Tern's `.path` link points at that machine's checkout, so Git updates change the installed code directly. Restart the desktop Tern window after the first installation or a shortcut change. `tern plugin reload` reloads plugin-code updates.

The FW Dev host link points to `/home/nfragakis/Work/personal/dot-files/tern/plugins/diff`. The old standalone source directory has been removed. Running the installer on a client replaces an older Diff link with the repo-managed path; an old copied folder such as `~/.local/share/tern-diff` is no longer used. The installer does not update Tern itself.

## Compare sources

Press **s** or click **Compare**:

- **Working tree:** HEAD versus local files, including staged, unstaged and untracked changes.
- **Unstaged:** index versus working tree, including untracked files.
- **Staged:** HEAD versus index.
- **Branch:** merge base of base/head versus head. Select or type a base, then a head (defaults to HEAD). An empty base searches upstream/default/main/master/trunk candidates. Enter arbitrary valid refs even when they are outside the suggestion limit.
- **Commit:** first parent versus the selected commit. Root commits compare against the empty tree. Type a SHA or ref, or select a recent commit.
- **GitHub pull request:** select a recent open PR, enter a number, `owner/repo#123`, or paste a full PR URL. URLs do not require a local clone. Numbers and the open-PR list require a repository with a GitHub remote.

Comparisons are **snapshots**. **r** refreshes local content or resolves current PR/ref tips again. Failed refreshes retain the previous comparison with an explicit stale warning; viewed actions are disabled until a successful refresh. Refresh retries the failed source rather than silently switching back.

PR results pin the merge base and head. File details are reconstructed from full, hash-verified GitHub blobs, not GitHub's potentially truncated patch field. No checkout, fetch, review submission or PR mutation occurs.

## Navigation

| Keys | Action |
|---|---|
| `j` / `k`, arrows | Move through files when the rail has focus; move one logical diff row when the reader has focus |
| `Tab`, `Enter` | Switch rail/reader focus; Enter focuses the reader |
| `gg` / `G`, Home / End | First / last file or diff row |
| Ctrl D / U | Half-page down / up |
| Page Down / Up | Next / previous rendered page |
| `]f` / `[f` | Next / previous file |
| `]c` / `[c` | Next / previous hunk |
| Ctrl P or `f` | Fuzzy file picker with a bounded diff preview |
| `/`, `n` / `N` | Literal smartcase search within the active file; next / previous matching row |
| `z` | Full-width focus mode |
| `d` | Cycle auto, split, unified |
| `v` | Toggle viewed for the selected file snapshot |
| `s` | Choose source |
| `r`, Ctrl R | Refresh |
| `?` | Help |
| Esc | Dismiss picker/help, clear active search, or return focus to files |
| `q` | Close the viewer outside a picker |

Tern's primary-modifier events are accepted alongside Control for the named Control shortcuts. Ctrl/Alt H/J/K/L are not claimed.

In a picker, **letters type text**; Ctrl N/P or arrows move selection, Enter accepts, Esc cancels without changing the active file or its position. Suggestions do not prevent typing a revision or PR URL. An explicitly moved selection wins over typed text on Enter. Input edits use Tern's UTF-16 offsets without splitting UTF-8 codepoints.

File positions are kept separately for split and unified layouts. Auto uses split only when the reader has enough width; narrow panes hide the rail and retain the file picker. The reader renders a bounded number of logical rows rather than mounting an entire large patch; its footer states the visible range. Use row/page/hunk keys or the pointer buttons to move through the file. Search includes both deleted and added lines and uses ASCII smartcase; it is not a regex engine.

## Viewed state

Viewed marks live in **Tern plugin KV storage**, not `.git` or the worktree. They are namespaced by comparison identity and paired with the file fingerprint. Refresh invalidates a mark when content, mode or rename identity changes. Marks survive plugin reloads. Loading, failed and truncated diffs cannot be marked viewed. Binary and metadata-only changes can be acknowledged explicitly.

For local files above 8 MiB, the backend uses filesystem metadata rather than reading the entire content to compute a fingerprint. This is an explicit performance limit; exact content hashing is used below that threshold. PR fingerprints use the pinned GitHub file data. Files for which GitHub supplies no patch also include the base revision, so a rebase invalidates those marks conservatively.

## Safety and limits

- Repository access is read-only. Local comparisons use a temporary copy of the index and a temporary object directory; the original index, refs and worktree are not changed.
- External diff, textconv, configured clean/smudge filters, fsmonitor and hooks are disabled. Consequently, filtered/LFS worktree content is compared without executing repository-supplied conversion programs.
- Untracked symlinks are not followed. NUL-separated paths and literal pathspecs preserve unusual names; non-UTF-8 paths retain an opaque base64 identity and show an explicit decoding notice.
- Binary files, pure renames, mode changes, empty files, unborn HEAD and root commits have explicit states.
- Patches above **4 MiB** are refused with a visible notice, not silently clipped. Combined/incomplete hunks are not presented as complete reviews.
- File lists cap at **10,000**. GitHub's PR-files API caps at **3,000**; incomplete lists are labelled. GitHub blobs cap at **32 MiB**. Ref suggestions cap at **200 branches / 100 commits**; PR suggestions at **50**.
- Detail caching is bounded by file count and patch bytes. Async requests carry a comparison generation, so a late response cannot replace a newer source.
- No staging, discard, editing, notes, agent handoff or PR review actions.

## Development and verification

Run these checks from `tern/plugins/diff/`:

```sh
python3 -m unittest discover -s tests -v
lua tests/test_model.lua
lua tests/test_input.lua
tern plugin reload
```

`backend.py` is a standalone JSON CLI: `python3 backend.py list|detail|refs|pulls`, with a JSON request on stdin and one JSON result on stdout. Errors return `{ "error": "…" }` and a nonzero exit code. `detail` receives the entire opaque `comparison` and `file` returned by `list`.

Modules:

- `host.luau`: async comparison lifecycle, shortcuts, source/file/search dialogs and persisted state.
- `view.luau`, `diff.css`: native renderer and narrowly scoped layout/theme styling.
- `model.luau`: pure patch parsing, fuzzy ranking, search and split/unified viewport mapping.
- `input.luau`: controlled Unicode input editing.
- `window.luau`: palette entry points only; Git never runs on the window/UI thread.
- `backend.py`: local Git and GitHub reads.
- `../../../install-tern-diff.py`: repository-root installer; host-only mode or desktop shortcut setup, with settings preservation and backup.

Verification includes 23 backend tests against real temporary repositories and a controlled GitHub adapter, 18 pure model tests, and Unicode input boundary tests. The native application was also launched in an isolated X display: file/hunk/row navigation, picker typing, search, split/unified/focus layouts, narrow panes, mouse viewed toggling, persistence after reload and invalidation after a real file edit were exercised. A live comparison against `stencil-hq/tern-sdk#106` loaded and rendered full pinned PR content. No screenshot/mock renderer substitutes for the native UI smoke.

Installer verification exercised a real isolated Tern window: after restarting, Ctrl+Shift+D opened a Diff tab and the action catalog contained `New Diff block`, `Open diff viewer`, and `Open pull request diff…`. The smoke also checked an unrelated key binding, settings symlink, original backup, and repeat-install idempotence. This does not imply installation on a separate desktop client.

Design references: [SDK block lifecycle](https://docs.stencil.so/tern/guides/blocks.html), [native diff element](https://docs.stencil.so/tern/elements/text.html#diff), [view state and events](https://docs.stencil.so/tern/guides/views.html), [theme variables](https://docs.stencil.so/tern/styles/variables.html). Interaction ideas draw from Lazygit, GitHub's viewed-file workflow and Zed's file switching; no code from those applications is embedded.
