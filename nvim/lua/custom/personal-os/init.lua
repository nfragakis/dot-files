local M = {}

M.config = require("custom.personal-os.config")
M.keymaps = require("custom.personal-os.keymaps")
M.todos = require("custom.personal-os.todos")
M.clients = require("custom.personal-os.clients")
M.kanban = require("custom.personal-os.kanban")
M.goals = require("custom.personal-os.goals")

function M.setup()
  M.keymaps.setup()
  
  vim.api.nvim_create_user_command("PersonalOSKanban", function()
    M.kanban.open()
  end, { desc = "Open Personal OS Kanban board" })
  
  vim.api.nvim_create_user_command("PersonalOSClients", function()
    M.clients.pick_client()
  end, { desc = "Pick a client" })
  
  vim.api.nvim_create_user_command("PersonalOSPriority", function()
    vim.cmd("edit " .. M.config.files.priority_queue)
  end, { desc = "Open Priority Queue" })
end

return M
