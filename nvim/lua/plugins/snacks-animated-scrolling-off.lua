return {
  "folke/snacks.nvim",
  opts = {
    scroll = {
      enabled = false, -- Disable scrolling animations
    },
    picker = {
      sources = {
        files = {
          hidden = true,  -- Show hidden/dotfiles
          ignored = true, -- Show gitignored files
        },
      },
    },
  },
}
