local Model = require("./model")
local Input = require("./input")
local View = require("./view")

local CACHE_FILES, CACHE_BYTES = 12, 24 * 1024 * 1024
local SOURCE_ITEMS = {
    { path = "Working tree", value = "worktree", detail = "HEAD → local, including untracked files" },
    { path = "Unstaged", value = "unstaged", detail = "Index → working tree" },
    { path = "Staged", value = "staged", detail = "HEAD → index" },
    { path = "Branch", value = "branch", detail = "Merge base → head ref" },
    { path = "Commit", value = "commit", detail = "First parent → selected commit" },
    { path = "GitHub pull request", value = "pr", detail = "PR merge base → head; no checkout" },
}

local refresh, select_file, load_file, open_prompt, update_prompt, choose_prompt

local function live(s)
    if s.stopped then return false end
    for _, pane in ipairs(tern.pane.list()) do
        if pane.pane == s.cx.pane then return true end
    end
    s.stopped = true
    return false
end

local function request(s, operation, body, callback)
    if not live(s) then return end
    local ok, err = pcall(function()
        tern.process.run({ "python3", tern.plugin.dir .. "/backend.py", operation }, {
            stdin = tern.json.encode(body), timeout_ms = 120000,
            env = { GIT_OPTIONAL_LOCKS = "0", GH_PROMPT_DISABLED = "1", GIT_TERMINAL_PROMPT = "0" },
        }, function(result)
            if not live(s) then return end
            local decoded, data = pcall(tern.json.decode, result.stdout or "")
            local problem
            if not decoded then problem = result.timed_out and "Comparison timed out." or (result.stderr ~= "" and result.stderr or "The comparison reader returned invalid JSON.")
            elseif data.error then problem = data.error
            elseif result.status ~= 0 then problem = result.stderr ~= "" and result.stderr or "Comparison reader failed." end
            callback(problem and nil or data, problem)
            s.cx:render()
        end)
    end)
    if not ok then callback(nil, tostring(err)); s.cx:render() end
end

local function active(s)
    return s.files[s.index]
end

local function view_mode(s)
    if s.display ~= "auto" then return s.display end
    local width = s.cx.cols - ((s.focus_mode or s.cx.cols < 95) and 0 or 32)
    return width >= 112 and "split" or "unified"
end

local function layout(s, entry)
    local mode = view_mode(s)
    entry.layouts = entry.layouts or {}
    if not entry.layouts[mode] then entry.layouts[mode] = Model.layout(entry.hunks, mode) end
    return entry.layouts[mode], mode
end

local function position(s, file, mode)
    local p = s.positions[file.path]
    if not p then p = {}; s.positions[file.path] = p end
    return p[mode] or 1
end

