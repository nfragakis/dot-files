local M = {}

M.vault_path = vim.fn.expand("~/Notes/personal-os")

M.paths = {
  daily_notes = M.vault_path .. "/Daily Notes",
  templates = M.vault_path .. "/Templates",
  goals = M.vault_path .. "/Goals",
  goals_yearly = M.vault_path .. "/Goals/Yearly",
  goals_monthly = M.vault_path .. "/Goals/Monthly",
  goals_weekly = M.vault_path .. "/Goals/Weekly",
  clients = M.vault_path .. "/Profession/Clients",
  inbox = M.vault_path .. "/Inbox",
  fitness = M.vault_path .. "/Fitness",
  health = M.vault_path .. "/Health",
}

M.files = {
  priority_queue = M.paths.clients .. "/_index/Priority Queue.md",
  three_year_goals = M.paths.goals .. "/0. Three Year Goals.md",
}

M.templates = {
  yearly_goals = M.paths.templates .. "/Yearly Goals Template.md",
  monthly_goals = M.paths.templates .. "/Monthly Goals Template.md",
  weekly_review = M.paths.templates .. "/Weekly Review Template.md",
}

M.todo_states = {
  "[ ]",
  "[x]",
  "[>]",
  "[-]",
  "[?]",
  "[!]",
}

M.kanban = {
  lane_thresholds = {
    high = 5,
    medium = 3,
    low = 1,
  },
  deadline_column = "Deadline",
  card_width = 38,
  card_height = 5,
  lane_spacing = 2,
}

return M
