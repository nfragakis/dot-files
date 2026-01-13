local M = {}
local config = require("custom.personal-os.config")

local function get_current_year()
  return os.date("%Y")
end

local function get_current_month()
  return os.date("%Y-%m")
end

local function get_current_week()
  return os.date("%Y-W%V")
end

local function get_month_name(month_str)
  local months = {
    ["01"] = "January", ["02"] = "February", ["03"] = "March",
    ["04"] = "April", ["05"] = "May", ["06"] = "June",
    ["07"] = "July", ["08"] = "August", ["09"] = "September",
    ["10"] = "October", ["11"] = "November", ["12"] = "December",
  }
  local month = month_str:match("%-(%d%d)$")
  return months[month] or month
end

local function file_exists(path)
  return vim.fn.filereadable(path) == 1
end

local function read_template(template_path)
  if not file_exists(template_path) then
    return nil
  end
  local lines = vim.fn.readfile(template_path)
  return table.concat(lines, "\n")
end

local function create_from_template(filepath, template_path, title)
  local content = read_template(template_path)
  if content then
    content = content:gsub("{{title}}", title)
    content = content:gsub("{{date}}", os.date("%Y-%m-%d"))
  else
    content = "# " .. title .. "\n\n*Created: " .. os.date("%Y-%m-%d") .. "*\n"
  end
  
  local dir = vim.fn.fnamemodify(filepath, ":h")
  vim.fn.mkdir(dir, "p")
  vim.fn.writefile(vim.split(content, "\n"), filepath)
end

function M.open_yearly(year)
  year = year or get_current_year()
  local filename = year .. " Yearly Goals.md"
  local filepath = config.paths.goals_yearly .. "/" .. filename
  
  if not file_exists(filepath) then
    local title = year .. " Yearly Goals"
    create_from_template(filepath, config.templates.yearly_goals, title)
    vim.notify("Created " .. filename, vim.log.levels.INFO)
  end
  
  vim.cmd("edit " .. vim.fn.fnameescape(filepath))
end

function M.open_monthly(month)
  month = month or get_current_month()
  local month_name = get_month_name(month)
  local year = month:match("^(%d%d%d%d)")
  local filename = month .. " Monthly Goals.md"
  local filepath = config.paths.goals_monthly .. "/" .. filename
  
  if not file_exists(filepath) then
    local title = month_name .. " " .. year .. " Monthly Goals"
    create_from_template(filepath, config.templates.monthly_goals, title)
    vim.notify("Created " .. filename, vim.log.levels.INFO)
  end
  
  vim.cmd("edit " .. vim.fn.fnameescape(filepath))
end

function M.open_weekly(week)
  week = week or get_current_week()
  local week_num = week:match("W(%d+)$")
  local filename = week .. " Weekly Review.md"
  local filepath = config.paths.goals_weekly .. "/" .. filename
  
  if not file_exists(filepath) then
    local year = week:match("^(%d%d%d%d)")
    local title = "Week " .. week_num .. " - " .. year
    create_from_template(filepath, config.templates.weekly_review, title)
    vim.notify("Created " .. filename, vim.log.levels.INFO)
  end
  
  vim.cmd("edit " .. vim.fn.fnameescape(filepath))
end

function M.open_three_year()
  vim.cmd("edit " .. vim.fn.fnameescape(config.files.three_year_goals))
end

function M.pick_yearly()
  local ok, telescope = pcall(require, "telescope.builtin")
  if ok then
    telescope.find_files({
      cwd = config.paths.goals_yearly,
      prompt_title = "Yearly Goals",
    })
  else
    vim.cmd("edit " .. config.paths.goals_yearly)
  end
end

function M.pick_monthly()
  local ok, telescope = pcall(require, "telescope.builtin")
  if ok then
    telescope.find_files({
      cwd = config.paths.goals_monthly,
      prompt_title = "Monthly Goals",
    })
  else
    vim.cmd("edit " .. config.paths.goals_monthly)
  end
end

function M.pick_weekly()
  local ok, telescope = pcall(require, "telescope.builtin")
  if ok then
    telescope.find_files({
      cwd = config.paths.goals_weekly,
      prompt_title = "Weekly Reviews",
    })
  else
    vim.cmd("edit " .. config.paths.goals_weekly)
  end
end

return M
