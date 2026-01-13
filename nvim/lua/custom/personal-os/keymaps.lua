local M = {}
local config = require("custom.personal-os.config")

local function map(mode, lhs, rhs, opts)
  opts = opts or {}
  opts.silent = opts.silent ~= false
  vim.keymap.set(mode, lhs, rhs, opts)
end

function M.setup()
  local wk_ok, wk = pcall(require, "which-key")
  if wk_ok then
    wk.add({
      { "<leader>o", group = "Obsidian/Vault" },
      { "<leader>oc", group = "Clients" },
      { "<leader>og", group = "Goals" },
      { "<leader>t", group = "Todos" },
    })
  end

  map("n", "<leader>od", "<cmd>ObsidianToday<cr>", { desc = "Today's daily note" })
  map("n", "<leader>oy", "<cmd>ObsidianYesterday<cr>", { desc = "Yesterday's note" })
  map("n", "<leader>os", "<cmd>ObsidianSearch<cr>", { desc = "Search vault" })
  map("n", "<leader>oq", "<cmd>ObsidianQuickSwitch<cr>", { desc = "Quick switch note" })
  map("n", "<leader>ob", "<cmd>ObsidianBacklinks<cr>", { desc = "Backlinks" })
  map("n", "<leader>ol", "<cmd>ObsidianLinks<cr>", { desc = "Links in note" })
  map("n", "<leader>oT", "<cmd>ObsidianOpen<cr>", { desc = "Open in Obsidian app" })
  map("n", "<leader>on", "<cmd>ObsidianNew<cr>", { desc = "New note" })

  map("n", "<leader>op", function()
    vim.cmd("edit " .. vim.fn.fnameescape(config.files.priority_queue))
  end, { desc = "Priority Queue" })

  map("n", "<leader>oi", function()
    require("telescope.builtin").find_files({
      cwd = config.paths.inbox,
      prompt_title = "Inbox",
    })
  end, { desc = "Inbox" })

  local goals = require("custom.personal-os.goals")

  map("n", "<leader>og3", goals.open_three_year, { desc = "3-Year Goals" })
  map("n", "<leader>ogy", goals.open_yearly, { desc = "This Year's Goals" })
  map("n", "<leader>ogm", goals.open_monthly, { desc = "This Month's Goals" })
  map("n", "<leader>ogw", goals.open_weekly, { desc = "This Week's Review" })
  map("n", "<leader>ogY", goals.pick_yearly, { desc = "Browse Yearly Goals" })
  map("n", "<leader>ogM", goals.pick_monthly, { desc = "Browse Monthly Goals" })
  map("n", "<leader>ogW", goals.pick_weekly, { desc = "Browse Weekly Reviews" })

  map("n", "<leader>occ", function()
    require("custom.personal-os.clients").pick_client()
  end, { desc = "Pick client" })

  map("n", "<leader>ocf", function()
    require("custom.personal-os.clients").pick_client_file()
  end, { desc = "Pick client file" })

  map("n", "<leader>ok", function()
    require("custom.personal-os.kanban").open()
  end, { desc = "Open Kanban" })

  local todos = require("custom.personal-os.todos")
  map("n", "<leader>tt", todos.cycle_forward, { desc = "Cycle todo forward" })
  map("n", "<leader>tT", todos.cycle_backward, { desc = "Cycle todo backward" })
  map("n", "<leader>tx", function() todos.set_state("[x]") end, { desc = "Mark complete" })
  map("n", "<leader>t!", function() todos.set_state("[!]") end, { desc = "Mark priority" })
  map("n", "<leader>t?", function() todos.set_state("[?]") end, { desc = "Mark blocked" })
  map("n", "<leader>t>", function() todos.set_state("[>]") end, { desc = "Mark forwarded" })
  map("n", "<leader>t-", function() todos.set_state("[-]") end, { desc = "Mark cancelled" })
  map("v", "<leader>tt", todos.cycle_forward_visual, { desc = "Cycle todos forward" })
  map("v", "<leader>tx", function() todos.set_state_visual("[x]") end, { desc = "Mark complete" })
end

return M
