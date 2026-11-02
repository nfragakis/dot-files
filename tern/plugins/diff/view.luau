local Model = require("./model")
local ui = tern.ui
local M = {}

local function text(spans, props)
    local node = ui.text(spans)
    node.p.key, node.p.role = props and props.key, props and props.role
    node.p.wrap, node.p.truncate = "none", "middle"
    return node
end
local function span(value, token) return ui.span(tostring(value or ""), token) end
local function button(label, action, opts)
    opts = opts or {}
    opts.text, opts.actions = label, { click = action }
    opts.class = "btn sm quiet"
    return ui.el("button", opts)
end
local function col(key, role, children, extra)
    local p = extra or {}; p.key, p.role = key, role
    return ui.node("col", p, children)
end
local function row(key, role, children)
    return ui.node("row", { key = key, role = role }, children)
end
local function display_path(path)
    return path:gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
end
local function file_marks(s, file)
    return file.fingerprint and s.marks[file.path] == file.fingerprint
end
local function shown_list(items, key, selected, max, role)
    local node = ui.list(items)
    for i, child in ipairs(node.c or {}) do child.p = child.p or {}; child.p.key = "i" .. i end
    node.p = { key = key, selected = selected, max = { lines = max }, role = role }
    return node
end

local function file_rail(s)
    local items = {}
    for _, file in ipairs(s.files) do
        local seen = file_marks(s, file)
        local status = ({ added = "A", deleted = "D", modified = "M", renamed = "R", copied = "C", untracked = "?", typechange = "T", unmerged = "!" })[file.status] or "M"
        local tone = file.status == "deleted" and "error" or ((file.status == "added" or file.status == "untracked") and "success" or "muted")
        items[#items + 1] = {
            label = { span(seen and "✓ " or status .. " ", seen and "success" or tone), span(display_path(file.path), "path") },
            value = { span("+" .. (file.additions or 0), "success"), span(" −" .. (file.deletions or 0), "error") },
        }
    end
    local height = math.max(4, math.floor((s.cx.rows - 12) * .72))
    return col("rail", "diff.rail", {
        row("head", "diff.rail-head", { text({ span("Changed files", "strong"), span("  " .. #items, "muted") }), button("Find", "files", { keys = { "ctrl", "p" } }) }),
        shown_list(items, "files", "main.work.rail.files.i" .. s.index, height, "diff.files"),
        text({ span(s.focus == "files" and "FILES" or "j/k select · Enter read", s.focus == "files" and "accent strong" or "muted") }),
    })
end

local function message(title, detail, action)
    local children = { text({ span(title, "strong") }), ui.text({ span(detail, "muted") }) }
    if action then children[#children + 1] = button("Retry", action) end
    return col("message", "diff.message", children)
end

local function diff_window(entry, rows, top, count, mode, prefix)
    local nodes = {}
    local groups = Model.window(rows, top, count)
    for i, h in ipairs(groups) do
        local original = entry.hunks[h.hunk]
        nodes[#nodes + 1] = col("h" .. i, "diff.hunk", {
            text({ span(original and original.header or "Change", "muted mono") }, { key = "head", role = "diff.hunk-head" }),
            ui.node("diff", {
                key = "code", path = entry.path, mode = mode,
                hunks = { { oldStart = h.old_start, newStart = h.new_start, lines = h.lines } },
            }),
        })
    end
    return col(prefix or "viewport", "diff.viewport", nodes)
end

local function reading(s)
    local file = s.files[s.index]
    if not s.comparison then
        if s.loading then return message("Reading comparison…", "Git and GitHub reads run on this host, outside the UI thread.") end
        return message("Choose a comparison", s.error or "Press s to choose working changes, revisions, or a pull request.", s.error and "refresh" or nil)
    end
    if #s.files == 0 then return message("No changes", "This comparison has no changed files. Press s to compare something else.") end
    local entry = file and s.cache[file.path]
    local children = {
        row("filehead", "diff.file-head", {
            text({ span(display_path(file.path), "path strong") }, { key = "path", role = "diff.filename" }),
            button(file_marks(s, file) and "Viewed" or "Mark viewed", "viewed", { on = file_marks(s, file), keys = { "v" }, disabled = (not entry or entry.error or entry.truncated or s.loading or s.error) and "Wait for a complete comparison" or nil }),
        }),
    }
    if file.old_path and file.old_path ~= file.path then children[#children + 1] = text({ span("Renamed from " .. display_path(file.old_path), "muted path") }) end
    if not entry then
        children[#children + 1] = ui.progress(nil, "Reading " .. display_path(file.path) .. "…")
    elseif entry.error then
        children[#children + 1] = message("Could not read this file", entry.error, "refresh")
    elseif entry.truncated then
        children[#children + 1] = message("Diff exceeds the display limit", entry.notice or "This file was not truncated silently. Use an external viewer for this change.")
    elseif entry.binary then
        children[#children + 1] = message("Binary file changed", entry.notice or "No textual diff is available. Viewed marks track the binary content fingerprint.")
    elseif #entry.hunks == 0 then
        children[#children + 1] = message("Metadata-only change", entry.notice or "The file was renamed, its mode changed, or an empty file was added or removed.")
    else
        if entry.notice then children[#children + 1] = text({ span(entry.notice, "warning") }) end
        local hunk = s.rows[s.top] and s.rows[s.top].hunk or 1
        children[#children + 1] = row("location", "diff.location", {
            text({ span(s.mode == "split" and "BEFORE  /  AFTER" or "UNIFIED", "muted"), span("    Hunk " .. hunk .. " / " .. #entry.hunks, "muted mono") }),
            button("Previous hunk", "previous-hunk"), button("Next hunk", "next-hunk"),
        })
        if s.query ~= "" then
            local hit = s.matches[s.match_index]
            children[#children + 1] = text({ span("/" .. s.query, "accent"), span("  " .. s.match_index .. "/" .. #s.matches .. "  ", "muted mono"), span(hit and hit.text or "No matches", "mono") })
        end
        -- Bound rendered rows so large files do not slow file switching or key repeat.
        -- Reserve two row heights for each hunk header to avoid clipping many tiny hunks.
        local count, used, previous = 0, 0, nil
        for i = s.top, math.min(#s.rows, s.top + s.capacity - 1) do
            local r = s.rows[i]
            local cost = 1 + (r.hunk ~= previous and 2 or 0)
            if used + cost > s.capacity and count > 0 then break end
            count, used, previous = count + 1, used + cost, r.hunk
        end
        s.page_rows = math.max(1, count)
        children[#children + 1] = diff_window(entry, s.rows, s.top, math.max(1, count), s.mode)
        children[#children + 1] = row("paging", "diff.paging", {
            button("Previous page", "previous-page"),
            text({ span("Rows " .. s.top .. "–" .. math.min(#s.rows, s.top + count - 1) .. " / " .. #s.rows, "muted mono") }),
            button("Next page", "next-page"),
        })
    end
    return col("reader", "diff.reader", children)
end

local function prompt(s)
    local p = s.prompt
    if not p then return nil end
    local hints = {
        files = "Type a path · Ctrl N/P select · Enter open · Esc cancels",
        source = "Choose what to compare · Enter choose · Esc cancels",
        base = "Type a base ref, or select one. Empty uses the upstream/default branch.",
        head = "Type a head ref. HEAD uses the current branch tip.",
        commit = "Type any commit SHA/ref, or select a recent commit.",
        pr = "Paste a PR URL or number, or select an open pull request.",
        search = "Literal search · lowercase ignores case · uppercase matches case",
    }
    local children = {
        row("title", "diff.dialog-head", { text({ span(p.title, "strong") }), button("Cancel", "cancel", { keys = { "esc" } }) }),
        ui.node("input", { key = "query", text = p.field.text, cursor = p.field.cursor, placeholder = hints[p.kind], role = "diff.query" }),
        ui.text({ span(hints[p.kind], "muted") }),
    }
    if p.loading then children[#children + 1] = ui.progress(nil, "Reading suggestions…") end
    if p.error then children[#children + 1] = ui.text({ span(p.error, "warning") }) end
    if p.notice then children[#children + 1] = text({ span(p.notice, "muted") }) end
    if p.kind == "search" then
        children[#children + 1] = text({ span(#(p.hits or {}) .. " matches in this file", "accent") })
        for i = 1, math.min(5, #(p.hits or {})) do
            local hit = p.hits[i]
            children[#children + 1] = text({ span(tostring(hit.new_line or hit.old_line) .. "  ", "muted mono"), span(hit.text, "mono") })
        end
    else
        local items = {}
        for _, result in ipairs(p.results or {}) do
            items[#items + 1] = { label = { span(display_path(result.file.path), "mono") }, detail = result.file.detail and { span(result.file.detail, "muted") } or nil }
        end
        local list = shown_list(items, "results", "layer.dialog.results.i" .. p.index, math.max(3, math.min(9, math.floor(s.cx.rows / 4))), "diff.results")
        list.p.empty = { span(p.loading and "Reading…" or "No matches. You can still enter a revision or PR URL.", "muted") }
        list.p.filter = p.field.text
        children[#children + 1] = list
        if p.kind == "files" and p.preview then
            local entry = s.cache[p.preview]
            if entry and entry.hunks then
                local rows = Model.layout(entry.hunks, "unified")
                children[#children + 1] = text({ span("Preview · " .. display_path(p.preview), "muted path") })
                if #rows > 0 then children[#children + 1] = diff_window(entry, rows, 1, 4, "unified", "preview")
                else children[#children + 1] = text({ span(entry.notice or (entry.binary and "Binary change" or "Metadata-only change"), "muted") }) end
            elseif entry and entry.error then children[#children + 1] = text({ span(entry.error, "warning") })
            else children[#children + 1] = ui.progress(nil, "Reading preview…") end
        end
    end
    children[#children + 1] = row("foot", "diff.dialog-foot", { button(p.kind == "search" and "Find" or "Open", "choose", { keys = { "enter" } }) })
    return col("dialog", "diff.dialog", children)
end

local function help()
    return col("help", "diff.dialog", {
        row("head", "diff.dialog-head", { text({ span("Diff · navigation", "strong") }), button("Close", "cancel", { keys = { "esc" } }) }),
        ui.md("| Keys | Action |\n|---|---|\n| j / k · arrows | File selection or logical diff-row scrolling |\n| gg / G · Home / End | First / last row or file |\n| Ctrl D / U | Half-page down / up |\n| Page Down / Up | Full page |\n| ]f / [f | Next / previous file |\n| ]c / [c | Next / previous hunk |\n| Ctrl P · f | Fuzzy changed-file picker |\n| / · n / N | Search current file; next / previous match |\n| Tab · Enter | Change internal focus; enter diff |\n| z | Toggle full-width focus mode |\n| d | Auto / split / unified |\n| s | Change comparison source |\n| v | Toggle viewed for this exact content |\n| r · Ctrl R | Refresh comparison |\n| Esc | Close dialog, clear search, or focus files |\n| q | Close viewer (normal mode only) |\n\nPicker: type normally, Ctrl N/P or arrows select, Enter accepts, Esc cancels. Repository contents are read-only. Viewed marks are stored in Tern's plugin data.\n\nLong wrapped lines can also be read with the pointer scrollbar inside the viewport. Your pane/editor Ctrl H/J/K/L and Alt H/J/K/L remain untouched."),
    })
end

function M.render(s)
    local count, added, deleted = 0, 0, 0
    for _, file in ipairs(s.files) do
        if file_marks(s, file) then count = count + 1 end
        added, deleted = added + (file.additions or 0), deleted + (file.deletions or 0)
    end
    local comparison = s.comparison
    local head = row("head", "diff.head", {
        text({ span("Diff", "title strong"), span("  " .. (comparison and comparison.label or "Read only"), "muted") }, { role = "diff.title" }),
        button("Compare", "source", { keys = { "s" } }),
        button(s.display == "auto" and ("Auto · " .. s.mode) or s.display, "display", { keys = { "d" } }),
        button(s.focus_mode and "Show files" or "Focus", "focus-mode", { on = s.focus_mode, keys = { "z" } }),
        button("Refresh", "refresh", { keys = { "r" }, busy = s.loading }),
    })
    local main = { head }
    if comparison then
        main[#main + 1] = row("summary", "diff.summary", {
            text({ span((comparison.base or ""):sub(1, 12), "mono"), span(" → ", "muted"), span((comparison.head or ""):sub(1, 12), "mono"), span("   " .. #s.files .. " files · " .. count .. " viewed", "muted"), span("   +" .. added, "success"), span(" −" .. deleted, "error") }),
            button("Find file", "files", { keys = { "ctrl", "p" } }),
        })
    end
    if s.error then main[#main + 1] = ui.text({ span("Comparison failed. " .. (comparison and "Previous snapshot is stale. " or "") .. s.error, "error") }) end
    if s.notice then main[#main + 1] = ui.text({ span(s.notice, "warning") }) end
    local work = {}
    if not s.focus_mode and s.cx.cols >= 95 then work[#work + 1] = file_rail(s) end
    work[#work + 1] = reading(s)
    main[#main + 1] = row("work", "diff.work", work)
    local dock = row("status", "diff.status", {
        text({ span(s.prompt and "PICKER" or s.focus:upper(), "accent strong"), span("   [f ]f file   [c ]c hunk   / search   v viewed   ? help", "muted mono") }),
        button("Previous file", "previous-file"), button("Next file", "next-file"), button("Help", "help"),
    })
    return {
        main = ui.node("col", { role = "diff.main" }, main),
        dock = ui.col({ dock }),
        layer = ui.col(s.prompt and { prompt(s) } or (s.help and { help() } or {})),
    }
end

return M
