-- opencode.nvim - AI assistant integration for NeoVim
-- https://github.com/NickvanDyke/opencode.nvim
return {
  {
    -- Ensure snacks.nvim has required features enabled
    "folke/snacks.nvim",
    opts = {
      input = { enabled = true },
      picker = { enabled = true },
      terminal = { enabled = true },
    },
  },
  {
    "NickvanDyke/opencode.nvim",
    dependencies = {
      "folke/snacks.nvim",
    },
    config = function()
    -- Configuration options
    vim.g.opencode_opts = {
      provider = {
        enabled = "snacks", -- Options: snacks, kitty, wezterm, tmux
      },
    }

    -- Auto-reload buffers when opencode makes changes
    vim.o.autoread = true

    -- Keymaps for opencode
    -- Ask with context (selection or cursor position)
    vim.keymap.set({ "n", "x" }, "<C-a>", function()
      require("opencode").ask("@this: ", { submit = false })
    end, { desc = "Ask opencode with context" })

    -- Quick ask and auto-submit
    vim.keymap.set({ "n", "x" }, "<leader>aa", function()
      require("opencode").ask("@this: ", { submit = true })
    end, { desc = "Ask opencode (auto-submit)" })

    -- Select from available actions/prompts
    vim.keymap.set({ "n", "x" }, "<C-x>", function()
      require("opencode").select()
    end, { desc = "Select opencode action" })

    -- Add context to prompt without asking
    vim.keymap.set({ "n", "x" }, "ga", function()
      require("opencode").prompt("@this")
    end, { desc = "Add to opencode prompt" })

    -- Toggle opencode interface
    vim.keymap.set({ "n", "t" }, "<C-.>", function()
      require("opencode").toggle()
    end, { desc = "Toggle opencode" })

    -- Additional useful keymaps
    -- Review current git diff
    vim.keymap.set("n", "<leader>ar", function()
      require("opencode").ask("@diff: Review these changes", { submit = true })
    end, { desc = "Review git diff" })

    -- Explain selected code
    vim.keymap.set("x", "<leader>ae", function()
      require("opencode").ask("@this: Explain this code", { submit = true })
    end, { desc = "Explain selection" })

    -- Fix diagnostics in current buffer
    vim.keymap.set("n", "<leader>af", function()
      require("opencode").ask("@diagnostics: Fix these errors", { submit = true })
    end, { desc = "Fix diagnostics" })

    -- Generate tests for selection
    vim.keymap.set("x", "<leader>at", function()
      require("opencode").ask("@this: Write tests for this code", { submit = true })
    end, { desc = "Generate tests" })

    -- Document selection
    vim.keymap.set("x", "<leader>ad", function()
      require("opencode").ask("@this: Add documentation comments", { submit = true })
    end, { desc = "Document code" })
  end,
  },
}
