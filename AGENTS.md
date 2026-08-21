# Working in this repository

Personal configuration for an Omarchy 4 / Hyprland desktop. Read this before
setting it up on a machine, and before assuming a file here is the one in use.

## What is actually installed, and what is not

Only `omarchy/` has an installer. `./install-omarchy.sh` symlinks the plugin
directories, `shell.json` and `shell.toml` into `~/.config/omarchy`, backing up
whatever it replaces under `~/.local/state/dot-files/backups/omarchy/`.

**Everything else was copied by hand and is not linked.** `ghostty/`, `hypr/`,
`nvim/`, `opencode/`, `wiremix/`, `zed/`, `tmux.conf` and `pipewire/` are
ordinary directories that happen to resemble what is in `~/.config`. Nothing
keeps them in step.

Two consequences, both of which have already happened:

- **Editing a file here changes nothing on a running machine.** The live copy
  is the one under `~/.config`. Check which you are looking at before
  concluding a change had no effect.
- **Local edits are invisible to git and are lost on a clean install.** At the
  time of writing, `~/.config/nvim` carried three files that were never
  committed. Before rebuilding a machine, diff the live tree against this one
  and rescue what only exists there:

```bash
diff -rq nvim ~/.config/nvim
```

Do not "fix" this by copying `~/.config` over the repo wholesale — that drags
in caches, backups and `node_modules`. Copy the specific files that matter.

## Setting up a new machine

Roughly in order. Nothing here is automated beyond step 2, deliberately.

1. **Packages.** `PACKAGES.md` lists what has to exist and why, with a check
   loop at the end. Run that first; several later steps fail in confusing ways
   rather than obvious ones when something is absent.
2. **Omarchy config.** `./install-omarchy.sh`. Safe to re-run.
3. **Everything else.** Copy the directories in by hand, or link them — see
   the warning above about which you have chosen.
4. **The steps no script can do.** Below.

## Steps that need a person

A script cannot do these. They are the difference between a machine that looks
configured and one that works.

- **Evolution accounts.** Omamail and the calendar dashboard both get their
  Google tokens from Evolution Data Server. Account definitions under
  `~/.config/evolution/sources/` copy between machines cleanly, but the refresh
  tokens do not — they are in the login keyring, which a non-interactive ssh
  session cannot reach. Each account needs one browser consent, in Evolution's
  GUI, on the target machine. Full detail, including the traps, is in
  `omarchy/plugins/omamail/docs/EVOLUTION.md`. Read it before touching mail
  setup rather than after.
- **Calendar dashboard config.** `~/.config/omarchy/calendar-dashboard.json`
  does not exist until it is created. `omarchy/plugins/nfragakis.clock/sync/`
  has the setup script and `AUTH.md`.
- **Whisper dictation.** A `whisper.cpp` checkout, a local build, and model
  weights, none of which are in this repository. See `whisper-stt/README.md`.

## Traps

- **`shell.json` will stop being a symlink.** `omarchy-shell` saves it by
  writing a temporary file and renaming it over the target, and a rename
  replaces a symlink rather than writing through it. So any bar setting changed
  in the UI silently detaches the repo copy, and edits here stop taking effect.
  Re-run `./install-omarchy.sh` after changing bar settings. If a change to
  `omarchy/shell.json` appears to do nothing, check with `ls -l
  ~/.config/omarchy/shell.json` before debugging anything else. Tools that own
  their own config are likely to behave the same way; `zed/` and `opencode/`
  are the candidates.
- **`hypr/monitors.lua` is machine-specific** and will differ on every machine.
  That difference is correct. Do not reconcile it.
- **Symlinked plugins mean the repo is live.** `~/.config/omarchy/plugins/*`
  point into this checkout, so editing a plugin here changes the running
  desktop immediately, and a `git checkout` can change the desktop under you.
- **Omamail's plugin directory is a vendored upstream checkout** with local
  changes on top. It has its own `AGENTS.md`, its own tests, and a `make
  validate` gate. Follow those rather than this file when working inside it,
  and run `make validate` before committing anything there.

## Removed on purpose

- `hypr/shaders/` was 89 tracked symlinks into `/usr/share/aether/shaders/`, a
  path owned by no package and absent on the machine they were committed from.
  All 89 were broken. If shader files are wanted, vendor the real ones.
- `waybar/` was configuration for a bar this desktop does not run — Omarchy
  uses `omarchy.bar`. It also referenced a script that was never committed.

Neither was deleted from `~/.config`, only from this repository.
