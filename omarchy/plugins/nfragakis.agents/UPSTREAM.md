# Upstream

Cloned from Omarchy's first-party `omarchy.agents` panel so the provider
strip can scroll. The packaged copy under `/usr/share/omarchy` is not edited.

- Source: `/usr/share/omarchy/shell/plugins/agents`
- Cloned: 2026-09-21

`omarchy.clonedFrom` stays `omarchy.agents`, so `omarchy.agents` IPC still
reaches this copy. The provider switch in `Panel.qml` uses
a horizontal `ListView` sized to each label, with
`positionViewAtIndex(..., ListView.Contain)` when the selection moves.

`Main.qml` invokes the local `update-usage.sh` using the packaged updater's
flags and JSON record contract. `collect-native.py` loads the installed Claude
and Codex collectors, replacing `oauth_login` and `rpc_request` respectively.
These local fixes renew an expired Claude token through its CLI and prevent
Codex notifications from hiding buffered RPC replies. The installed collector
functions are an upstream dependency; review these two seams after an Omarchy
update. The remaining providers use their packaged collectors.
