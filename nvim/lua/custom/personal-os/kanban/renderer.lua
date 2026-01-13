local M = {}

M.state = {
  board_buf = nil,
  board_win = nil,
  lane_wins = {},
  card_wins = {},
  card_bufs = {},
  lanes = nil,
  focus = { lane = 1, card = 1 },
  source_buf = nil,
}

local config = require("custom.personal-os.config")

local CARD_WIDTH = config.kanban.card_width
local CARD_HEIGHT = config.kanban.card_height
local LANE_SPACING = config.kanban.lane_spacing

local function create_card_lines(card)
  local client_display = card.client
  if #client_display > CARD_WIDTH - 6 then
    client_display = client_display:sub(1, CARD_WIDTH - 9) .. "..."
  end
  
  local next_display = card.next_action
  if #next_display > CARD_WIDTH - 8 then
    next_display = next_display:sub(1, CARD_WIDTH - 11) .. "..."
  end
  
  return {
    string.format(" #%s %s", card.rank, client_display),
    string.format(" Score: %s  DL: %s", card.score, card.deadline),
    string.format(" Next: %s", next_display),
  }
end

local function get_highlight_for_deadline(deadline)
  if deadline >= 5 then
    return "DiagnosticError"
  elseif deadline >= 3 then
    return "DiagnosticWarn"
  else
    return "DiagnosticHint"
  end
end

function M.render_board(lanes)
  M.close()
  M.state.lanes = lanes
  M.state.focus = { lane = 1, card = 1 }
  
  local editor_width = vim.o.columns
  local editor_height = vim.o.lines
  
  local board_width = math.min(editor_width - 4, 140)
  local board_height = math.min(editor_height - 4, 35)
  local board_row = math.floor((editor_height - board_height) / 2)
  local board_col = math.floor((editor_width - board_width) / 2)
  
  M.state.board_buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_option_value("bufhidden", "wipe", { buf = M.state.board_buf })
  
  M.state.board_win = vim.api.nvim_open_win(M.state.board_buf, true, {
    relative = "editor",
    row = board_row,
    col = board_col,
    width = board_width,
    height = board_height,
    style = "minimal",
    border = "rounded",
    title = " Client Priority Board ",
    title_pos = "center",
    zindex = 10,
  })
  
  local lane_width = math.floor((board_width - 6) / 3)
  local lane_height = board_height - 6
  
  for lane_idx, lane in ipairs(lanes) do
    local lane_col = board_col + 2 + (lane_idx - 1) * (lane_width + LANE_SPACING)
    local lane_row = board_row + 2
    
    local lane_buf = vim.api.nvim_create_buf(false, true)
    vim.api.nvim_set_option_value("bufhidden", "wipe", { buf = lane_buf })
    
    local header_icon = lane_idx == 1 and "🔴" or (lane_idx == 2 and "🟡" or "🟢")
    local header = string.format(" %s %s ", header_icon, lane.title)
    
    vim.api.nvim_buf_set_lines(lane_buf, 0, -1, false, { header, string.rep("─", lane_width - 2) })
    
    local lane_win = vim.api.nvim_open_win(lane_buf, false, {
      relative = "editor",
      row = lane_row,
      col = lane_col,
      width = lane_width,
      height = 2,
      style = "minimal",
      border = "none",
      zindex = 15,
    })
    
    table.insert(M.state.lane_wins, lane_win)
    
    for card_idx, card in ipairs(lane.cards) do
      local card_row = lane_row + 3 + (card_idx - 1) * (CARD_HEIGHT + 1)
      
      if card_row + CARD_HEIGHT < board_row + board_height - 1 then
        local card_buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_set_option_value("bufhidden", "wipe", { buf = card_buf })
        
        local card_lines = create_card_lines(card)
        vim.api.nvim_buf_set_lines(card_buf, 0, -1, false, card_lines)
        
        local is_focused = (lane_idx == M.state.focus.lane and card_idx == M.state.focus.card)
        local border_hl = is_focused and "CursorLine" or "FloatBorder"
        
        local card_win = vim.api.nvim_open_win(card_buf, false, {
          relative = "editor",
          row = card_row,
          col = lane_col + 1,
          width = lane_width - 4,
          height = CARD_HEIGHT - 2,
          style = "minimal",
          border = is_focused and "double" or "rounded",
          zindex = 20,
        })
        
        local hl = get_highlight_for_deadline(card.deadline)
        vim.api.nvim_buf_add_highlight(card_buf, -1, hl, 0, 0, -1)
        
        table.insert(M.state.card_wins, {
          win = card_win,
          buf = card_buf,
          lane_idx = lane_idx,
          card_idx = card_idx,
          card = card,
        })
        table.insert(M.state.card_bufs, card_buf)
      end
    end
  end
  
  M.render_help_line(board_row + board_height - 1, board_col, board_width)
  M.update_focus_highlight()
  M.setup_keymaps()
