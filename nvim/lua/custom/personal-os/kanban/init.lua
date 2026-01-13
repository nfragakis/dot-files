local M = {}

M.parser = require("custom.personal-os.kanban.parser")
M.renderer = require("custom.personal-os.kanban.renderer")
M.actions = require("custom.personal-os.kanban.actions")

function M.open()
  local config = require("custom.personal-os.config")
  local filepath = config.files.priority_queue
  
  if vim.fn.filereadable(filepath) ~= 1 then
    vim.notify("Priority Queue not found: " .. filepath, vim.log.levels.ERROR)
    return
  end
  
  vim.cmd("edit " .. filepath)
  
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  local table_line = nil
  
  for i, line in ipairs(lines) do
    if line:match("^|%s*Rank") then
      table_line = i
      break
    end
  end
  
  if not table_line then
    vim.notify("Could not find Priority Queue table", vim.log.levels.ERROR)
    return
  end
  
  vim.api.nvim_win_set_cursor(0, { table_line, 0 })
  
  local parsed = M.parser.parse_table_at_cursor(0)
  
  if not parsed or not parsed.rows or #parsed.rows == 0 then
    vim.notify("Could not parse Priority Queue table", vim.log.levels.ERROR)
    return
  end
  
  local lanes = M.parser.group_by_deadline(parsed)
  
  if not lanes then
    vim.notify("Could not create kanban lanes", vim.log.levels.ERROR)
    return
  end
  
  M.renderer.render_board(lanes)
end

function M.close()
  M.renderer.close()
end

function M.is_open()
  return M.renderer.state.board_win ~= nil and vim.api.nvim_win_is_valid(M.renderer.state.board_win)
end

function M.toggle()
  if M.is_open() then
    M.close()
  else
    M.open()
  end
end

return M
