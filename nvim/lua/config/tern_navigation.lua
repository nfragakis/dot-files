local M = {}

function M.setup()
  -- Tern variables can be inherited by nested tmux; do not change that workflow.
  if vim.env.TERM_PROGRAM ~= "tern" or not vim.env.TERN_PANE or vim.env.TMUX then
    return
  end

  local prefix = "nvim [tern-nav] "
  local sequence = 0
  local function title()
    local name = vim.fn.fnamemodify(vim.api.nvim_buf_get_name(0), ":t")
    return prefix .. (name ~= "" and name or "[No Name]")
  end
  local function set_title(value)
    -- Strip control characters so filenames cannot inject terminal escapes.
    vim.api.nvim_chan_send(vim.v.stderr, "\27]2;" .. value:gsub("[%c]", "") .. "\7")
  end

  -- Publish an editor marker for routing; the shell restores its title on exit.
  vim.opt.title = false
  local group = vim.api.nvim_create_augroup("TernNavigation", { clear = true })
  vim.api.nvim_create_autocmd({ "BufEnter", "VimEnter", "VimResume" }, {
    group = group,
    callback = function()
      set_title(title())
    end,
  })
  vim.api.nvim_create_autocmd({ "VimLeavePre", "VimSuspend" }, {
    group = group,
    callback = function()
      set_title("shell")
    end,
  })
  set_title(title())

  for _, key in ipairs({ "h", "j", "k", "l" }) do
    vim.keymap.set({ "n", "i", "t" }, "<C-" .. key .. ">", function()
      if vim.fn.winnr(key) ~= vim.fn.winnr() then
        vim.cmd("wincmd " .. key)
      else
        sequence = sequence + 1
        set_title("nvim [tern-nav-request] " .. key .. ":" .. sequence)
        -- Events are ordered; restore the editor marker without leaving stale requests.
        set_title(title())
      end
    end, { desc = "Navigate Neovim or Tern " .. key, silent = true })
  end
end

return M