end

function M.render_help_line(row, col, width)
  local help_buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_set_option_value("bufhidden", "wipe", { buf = help_buf })
  
  local help_text = " [j/k] Navigate  [h/l] Lanes  [Enter] Open  [e] Edit  [r] Refresh  [q] Close "
  vim.api.nvim_buf_set_lines(help_buf, 0, -1, false, { help_text })
  
  local help_win = vim.api.nvim_open_win(help_buf, false, {
    relative = "editor",
    row = row,
    col = col + math.floor((width - #help_text) / 2),
    width = #help_text,
    height = 1,
    style = "minimal",
    border = "none",
    zindex = 25,
  })
  
  vim.api.nvim_set_option_value("winhl", "Normal:Comment", { win = help_win })
  table.insert(M.state.lane_wins, help_win)
end

function M.update_focus_highlight()
  for _, cw in ipairs(M.state.card_wins) do
    local is_focused = (cw.lane_idx == M.state.focus.lane and cw.card_idx == M.state.focus.card)
    
    if vim.api.nvim_win_is_valid(cw.win) then
      local win_config = vim.api.nvim_win_get_config(cw.win)
      win_config.border = is_focused and "double" or "rounded"
      vim.api.nvim_win_set_config(cw.win, win_config)
      
      if is_focused then
        vim.api.nvim_set_option_value("winhl", "FloatBorder:CursorLine", { win = cw.win })
      else
        vim.api.nvim_set_option_value("winhl", "FloatBorder:FloatBorder", { win = cw.win })
      end
    end
  end
end

function M.setup_keymaps()
  local opts = { buffer = M.state.board_buf, noremap = true, silent = true }
  local actions = require("custom.personal-os.kanban.actions")
  
  vim.keymap.set("n", "j", function() actions.move_focus("down") end, opts)
  vim.keymap.set("n", "k", function() actions.move_focus("up") end, opts)
  vim.keymap.set("n", "h", function() actions.move_focus("left") end, opts)
  vim.keymap.set("n", "l", function() actions.move_focus("right") end, opts)
  vim.keymap.set("n", "<Down>", function() actions.move_focus("down") end, opts)
  vim.keymap.set("n", "<Up>", function() actions.move_focus("up") end, opts)
  vim.keymap.set("n", "<Left>", function() actions.move_focus("left") end, opts)
  vim.keymap.set("n", "<Right>", function() actions.move_focus("right") end, opts)
  vim.keymap.set("n", "<CR>", actions.open_client, opts)
  vim.keymap.set("n", "<Tab>", function() actions.move_focus("right") end, opts)
  vim.keymap.set("n", "<S-Tab>", function() actions.move_focus("left") end, opts)
  vim.keymap.set("n", "e", actions.edit_card, opts)
  vim.keymap.set("n", "r", actions.refresh, opts)
  vim.keymap.set("n", "q", M.close, opts)
  vim.keymap.set("n", "<Esc>", M.close, opts)
end

function M.close()
  for _, win in ipairs(M.state.lane_wins) do
    if vim.api.nvim_win_is_valid(win) then
      vim.api.nvim_win_close(win, true)
    end
  end
  
  for _, cw in ipairs(M.state.card_wins) do
    if vim.api.nvim_win_is_valid(cw.win) then
      vim.api.nvim_win_close(cw.win, true)
    end
  end
  
  if M.state.board_win and vim.api.nvim_win_is_valid(M.state.board_win) then
    vim.api.nvim_win_close(M.state.board_win, true)
  end
  
  M.state.lane_wins = {}
  M.state.card_wins = {}
  M.state.card_bufs = {}
  M.state.board_buf = nil
  M.state.board_win = nil
  M.state.lanes = nil
end

function M.get_focused_card()
  for _, cw in ipairs(M.state.card_wins) do
    if cw.lane_idx == M.state.focus.lane and cw.card_idx == M.state.focus.card then
      return cw.card
    end
  end
  return nil
end

return M
