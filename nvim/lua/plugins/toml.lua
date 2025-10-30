return {
  -- Disable Taplo TOML LSP server
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        taplo = {
          enabled = false,
        },
      },
    },
  },
}
