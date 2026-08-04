return {
  "pablopunk/pi.nvim",
  config = function()
    require("pi").setup({
      provider = "openai-codex",
      model = "gpt-5.3-codex",
    })

    vim.keymap.set("n", "<leader>P", ":PiAsk<CR>", { desc = "Ask pi" })
    vim.keymap.set("v", "<leader>P", ":PiAskSelection<CR>", { desc = "Ask pi (selection)" })
  end,
}
