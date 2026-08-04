return {
  "0xKitsune/pr.nvim",
  event = "VeryLazy",
  dependencies = {
    "nvim-telescope/telescope.nvim",
  },
  config = function()
    require("pr").setup()
  end,
}
