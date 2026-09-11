# Upstream

This plugin was cloned from Omarchy's first-party `omarchy.clock` plugin.

- Omarchy package version: `4.0.0-1`
- Upstream plugin version: `1.0.0`
- Source path: `/usr/share/omarchy/shell/plugins/panels/clock`
- Cloned: 2026-08-17
- Resynced `Panel.qml` `setCenterHoverRevealSuppressed` with 4.0.3-1 on 2026-09-11: the bar API made `centerHoverRevealSuppressed` read-only and added a `setCenterHoverRevealSuppressed()` setter; assigning the property threw and aborted `close()`.

The manifest keeps `omarchy.clonedFrom: omarchy.clock`, so built-in clock IPC
continues to route to this user-owned implementation. Keep changes to the three
upstream files (`BarWidget.qml`, `Panel.qml`, and `Model.js`) narrow; new behavior
belongs in separate QML components and the `sync/` package where possible.