local function set_top(s, n)
    local file = active(s)
    local entry = file and s.cache[file.path]
    if not entry or entry.error then return end
    local rows, mode = layout(s, entry)
    local p = s.positions[file.path] or {}
    s.positions[file.path] = p
    p[mode] = math.max(1, math.min(math.max(1, #rows), n))
end

local function current_top(s)
    local file = active(s)
    return file and position(s, file, view_mode(s)) or 1
end

local function trim_cache(s)
    local count, bytes = 0, 0
    for _, e in pairs(s.cache) do count = count + 1; bytes = bytes + (e.bytes or 0) end
    while count > CACHE_FILES or bytes > CACHE_BYTES do
        local victim, oldest
        for path, entry in pairs(s.cache) do
            local preview = s.prompt and s.prompt.preview
            if path ~= s.path and path ~= preview and (not oldest or entry.used < oldest) then
                victim, oldest = path, entry.used
            end
        end
        if not victim then break end
        bytes = bytes - (s.cache[victim].bytes or 0); count = count - 1
        s.cache[victim] = nil
    end
end

local function touch(s, entry)
    s.clock = s.clock + 1
    entry.used = s.clock
end

load_file = function(s, file)
    if not file or not s.comparison then return end
    local cached = s.cache[file.path]
    if cached and not cached.error and cached.fingerprint == file.fingerprint then touch(s, cached); return end
    if s.pending[file.path] then return end
    local epoch, snapshot = s.epoch, s.comparison
    s.pending[file.path] = true
    request(s, "detail", { comparison = snapshot, file = file }, function(detail, problem)
        if s.epoch ~= epoch then return end
        s.pending[file.path] = nil
        if problem then
            s.cache[file.path] = { error = problem, fingerprint = file.fingerprint, used = 0 }
        else
            local ok, hunks, unparsed = pcall(Model.parse, detail.patch or "")
            if not ok then
                s.cache[file.path] = { error = "Could not parse this patch: " .. tostring(hunks), fingerprint = file.fingerprint, used = 0 }
            else
                local incomplete = #unparsed > 0
                for _, hunk in ipairs(hunks) do if hunk.incomplete then incomplete = true end end
                if incomplete then
                    detail.truncated = true
                    detail.notice = "This patch is incomplete or uses an unsupported combined diff. It cannot be marked viewed."
                end
                -- A working file can change between list and detail. Never retain its old viewed mark.
                file.fingerprint = detail.fingerprint
                detail.hunks, detail.bytes, detail.layouts = hunks, #(detail.patch or ""), {}
                detail.patch = nil
                s.cache[file.path] = detail
                detail.used = 0
            end
        end
        touch(s, s.cache[file.path]); trim_cache(s)
        if file.path == s.path and s.query ~= "" then
            s.matches = Model.search(s.cache[file.path].hunks or {}, s.query)
            s.match_index = math.min(s.match_index, #s.matches)
        end
    end)
end

select_file = function(s, index)
    if #s.files == 0 then return end
    s.index = math.max(1, math.min(#s.files, index))
    local file = active(s)
    s.path = file.path
    s.clock = s.clock + 1; s.recent[file.path] = s.clock
    s.matches, s.match_index = {}, 0
    load_file(s, file)
    local entry = s.cache[file.path]
    if s.query ~= "" and entry and entry.hunks then s.matches = Model.search(entry.hunks, s.query) end
end

local function read_marks(s)
    local ok, value = pcall(tern.kv.get, "viewed:" .. s.comparison.id)
    s.marks = ok and type(value) == "table" and value or {}
    if not ok then s.notice = "Could not read viewed marks: " .. tostring(value) end
end

refresh = function(s, source)
    s.epoch = s.epoch + 1
    local epoch = s.epoch
    s.loading, s.error, s.notice = true, nil, nil
    s.pending = {}
    local wanted = source or s.requested_source or s.source
    s.requested_source = wanted
    request(s, "list", { cwd = s.cwd, source = wanted }, function(snapshot, problem)
        if s.epoch ~= epoch then return end
        s.loading = false
        if problem then s.error = problem; return end
        local same = (s.comparison and s.comparison.id or s.saved_id) == snapshot.id
        if not same then s.cache, s.positions = {}, {} end
        s.source, s.comparison, s.files = wanted, snapshot, snapshot.files or {}
        s.requested_source = nil
        s.notice = snapshot.notice
        local index, valid = nil, {}
        for i, file in ipairs(s.files) do
            valid[file.path] = true
            if file.path == s.path then index = i end
            local entry = s.cache[file.path]
            if entry and entry.fingerprint ~= file.fingerprint then s.cache[file.path] = nil end
        end
        for path in pairs(s.cache) do if not valid[path] then s.cache[path] = nil end end
        read_marks(s)
        s.index = math.max(1, math.min(index or s.index, #s.files))
        if #s.files > 0 then select_file(s, s.index) else s.path = nil end
        if s.prompt and s.prompt.kind == "files" then
            s.prompt.items = s.files
            update_prompt(s)
        end
        s.cx:save()
    end)
end

local function ref_items(data, kind)
    local items = {}
    if kind == "commit" then
        for _, commit in ipairs(data.commits or {}) do
            items[#items + 1] = { path = commit.sha:sub(1, 10) .. "  " .. commit.subject, value = commit.sha }
        end
    else
        for _, branch in ipairs(data.branches or {}) do items[#items + 1] = { path = branch, value = branch } end
    end
    return items
end

local function close_prompt(s)
    s.prompt = nil
    -- An empty Lua table cannot express protocol null: deleting the focused field releases focus.
end

update_prompt = function(s)
    local p = s.prompt
    if not p then return end
    if p.kind == "search" then
        local file = active(s); local entry = file and s.cache[file.path]
        p.hits = entry and Model.search(entry.hunks or {}, p.field.text) or {}
        return
    end
    p.results = Model.filter(p.items or {}, p.field.text, p.kind == "files" and s.recent or {})
    p.index = math.max(1, math.min(p.index or 1, #p.results))
    local result = p.results[p.index]
    if p.kind == "files" then
        p.preview = result and result.file.path or nil
        if result then load_file(s, result.file) end
    end
end

open_prompt = function(s, kind, text)
    local labels = { files = "Changed files", source = "Compare", base = "Base branch or revision", head = "Head branch or revision", commit = "Commit", pr = "GitHub pull request", search = "Search this file" }
    local p = { kind = kind, title = labels[kind], field = Input.new(text), index = 1, items = {}, results = {} }
    s.prompt = p
    if kind == "files" then p.items = s.files
    elseif kind == "source" then p.items = SOURCE_ITEMS
    elseif kind == "base" or kind == "head" or kind == "commit" then
        p.loading = true
        request(s, "refs", { cwd = s.cwd }, function(data, problem)
            if s.prompt ~= p then return end
            p.loading = false; p.error = problem
            if data then
                p.items = ref_items(data, kind)
                if data.branches_truncated or data.commits_truncated then p.notice = "Recent references shown; type any revision to open it." end
            end
            update_prompt(s)
        end)
    elseif kind == "pr" then
        p.loading = true
        request(s, "pulls", { cwd = s.cwd }, function(data, problem)
            if s.prompt ~= p then return end
            p.loading = false; p.error = problem
            if data then
                for _, pr in ipairs(data.pulls or {}) do
                    p.items[#p.items + 1] = { path = "#" .. pr.number .. "  " .. pr.title, value = pr.url }
                end
                if data.truncated then p.notice = "Recent pull requests shown; paste any PR URL or number." end
            end
            update_prompt(s)
        end)
    end
    update_prompt(s)
    -- Focus is queued after the new field has been rendered (SDK frame ordering).
    tern.timer(20, function()
        if live(s) and s.prompt == p then s.cx:frame({ { "focus", "layer.dialog.query" } }) end
    end)
end

local function find_match(s, delta)
    local file = active(s); local entry = file and s.cache[file.path]
    if not entry or not entry.hunks then return end
    s.matches = Model.search(entry.hunks, s.query)
    if #s.matches == 0 then s.match_index = 0; s.notice = "No matches in this file."; return end
    if s.notice == "No matches in this file." then s.notice = nil end
    s.match_index = Model.next(s.match_index, #s.matches, delta)
    local hit = s.matches[s.match_index]
    local rows = layout(s, entry)
    local index = Model.row_at(rows, hit.hunk, hit.line)
    if index then set_top(s, index) end
end

choose_prompt = function(s)
    local p = s.prompt
    if not p then return end
    local result = p.results and p.results[p.index]
    local text = p.field.text:match("^%s*(.-)%s*$")
    if p.kind == "files" then
        if result then close_prompt(s); select_file(s, result.index); s.focus = "diff" end
    elseif p.kind == "source" then
        if not result then return end
        local kind = result.file.value
        close_prompt(s)
        if kind == "branch" then open_prompt(s, "base")
        elseif kind == "commit" then open_prompt(s, "commit")
        elseif kind == "pr" then open_prompt(s, "pr")
        else refresh(s, { kind = kind }) end
    elseif p.kind == "search" then
        s.query, s.match_index = p.field.text, 0
        close_prompt(s); find_match(s, 1)
    else
        local use_result = p.picked or (p.kind == "pr" and text == "")
        local value = (use_result and result) and result.file.value or text
        if p.kind == "base" then
            s.branch_base = value
            open_prompt(s, "head", "HEAD")
        elseif p.kind == "head" then
            close_prompt(s); refresh(s, { kind = "branch", base = s.branch_base ~= "" and s.branch_base or nil, head = value ~= "" and value or "HEAD" })
        elseif p.kind == "commit" then
            close_prompt(s); refresh(s, { kind = "commit", head = value ~= "" and value or "HEAD" })
        elseif p.kind == "pr" and value ~= "" then
            close_prompt(s); refresh(s, { kind = "pr", pr = value })
        end
    end
end

local function toggle_viewed(s)
    local file = active(s); local entry = file and s.cache[file.path]
    if not file or not entry or entry.error or entry.truncated or s.loading or s.error then return end
    local key = "viewed:" .. s.comparison.id
    local ok, err = pcall(function()
        local marks = tern.kv.get(key)
        if type(marks) ~= "table" then marks = {} end
        if marks[file.path] == entry.fingerprint then marks[file.path] = nil
        else marks[file.path] = entry.fingerprint end
        tern.kv.set(key, marks)
        s.marks = marks
    end)
    if not ok then s.notice = "Could not save viewed mark: " .. tostring(err) end
end

local function jump_hunk(s, delta)
    local file = active(s); local entry = file and s.cache[file.path]
    if not entry or not entry.hunks then return end
    local rows = layout(s, entry)
    local top = current_top(s)
    local hunk = rows[top] and rows[top].hunk or 1
    local wanted = math.max(1, math.min(#entry.hunks, hunk + delta))
    for i, row in ipairs(rows) do if row.hunk == wanted then set_top(s, i); return end end
end

local function dispatch(s, action, value)
    if action == "files" then open_prompt(s, "files")
    elseif action == "source" then open_prompt(s, "source")
    elseif action == "refresh" then refresh(s)
    elseif action == "viewed" then toggle_viewed(s)
    elseif action == "focus-mode" then s.focus_mode = not s.focus_mode
    elseif action == "display" then s.display = s.display == "auto" and "split" or (s.display == "split" and "unified" or "auto")
    elseif action == "help" then s.help = not s.help
    elseif action == "next-file" then select_file(s, Model.next(s.index, #s.files, 1) or 1)
    elseif action == "previous-file" then select_file(s, Model.next(s.index, #s.files, -1) or 1)
    elseif action == "next-hunk" then jump_hunk(s, 1)
    elseif action == "previous-hunk" then jump_hunk(s, -1)
    elseif action == "next-page" then set_top(s, current_top(s) + (s.page_rows or s.capacity))
    elseif action == "previous-page" then set_top(s, current_top(s) - (s.page_rows or s.capacity))
    elseif action == "cancel" then close_prompt(s); s.help = false
    elseif action == "choose" then choose_prompt(s)
    elseif action == "pick-file" then select_file(s, tonumber(value) or 1); s.focus = "files"
    elseif action == "read" then s.focus = "diff"
    end
end

local function key(s, key)
    local name, text = key.name, key.text or key.name
    if key.shift and #text == 1 then text = string.upper(text) end
    if s.prompt then
        local p = s.prompt
        if name == "escape" then close_prompt(s); return true end
        if name == "enter" then choose_prompt(s); return true end
        if name == "down" or name == "up" or ((key.ctrl or key.meta) and (name == "n" or name == "p")) then
            local delta = (name == "down" or name == "n") and 1 or -1
            p.index = Model.next(p.index, #(p.results or {}), delta) or 1
            p.picked = true
            local result = p.results[p.index]
            if p.kind == "files" then p.preview = result and result.file.path; if result then load_file(s, result.file) end end
            return true
        end
        local old = p.field.text
        if Input.key(p.field, key) then
            if p.field.text ~= old then p.index, p.picked = 1, false; update_prompt(s) end
            return true
        end
        return false
    end
    if s.help then
        if name == "escape" or text == "q" or text == "?" then s.help = false; return true end
        return false
    end
    if key.alt or name == "paste" then return false end
    if key.ctrl or key.meta then
        if name == "p" then open_prompt(s, "files"); return true end
        if name == "r" then refresh(s); return true end
        if name == "d" or name == "u" then
            local delta = math.max(1, math.floor(s.capacity / 2)) * (name == "d" and 1 or -1)
            if s.focus == "files" then select_file(s, s.index + delta) else set_top(s, current_top(s) + delta) end
            return true
        end
        return false
    end
    local prefix = s.prefix; s.prefix = nil
    if prefix == "g" and text == "g" then
        if s.focus == "files" then select_file(s, 1) else set_top(s, 1) end
        return true
    elseif (prefix == "]" or prefix == "[") and (text == "f" or text == "c") then
        local delta = prefix == "]" and 1 or -1
        if text == "f" then select_file(s, Model.next(s.index, #s.files, delta) or 1) else jump_hunk(s, delta) end
        return true
    end
    if text == "g" or text == "[" or text == "]" then s.prefix = text; return true end
    if text == "j" or text == "k" or name == "up" or name == "down" then
        local delta = (text == "j" or name == "down") and 1 or -1
        if s.focus == "files" then select_file(s, Model.next(s.index, #s.files, delta) or 1) else set_top(s, current_top(s) + delta) end
    elseif text == "G" or name == "end" then
        if s.focus == "files" then select_file(s, #s.files) else set_top(s, math.huge) end
    elseif name == "home" then
        if s.focus == "files" then select_file(s, 1) else set_top(s, 1) end
    elseif name == "pageup" or name == "page_up" or name == "pagedown" or name == "page_down" then
        local up = name == "pageup" or name == "page_up"
        if s.focus == "files" then select_file(s, s.index + s.capacity * (up and -1 or 1)) else set_top(s, current_top(s) + (s.page_rows or s.capacity) * (up and -1 or 1)) end
    elseif name == "tab" then s.focus = s.focus == "files" and "diff" or "files"
    elseif name == "enter" then s.focus = "diff"
    elseif name == "escape" then
        if s.query ~= "" then s.query, s.matches, s.match_index = "", {}, 0 else s.focus = "files" end
    elseif text == "/" then open_prompt(s, "search", s.query)
    elseif text == "n" or text == "N" then find_match(s, text == "n" and 1 or -1)
    elseif text == "s" then open_prompt(s, "source")
    elseif text == "f" then open_prompt(s, "files")
    elseif text == "r" then refresh(s)
    elseif text == "v" then toggle_viewed(s)
    elseif text == "z" then s.focus_mode = not s.focus_mode
    elseif text == "d" then dispatch(s, "display")
    elseif text == "?" then s.help = true
    elseif text == "q" then s.stopped = true; s.cx:exit(0)
    else return prefix ~= nil end
    return true
end

tern.block.define("viewer", {
    font = "sans",
    features = { "edit" },
    init = function(cx, args, saved)
        saved = type(saved) == "table" and saved or {}
        local source = saved.source or { kind = "worktree" }
        local s = {
            cx = cx, cwd = cx.cwd or ".", source = source, files = {}, index = 1,
            path = saved.path, positions = saved.positions or {}, cache = {}, pending = {}, recent = {},
            saved_id = saved.comparison_id,
            epoch = 0, clock = 0, focus = "diff", focus_mode = saved.focus_mode == true,
            display = saved.display or "auto", query = "", matches = {}, match_index = 0,
            capacity = math.max(3, cx.rows - 18), marks = {}, stopped = false,
        }
        if args[1] == "pr" then open_prompt(s, "pr") else refresh(s) end
        return s
    end,
    title = function(s) return "Diff · " .. (s.comparison and s.comparison.label or "Read only") end,
    view = function(s, cx)
        s.cx = cx
        s.capacity = math.max(3, math.floor(cx.rows - 18 - (s.query ~= "" and 2 or 0)))
        s.mode = view_mode(s)
        local file = active(s); local entry = file and s.cache[file.path]
        s.top = file and position(s, file, s.mode) or 1
        s.rows = entry and entry.hunks and layout(s, entry) or {}
        s.top = math.max(1, math.min(s.top, math.max(1, #s.rows)))
        if file and entry and entry.hunks then
            s.positions[file.path] = s.positions[file.path] or {}
            s.positions[file.path][s.mode] = s.top
        end
        return View.render(s)
    end,
    key = function(s, event) return key(s, event) end,
    event = function(s, ev)
        if ev.ev == "action" then dispatch(s, ev.act, ev.value)
        elseif (ev.ev == "select" or ev.ev == "activate") and ev.id == "main.work.rail.files" then
            local index = tonumber((ev.item or ""):match("i(%d+)$"))
            if index then select_file(s, index); s.focus = ev.ev == "activate" and "diff" or "files" end
        elseif (ev.ev == "select" or ev.ev == "activate") and ev.id == "layer.dialog.results" and s.prompt then
            local index = tonumber((ev.item or ""):match("i(%d+)$"))
            if index then
                s.prompt.index, s.prompt.picked = index, true
                local result = s.prompt.results[index]
                if s.prompt.kind == "files" and result then s.prompt.preview = result.file.path; load_file(s, result.file) end
                if ev.ev == "activate" then choose_prompt(s) end
            end
        elseif ev.ev == "edit" and s.prompt and ev.id == "layer.dialog.query" then
            if ev.len == Input.length(s.prompt.field.text) then
                Input.edit(s.prompt.field, ev.from, ev.to, ev.text, ev.cursor)
                s.prompt.index, s.prompt.picked = 1, false; update_prompt(s)
            end
        elseif ev.ev == "focus" and s.prompt and ev.id == "layer.dialog.query" then
            s.cx:frame({ { "focus", "layer.dialog.query" } })
        end
    end,
    save = function(s)
        return { source = s.source, comparison_id = s.comparison and s.comparison.id, path = s.path, positions = s.positions, focus_mode = s.focus_mode, display = s.display }
    end,
})
