return {
  dir = vim.fn.stdpath("config") .. "/lua/custom/personal-os",
  name = "personal-os",
  lazy = false,
  dependencies = {
    "nvim-lua/plenary.nvim",
    "nvim-telescope/telescope.nvim",
    "obsidian-nvim/obsidian.nvim",
  },
  config = function()
    require("custom.personal-os").setup()
  end,
}
