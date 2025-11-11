-- Options are automatically loaded before lazy.nvim startup
-- Default options that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/options.lua
-- Add any additional options here
vim.opt.relativenumber = false

-- Default keycode timeout so <Esc> remains responsive
vim.opt.timeout = true
vim.opt.ttimeoutlen = 100

-- Ghostty can be slow to answer the DA1 (Device Attributes) probe that Neovim
-- runs on startup, which shows up in ~/.local/state/nvim/log as
-- `tui_stop` / `timed out waiting for DA1 response` and ultimately kills the
-- TUI. When we detect Ghostty (directly or inside tmux) let the handshake wait
-- longer, disable terminal sync, and hint that the connection is fast.
local term_program = (vim.env.TERM_PROGRAM or ""):lower()
local term_name = (vim.env.TERM or ""):lower()
if term_program == "ghostty" or term_name == "ghostty" or term_name == "xterm-ghostty" then
  vim.opt.ttimeoutlen = 750
  vim.opt.termsync = false
  vim.opt.ttyfast = true
end
