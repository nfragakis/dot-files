-- Omarchy's universal Super+V sends Shift+Insert to terminal-tagged windows.
-- Tern must handle paste locally so remote panes receive the client clipboard.
o.window("so\\.stencil\\.tern", { tag = "+terminal" })
