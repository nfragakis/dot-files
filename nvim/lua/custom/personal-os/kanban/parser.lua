local M = {}

local function get_table_at_cursor(bufnr)
  bufnr = bufnr or 0
  local node = vim.treesitter.get_node({ bufnr = bufnr })
  
  if not node then
    return nil
  end
  
  while node do
    if node:type() == "pipe_table" then
      return node
    end
    node = node:parent()
  end
  
  return nil
end

local function iter_cells(row_node, bufnr)
  local cells = {}
  for i = 0, row_node:named_child_count() - 1 do
    local cell = row_node:named_child(i)
    if cell then
      local text = vim.treesitter.get_node_text(cell, bufnr)
      text = vim.trim(text)
      table.insert(cells, text)
    end
  end
  return cells
end

function M.parse_table_at_cursor(bufnr)
  bufnr = bufnr or 0
  local table_node = get_table_at_cursor(bufnr)
  
  if not table_node then
    return nil
  end
  
  local columns = {}
  local rows = {}
  local row_line_numbers = {}
  
  for i = 0, table_node:named_child_count() - 1 do
    local child = table_node:named_child(i)
    local child_type = child:type()
    
    if child_type == "pipe_table_header" then
      columns = iter_cells(child, bufnr)
    elseif child_type == "pipe_table_row" then
      local cells = iter_cells(child, bufnr)
      local row_data = {}
      
      for idx, col_name in ipairs(columns) do
        row_data[col_name] = cells[idx] or ""
      end
      
      local start_row = child:start()
      row_data._line_number = start_row + 1
      
      table.insert(rows, row_data)
      table.insert(row_line_numbers, start_row + 1)
    end
  end
  
  return {
    columns = columns,
    rows = rows,
    row_line_numbers = row_line_numbers,
    node = table_node,
  }
end

function M.parse_file(filepath)
  local bufnr = vim.fn.bufnr(filepath)
  local was_loaded = bufnr ~= -1
  
  if not was_loaded then
    bufnr = vim.fn.bufadd(filepath)
    vim.fn.bufload(bufnr)
  end
  
  local lines = vim.api.nvim_buf_get_lines(bufnr, 0, -1, false)
  local table_start = nil
  
  for i, line in ipairs(lines) do
    if line:match("^|.*|$") and line:match("Client") then
      table_start = i
      break
    end
  end
  
  if not table_start then
    return nil
  end
  
  vim.api.nvim_win_set_cursor(0, { table_start, 0 })
  
  local result = M.parse_table_at_cursor(bufnr)
  
  return result
end

function M.parse_priority_queue()
  local config = require("custom.personal-os.config")
  local filepath = config.files.priority_queue
  
  if vim.fn.filereadable(filepath) ~= 1 then
    vim.notify("Priority Queue not found: " .. filepath, vim.log.levels.ERROR)
    return nil
  end
  
  local current_buf = vim.api.nvim_get_current_buf()
  local current_file = vim.api.nvim_buf_get_name(current_buf)
  
  local need_switch = current_file ~= filepath
  
  if need_switch then
    vim.cmd("edit " .. filepath)
  end
  
  vim.cmd("normal! gg")
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  
  for i, line in ipairs(lines) do
    if line:match("^|%s*Rank") then
      vim.api.nvim_win_set_cursor(0, { i, 0 })
      break
    end
  end
  
  local result = M.parse_table_at_cursor(0)
  
  if need_switch then
    vim.cmd("bdelete")
  end
  
  return result
end

function M.group_by_deadline(parsed_data)
  if not parsed_data or not parsed_data.rows then
    return nil
  end
  
  local lanes = {
    { title = "HIGH (5)", priority = 5, cards = {} },
    { title = "MEDIUM (3-4)", priority = 3, cards = {} },
    { title = "LOW (1-2)", priority = 1, cards = {} },
  }
  
  for _, row in ipairs(parsed_data.rows) do
    local deadline = tonumber(row.Deadline) or 0
    local card = {
      rank = row.Rank or "?",
      client = row.Client or "Unknown",
      deadline = deadline,
      score = row.Score or "?",
      next_action = row["Next Action"] or "[TBD]",
      line_number = row._line_number,
      raw = row,
    }
    
    if deadline >= 5 then
      table.insert(lanes[1].cards, card)
    elseif deadline >= 3 then
      table.insert(lanes[2].cards, card)
    else
      table.insert(lanes[3].cards, card)
    end
  end
  
  return lanes
end

return M
