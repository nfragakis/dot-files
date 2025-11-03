return {
  -- Multi-cursor editing like VS Code
  {
    "mg979/vim-visual-multi",
    event = "VeryLazy",
    init = function()
      vim.g.VM_maps = {
        ["Find Under"] = "<C-n>", -- Start/add cursor on word
        ["Find Subword Under"] = "<C-n>",
        ["Add Cursor Down"] = "<C-Down>",
        ["Add Cursor Up"] = "<C-Up>",
        ["Select All"] = "<Leader>a", -- Select all occurrences
        ["Visual All"] = "<Leader>a", -- In visual mode, select all in selection
        ["Visual Cursors"] = "<Leader>m", -- Create cursor on each visual line
      }
    end,
  },
}
