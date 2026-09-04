# Packages

What has to exist on a machine before the configuration in this repository
does anything. Nothing here installs them — this is the list to check against,
and the reason each one is on it.

Package names are Arch's, verified with `pacman -Qoq $(command -v <tool>)`
rather than guessed.

## Assumed

Omarchy 4 and Hyprland. Everything under `omarchy/` and `hypr/` is
configuration *for* them, not a way to get them.

Omarchy already ships `socat`, `openssl`, `curl`, `xdg-utils` and `libsecret`.
They are listed under Omamail below because that plugin is what fails without
them, not because they normally need installing.

## Omamail and the calendar dashboard

Both plugins get their Google tokens from Evolution Data Server, so EDS is a
hard requirement for mail and for calendar events.

| Package | Why |
| --- | --- |
| `evolution` | The account wizard, and the OAuth consent prompt. There is no standalone credentials prompter — Evolution's GUI *is* the prompter, so it must be installed even if never used for reading mail. |
| `evolution-data-server` | Holds the Google grant and refreshes it. |
| `python-gobject` | `evolution-token.py` and `evolution-accounts.py` import `gi`. |
| `libsecret` | `secret-tool`, where IMAP passwords live. |
| `socat`, `openssl`, `xdg-utils` | The direct Google sign-in, only needed for an account EDS does not know. |
| `curl` | Every IMAP mailbox, and the Gmail API transport. |

**`python-gobject` installs into the system Python.** `gi` is therefore
importable from `/usr/bin/python3` and *not* from a mise- or venv-managed
`python3`. Both scripts pin `#!/usr/bin/python3` for that reason. See
`omarchy/plugins/omamail/docs/EVOLUTION.md`.

## Calendar dashboard, direct providers only

| Package | Why |
| --- | --- |
| `uv` | `omarchy/plugins/nfragakis.clock/sync/setup --direct-deps` refuses without it. |

Only needed for Google or Microsoft accounts added directly. The default path
reads the calendars EDS already has and needs nothing here.

## Terminal, editors, shell

| Package | Config in this repo |
| --- | --- |
| `ghostty` | `ghostty/` |
| `neovim` | `nvim/` |
| `tmux` | `tmux.conf` |
| `mise` | runtime versions |
| `zed` | `zed/` |
| `wiremix` | `wiremix/` |

## Keyboard

| Package | Why |
| --- | --- |
| `keyd` | Makes Caps Lock a dual-role key: Escape when tapped and Super/Meta when held. |

## Whisper dictation

`omarchy/plugins/nfragakis.whisper/` needs a `whisper.cpp` checkout, a local
build, and model weights, none of which are in this repository. Its README has
the setup steps. The runtime path uses only Python's standard library.

| Package | Why |
| --- | --- |
| `pipewire-audio` | Provides `pw-record` for microphone capture. |
| `python` | Runs the local transcription and clipboard pipeline. |
| `wl-clipboard` | Provides `wl-copy` for the transcript. |
| `wtype` | Pastes the transcript into the focused Wayland application. |

## Checking a machine

```bash
for p in evolution evolution-data-server python-gobject libsecret socat \
         openssl curl xdg-utils uv ghostty neovim tmux mise zed wiremix keyd \
         pipewire-audio python wl-clipboard wtype; do
  pacman -Qq "$p" >/dev/null 2>&1 || echo "missing: $p"
done
```
