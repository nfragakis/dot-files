local M = {}
local config = require("custom.personal-os.config")

function M.get_client_list()
  local clients = {}
  local clients_path = config.paths.clients
  
  local handle = vim.loop.fs_scandir(clients_path)
  if not handle then
    return clients
  end
  
  while true do
    local name, type = vim.loop.fs_scandir_next(handle)
    if not name then
      break
    end
    
    if type == "directory" and not name:match("^_") and not name:match("^%.") then
      local claude_path = clients_path .. "/" .. name .. "/CLAUDE.md"
      if vim.fn.filereadable(claude_path) == 1 then
        table.insert(clients, {
          name = name,
          path = clients_path .. "/" .. name,
          claude_path = claude_path,
        })
      end
    end
  end
  
  table.sort(clients, function(a, b)
    return a.name < b.name
  end)
  
  return clients
end

function M.pick_client()
  local pickers = require("telescope.pickers")
  local finders = require("telescope.finders")
  local conf = require("telescope.config").values
  local actions = require("telescope.actions")
  local action_state = require("telescope.actions.state")
  local previewers = require("telescope.previewers")
  
  local clients = M.get_client_list()
  
  pickers.new({}, {
    prompt_title = "Select Client",
    finder = finders.new_table({
      results = clients,
      entry_maker = function(entry)
        return {
          value = entry,
          display = entry.name,
          ordinal = entry.name,
          path = entry.claude_path,
        }
      end,
    }),
    sorter = conf.generic_sorter({}),
    previewer = previewers.new_buffer_previewer({
      title = "Client Context",
      define_preview = function(self, entry)
        conf.buffer_previewer_maker(entry.path, self.state.bufnr, {
          bufname = entry.value.name,
        })
      end,
    }),
    attach_mappings = function(prompt_bufnr, map_fn)
      actions.select_default:replace(function()
        actions.close(prompt_bufnr)
        local selection = action_state.get_selected_entry()
        if selection then
          vim.cmd("edit " .. selection.path)
        end
      end)
      return true
    end,
  }):find()
end

function M.pick_client_file()
  local clients = M.get_client_list()
  
  vim.ui.select(clients, {
    prompt = "Select Client:",
    format_item = function(item)
      return item.name
    end,
  }, function(choice)
    if choice then
      require("telescope.builtin").find_files({
        cwd = choice.path,
        prompt_title = "Files: " .. choice.name,
      })
    end
  end)
end

function M.open_client_by_name(name)
  local clients = M.get_client_list()
  for _, client in ipairs(clients) do
    if client.name:lower():find(name:lower()) then
      vim.cmd("edit " .. client.claude_path)
      return true
    end
  end
  vim.notify("Client not found: " .. name, vim.log.levels.WARN)
  return false
end

return M
