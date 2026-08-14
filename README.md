# Dot files

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

It is safe to run repeatedly. A conflicting file, directory, or link is moved
to `~/.local/state/dot-files/backups/omarchy/<timestamp>` before the repo path
is linked. Other user plugins and Omarchy configuration are left in place.
