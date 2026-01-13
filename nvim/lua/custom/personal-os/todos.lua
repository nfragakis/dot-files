local M = {}
local config = require("custom.personal-os.config")

local function find_checkbox_in_line(line)
  local pattern = "%[.%]"
  local start_pos, end_pos = line:find(pattern)
  if start_pos then
    return start_pos, end_pos, line:sub(start_pos, end_pos)
  end
  return nil, nil, nil
end

local function get_state_index(state)
  for i, s in ipairs(config.todo_states) do
    if s == state then
      return i
    end
  end
  return nil
end

function M.cycle_forward()
  local line = vim.api.nvim_get_current_line()
  local start_pos, end_pos, current_state = find_checkbox_in_line(line)
  
  if not current_state then
    return
  end
  
  local current_idx = get_state_index(current_state)
  if not current_idx then
    current_idx = 0
  end
  
  local next_idx = (current_idx % #config.todo_states) + 1
  local next_state = config.todo_states[next_idx]
  
  local new_line = line:sub(1, start_pos - 1) .. next_state .. line:sub(end_pos + 1)
  vim.api.nvim_set_current_line(new_line)
end

function M.cycle_backward()
  local line = vim.api.nvim_get_current_line()
  local start_pos, end_pos, current_state = find_checkbox_in_line(line)
  
  if not current_state then
    return
  end
  
  local current_idx = get_state_index(current_state)
  if not current_idx then
    current_idx = 2
  end
  
  local prev_idx = ((current_idx - 2) % #config.todo_states) + 1
  local prev_state = config.todo_states[prev_idx]
  
  local new_line = line:sub(1, start_pos - 1) .. prev_state .. line:sub(end_pos + 1)
  vim.api.nvim_set_current_line(new_line)
end

function M.set_state(target_state)
  local line = vim.api.nvim_get_current_line()
  local start_pos, end_pos, current_state = find_checkbox_in_line(line)
  
  if not current_state then
    return
  end
  
  local new_line = line:sub(1, start_pos - 1) .. target_state .. line:sub(end_pos + 1)
  vim.api.nvim_set_current_line(new_line)
end

function M.cycle_forward_visual()
  local start_line = vim.fn.line("'<")
  local end_line = vim.fn.line("'>")
  
  for lnum = start_line, end_line do
    local line = vim.api.nvim_buf_get_lines(0, lnum - 1, lnum, false)[1]
    local start_pos, end_pos, current_state = find_checkbox_in_line(line)
    
    if current_state then
      local current_idx = get_state_index(current_state) or 0
      local next_idx = (current_idx % #config.todo_states) + 1
      local next_state = config.todo_states[next_idx]
      
      local new_line = line:sub(1, start_pos - 1) .. next_state .. line:sub(end_pos + 1)
      vim.api.nvim_buf_set_lines(0, lnum - 1, lnum, false, { new_line })
    end
  end
  
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Esc>", true, false, true), "n", false)
end

function M.set_state_visual(target_state)
  local start_line = vim.fn.line("'<")
  local end_line = vim.fn.line("'>")
  
  for lnum = start_line, end_line do
    local line = vim.api.nvim_buf_get_lines(0, lnum - 1, lnum, false)[1]
    local start_pos, end_pos, current_state = find_checkbox_in_line(line)
    
    if current_state then
      local new_line = line:sub(1, start_pos - 1) .. target_state .. line:sub(end_pos + 1)
      vim.api.nvim_buf_set_lines(0, lnum - 1, lnum, false, { new_line })
    end
  end
  
  vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Esc>", true, false, true), "n", false)
end

return M
