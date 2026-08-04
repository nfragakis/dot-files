return {
  {
    "dnlhc/glance.nvim",
    cmd = "Glance",
    opts = {
      height = 18,
      border = { enable = true },
      theme = { enable = true, mode = "auto" },
    },
  },
  -- Override LazyVim's default LSP keymaps to use Glance.
  -- Keys added to `servers['*'].keys` are appended to LazyVim's defaults
  -- (via `opts_extend`), so these later same-lhs entries take precedence.
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        ["*"] = {
          keys = {
            { "gd", "<cmd>Glance definitions<cr>", desc = "Goto Definition (Glance)", has = "definition" },
            { "gr", "<cmd>Glance references<cr>", desc = "References (Glance)", nowait = true },
            { "gy", "<cmd>Glance type_definitions<cr>", desc = "Goto T[y]pe Definition (Glance)" },
            { "gI", "<cmd>Glance implementations<cr>", desc = "Goto Implementation (Glance)" },
          },
        },
      },
    },
  },
}
