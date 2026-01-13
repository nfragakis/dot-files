local M = {}

local renderer = require("custom.personal-os.kanban.renderer")
local config = require("custom.personal-os.config")

function M.move_focus(direction)
  local state = renderer.state
  if not state.lanes then
    return
  end
  
  local lane_idx = state.focus.lane
  local card_idx = state.focus.card
  local current_lane = state.lanes[lane_idx]
  
  if direction == "down" then
    if current_lane and card_idx < #current_lane.cards then
      state.focus.card = card_idx + 1
    end
  elseif direction == "up" then
    if card_idx > 1 then
      state.focus.card = card_idx - 1
    end
  elseif direction == "right" then
    if lane_idx < #state.lanes then
      state.focus.lane = lane_idx + 1
      local new_lane = state.lanes[state.focus.lane]
      if new_lane and #new_lane.cards > 0 then
        state.focus.card = math.min(state.focus.card, #new_lane.cards)
      else
        state.focus.card = 1
      end
    end
  elseif direction == "left" then
    if lane_idx > 1 then
      state.focus.lane = lane_idx - 1
      local new_lane = state.lanes[state.focus.lane]
      if new_lane and #new_lane.cards > 0 then
        state.focus.card = math.min(state.focus.card, #new_lane.cards)
      else
        state.focus.card = 1
      end
    end
  end
  
  renderer.update_focus_highlight()
end

function M.open_client()
  local card = renderer.get_focused_card()
  if not card then
    vim.notify("No card selected", vim.log.levels.WARN)
    return
  end
  
  renderer.close()
  
  local client_name = card.client
  if client_name then
    client_name = client_name:gsub("%[%[.+|", ""):gsub("%]%]", "")
    client_name = vim.trim(client_name)
  end
  
  local clients = require("custom.personal-os.clients")
  local found = clients.open_client_by_name(client_name)
  
  if not found then
    vim.cmd("edit " .. config.files.priority_queue)
    if card.line_number then
      vim.api.nvim_win_set_cursor(0, { card.line_number, 0 })
    end
  end
end

function M.edit_card()
  local card = renderer.get_focused_card()
  if not card then
    vim.notify("No card selected", vim.log.levels.WARN)
    return
  end
  
  renderer.close()
  
  vim.cmd("edit " .. config.files.priority_queue)
  
  if card.line_number then
    vim.api.nvim_win_set_cursor(0, { card.line_number, 0 })
    vim.notify("Editing: " .. card.client, vim.log.levels.INFO)
  end
end

function M.refresh()
  local parser = require("custom.personal-os.kanban.parser")
  
  renderer.close()
  
  vim.cmd("edit " .. config.files.priority_queue)
  
  local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
  for i, line in ipairs(lines) do
    if line:match("^|%s*Rank") then
      vim.api.nvim_win_set_cursor(0, { i, 0 })
      break
    end
  end
  
  local parsed = parser.parse_table_at_cursor(0)
  
  if not parsed then
    vim.notify("Could not parse Priority Queue table", vim.log.levels.ERROR)
    return
  end
  
  local lanes = parser.group_by_deadline(parsed)
  
  if not lanes then
    vim.notify("Could not group cards into lanes", vim.log.levels.ERROR)
    return
  end
  
  renderer.render_board(lanes)
end

function M.get_card_count()
  local state = renderer.state
  if not state.lanes then
    return 0
  end
  
  local count = 0
  for _, lane in ipairs(state.lanes) do
    count = count + #lane.cards
  end
  return count
end

return M
