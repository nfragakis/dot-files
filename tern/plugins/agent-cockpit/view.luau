local ui = tern.ui
local selection = require("./selection")
local view = {}

view.LIST_ID = "layer.agents"

function view.item_key(item)
    return type(item) == "string" and item:match("^[^:]+:(pane%-%d+)$") or nil
end

local phases = {
    working = { label = "Working", tone = "info" },
    waiting_input = { label = "Needs input", tone = "warning" },
    idle = { label = "Idle", tone = "success" },
    unknown = { label = "Unknown", tone = "muted" },
    failed = { label = "Failed", tone = "error" },
    exited = { label = "Exited", tone = "muted" },
}

local providers = {
    omp = { label = "omp" },
    claude = { label = "Claude Code" },
    codex = { label = "Codex" },
}

local function phase(row)
    return phases[row.status] or phases.unknown
end

local function present(value, fallback)
    return type(value) == "string" and value ~= "" and value or fallback
end

local function with(node, props)
    local p = node.p or {}
    for key, value in pairs(props) do p[key] = value end
    node.p = p
    return node
end

local function duration(ms)
    if type(ms) ~= "number" or ms < 0 or ms >= math.huge then return "Not reported" end
    local seconds = math.floor(ms / 1000)
    if seconds < 60 then return tostring(seconds) .. "s" end
    if seconds < 3600 then return string.format("%dm %02ds", math.floor(seconds / 60), seconds % 60) end
    if seconds < 86400 then return string.format("%dh %02dm", math.floor(seconds / 3600), math.floor(seconds / 60) % 60) end
    return string.format("%dd %02dh", math.floor(seconds / 86400), math.floor(seconds / 3600) % 24)
end

-- Short age for cards and badges: 45s, 12m, 2h 14m, 3d 4h.
local function age(ms)
    if type(ms) ~= "number" or ms < 0 then return nil end
    local minutes = math.floor(ms / 60000)
    if minutes < 1 then return nil end
    if minutes < 60 then return tostring(minutes) .. "m" end
    if minutes < 1440 then return string.format("%dh %02dm", math.floor(minutes / 60), minutes % 60) end
    return string.format("%dd %dh", math.floor(minutes / 1440), math.floor(minutes / 60) % 24)
end

local tabColors = {
    red = true, orange = true, yellow = true, green = true, teal = true, blue = true, purple = true, pink = true,
}

local function agents(state, cx)
    local items, order = {}, {}
    local lastHost, lastSession
    state.page_size = math.max(1, math.floor((cx.rows - 10) / 3))
    for _, row in ipairs(state.rows) do
        local host, session = row.host_key or row.host, row.session_key or row.session
        if host ~= lastHost or session ~= lastSession then
            order[#order + 1] = {
                group = "group:" .. row.key,
                label = present(row.session, "Unknown session"),
                count = present(row.host, "Unknown host"),
            }
            lastHost, lastSession = host, session
        end
        local info = phase(row)
        local provider = providers[row.provider] or { label = "Agent" }
        local activity = row.activity
        if activity == row.title or activity == row.provider then activity = nil end
        local badges = {}
        if row.flagged then badges[#badges + 1] = { text = "Revisit", tone = "error" } end
        if row.status == "idle" and row.done_unseen then
            badges[#badges + 1] = { text = "Ready", tone = "success" }
        else
            badges[#badges + 1] = { text = info.label, tone = info.tone }
        end
        local when = age(row.phase_ms)
        items[#items + 1] = {
            id = row.provider .. ":" .. row.key,
            label = present(row.title, "Untitled agent"),
            detail = provider.label .. (when and ("  ·  " .. string.lower(info.label) .. " " .. when) or "")
                .. "\n" .. present(activity, "Activity not reported"),
            mark = { text = provider.label, seed = row.provider },
            badges = badges,
            -- Styled by cockpit.css: the card wears its tab's colour (red revisit, yellow
            -- needs input, green ready to review, or one picked by hand); long-idle agents dim.
            node = tabColors[row.tab_color] and ("tab-" .. row.tab_color) or (row.stale and "stale" or nil),
        }
        order[#order + 1] = row.provider .. ":" .. row.key
    end
    return tern.json.array(items), tern.json.array(order)
end

-- First " · "-separated segment of a collector string ("Open · review required" -> "Open").
local function head(text)
    return type(text) == "string" and (text:match("^(.-) · ") or text) or nil
end

-- A single-line text node, truncated at the end (tern-forge's usage panel idiom).
local function line(spans, props)
    local p = { spans = spans, truncate = "end" }
    for key, value in pairs(props or {}) do p[key] = value end
    return ui.node("text", p)
end

-- One labelled row: a fixed 9ch label, then its value nodes.
local function metric(key, title, nodes)
    local children = { line({ ui.span(title, "muted") }, { min = { w = "9ch" }, max = { w = "9ch" }, basis = "content" }) }
    for _, item in ipairs(nodes) do children[#children + 1] = item end
    return ui.node("row", { gap = "sm", key = key }, children)
end

-- omp's own status-line numbers: 999, 1.5K, 45K, 1.2M.
local function tokens(n)
    if type(n) ~= "number" then return nil end
    if n >= 1e6 then return string.format("%.1fM", n / 1e6) end
    if n >= 1e4 then return string.format("%dK", math.floor(n / 1e3 + 0.5)) end
    if n >= 1e3 then return string.format("%.1fK", n / 1e3) end
    return tostring(math.floor(n))
end

local agentStatus = {
    working = "running", waiting_input = "running", idle = "idle",
    exited = "done", failed = "failed", unknown = "pending",
}
local ciTones = { Passing = "success", Failing = "error", Pending = "warning" }

-- The native agent row Tern draws for omp subagents: status, model, live tool and stats in one header.
local function agent_header(row, provider, s)
    local badges = {}
    if row.flagged then badges[#badges + 1] = { text = "Revisit", tone = "error" } end
    if row.status == "waiting_input" then badges[#badges + 1] = { text = "Needs input", tone = "warning" } end
    if row.status == "idle" and row.done_unseen then badges[#badges + 1] = { text = "Ready to review", tone = "success" } end
    if row.parked then badges[#badges + 1] = { text = "Parked", tone = "muted" } end
    local stats = { age = row.phase_ms }
    if s then
        local total = (s.input or 0) + (s.output or 0) + (s.cache_read or 0) + (s.cache_write or 0)
        if total > 0 then stats.tokens = total end
        if s.cost then stats.cost = s.cost end
        if s.context and s.capacity then
            stats.context = math.min(1, s.context / s.capacity)
            stats.contextLabel = tokens(s.context) .. " / " .. tokens(s.capacity)
        end
    end
    local active = row.status == "working" or row.status == "waiting_input"
    return ui.node("agent", {
        key = "agent", name = present(row.title, "Untitled agent"), agent = provider.label,
        status = row.parked and "parked" or (row.status == "idle" and row.done_unseen and "done")
            or agentStatus[row.status] or "pending",
        model = row.model, task = row.request,
        tool = active and row.activity and { name = row.status == "waiting_input" and "Waiting" or "Now",
            intent = row.activity, age = row.phase_ms } or nil,
        stats = stats, badges = badges,
    })
end

local function usage_rows(row, s)
    local rows = {}
    if not s or next(s) == nil then
        rows[1] = line({ ui.span(row.collector_note or present(row.session_tokens, "No usage reported for this session yet."), "muted") },
            { key = "usage-empty", wrap = true })
        return rows
    end
    if s.context then
        local ratio = s.capacity and math.min(1, s.context / s.capacity) or nil
        rows[#rows + 1] = metric("context", "Context", {
            ui.node("meter", {
                value = ratio or tern.json.null, style = "bar", size = "sm", grow = 1,
                thresholds = { warn = 0.5, bad = 0.9 },
                label = ratio and string.format("%d%%", math.floor(ratio * 100 + 0.5)) or tokens(s.context),
                total = s.capacity and tokens(s.capacity) or "?",
                title = tokens(s.context) .. " of " .. (s.capacity and tokens(s.capacity) or "an unreported window") .. " tokens in the last request",
            }),
            line({ ui.span(tokens(s.context) .. (s.capacity and (" / " .. tokens(s.capacity)) or ""), "num") },
                { min = { w = "11ch" }, basis = "content" }),
        })
    end
    if s.output then
        local incoming = (s.input or 0) + (s.cache_read or 0) + (s.cache_write or 0)
        local spans = { ui.span(tokens(s.output), "num"), ui.span(" out", "muted") }
        if incoming > 0 then
            spans[#spans + 1] = ui.span("  ·  ", "dim")
            spans[#spans + 1] = ui.span(tokens(incoming), "num")
            spans[#spans + 1] = ui.span(" in", "muted")
            if s.cache_read and s.cache_read > 0 then
                spans[#spans + 1] = ui.span(string.format("  (%d%% cached)", math.floor(100 * s.cache_read / incoming + 0.5)), "dim")
            end
        end
        rows[#rows + 1] = metric("tokens", "Tokens", { line(spans) })
    end
    if s.cost then
        rows[#rows + 1] = metric("cost", "Cost", { line({ ui.span(string.format("$%.2f", s.cost), "num"), ui.span("  provider estimate", "dim") }) })
    end
    if s.agents then
        rows[#rows + 1] = metric("agents", "Subagents", { line({ ui.span(tostring(s.agents), "num"), ui.span(" spawned", "muted") }) })
    end
    return rows
end

-- omp's git segment: branch *changed ?untracked, then upstream, PR and CI as status segments.
local function delivery_row(row)
    if not row.workspace_branch and not row.git_status then
        local spans = {}
        if row.git_branch then spans = { ui.span(row.git_branch, "strong"), ui.span("  ", "") } end
        spans[#spans + 1] = ui.span(row.collector_note or present(row.workspace_source, "Repository state not observed yet."), "muted")
        return metric("git", "Git", { line(spans, { wrap = true }) })
    end
    local segs = {}
    local branch = { ui.span(present(row.workspace_branch, "unknown"), "strong") }
    local tracked, untracked = (row.git_status or ""):match("(%d+) tracked · (%d+) untracked")
    if tracked and tracked ~= "0" then branch[#branch + 1] = ui.span(" *" .. tracked, "warning") end
    if untracked and untracked ~= "0" then branch[#branch + 1] = ui.span(" ?" .. untracked, "warning") end
    segs[#segs + 1] = ui.node("seg", { icon = "branch", spans = branch, priority = 3 })
    local ahead, behind = (row.git_divergence or ""):match("↑(%d+) ↓(%d+)")
    if ahead and (ahead ~= "0" or behind ~= "0") then
        segs[#segs + 1] = ui.node("seg", { spans = { ui.span("↑" .. ahead .. " ↓" .. behind, "num") }, priority = 2 })
    elseif row.git_divergence == "No upstream" then
        segs[#segs + 1] = ui.node("seg", { spans = { ui.span("not pushed", "muted") }, priority = 2 })
    end
    local pr = row.pr_status
    if pr and pr:match("^#%d+") then
        local text = "PR " .. (pr:match("^(#%d+ · %a+)") or head(pr)):gsub(" · ", " ")
        segs[#segs + 1] = ui.node("seg", { spans = { row.pr_url and row.pr_url:match("^https://")
            and ui.link(text, row.pr_url) or ui.span(text) }, priority = 2 })
    elseif pr == "No open PR" then
        segs[#segs + 1] = ui.node("seg", { spans = { ui.span("no PR", "muted") }, priority = 1 })
    end
    local ci = head(row.ci_status and row.ci_status:gsub("^%a+ HEAD · ", "") or nil)
    if ci and ciTones[ci] then
        segs[#segs + 1] = ui.node("seg", { spans = { ui.span("CI " .. string.lower(ci), ciTones[ci]) }, priority = 2 })
    end
    return metric("git", "Git", { ui.node("status", { transparent = true, grow = 1 }, segs) })
end

local function detail(state)
    local row = selection.current(state)
    if not row then
        return with(ui.col({
            ui.text(state.loaded and "No agent selected" or "Waiting for observations…"),
            ui.text({ ui.span("Open omp, Claude Code, or Codex in a connected Tern session.", "muted") }),
        }), { key = "detail", role = "cockpit.detail" })
    end
    local provider = providers[row.provider] or { label = "Agent" }
    local s = type(row.usage_stats) == "table" and next(row.usage_stats) ~= nil and row.usage_stats or nil
    local children = {
        with(agent_header(row, provider, s), { role = "cockpit.agent" }),
        with(ui.node("row", { gap = "sm", key = "where" }, {
            line({ ui.span(present(row.session, "Unknown session"), "strong") }, { grow = 1 }),
            line({ ui.span(present(row.host, "Unknown host"), "muted") }, { basis = "content" }),
        }), { role = "cockpit.location" }),
        with(line({ ui.path(present(row.cwd, "")) }, { key = "cwd" }), { role = "cockpit.workspace" }),
    }
    local metrics = usage_rows(row, s)
    metrics[#metrics + 1] = delivery_row(row)
    children[#children + 1] = with(ui.col(metrics), { role = "cockpit.metrics" })
    local active = row.status == "working" or row.status == "waiting_input"
    local conversation = {}
    if row.request then conversation[#conversation + 1] = { "Asked", row.request } end
    local response = row.last_response
    if not response and row.provider == "omp" and not active then response = row.activity end
    if response and response ~= row.request and (not active or response ~= row.activity) then
        conversation[#conversation + 1] = { "Said", response }
    end
    if #conversation > 0 then
        children[#children + 1] = with(ui.kv(conversation), { role = "cockpit.conversation" })
    end
    local function details(key, heading, values, note)
        local content = {}
        if #values > 0 then content[#content + 1] = ui.kv(values) end
        if note then content[#content + 1] = ui.text({ ui.span(note, "muted") }) end
        children[#children + 1] = with(ui.section(heading, content), {
            key = key, role = "cockpit.facts", collapsible = true, collapsed = true,
        })
    end
    local hostFacts = { { "Connection", present(row.host_state, "unknown") .. (row.host_remote and " · remote" or " · local") } }
    if row.host_remote and row.host_latency_ms then hostFacts[#hostFacts + 1] = { "Round trip", tostring(row.host_latency_ms) .. " ms" } end
    if row.command and row.command ~= "" then
        hostFacts[#hostFacts + 1] = { row.process_exit ~= nil and "Exited command" or "Current command", row.command }
        hostFacts[#hostFacts + 1] = { "Elapsed", duration(row.command_ms) }
    end
    if row.last_command and row.last_command ~= "" then
        hostFacts[#hostFacts + 1] = { "Last command", row.last_command }
        hostFacts[#hostFacts + 1] = { "Last duration", duration(row.last_command_ms) }
    end
    if row.last_exit ~= nil then hostFacts[#hostFacts + 1] = { "Last command exit", tostring(row.last_exit) } end
    if row.process_exit ~= nil then hostFacts[#hostFacts + 1] = { "Process exit", tostring(row.process_exit) } end
    details("host", "Host & command", hostFacts, nil)
    local sources = {}
    for _, item in ipairs({
        { "Collector", row.collector_note }, { "Phase", row.source }, { "Phase observed", row.observed_at },
        { "Metadata", row.metadata_source }, { "Session tokens", row.session_tokens }, { "Cost", row.session_cost },
        { "Context", row.context_usage }, { "Subagents", row.subagents }, { "Latest call", row.usage },
        { "Usage", row.usage_source }, { "Upstream", row.git_divergence }, { "Pull request", row.pr_status },
        { "CI", row.ci_status }, { "Repository", row.workspace_source }, { "Recorded at", row.updated_at },
        { "Provider session", row.session_id },
    }) do
        if item[2] and item[2] ~= "" then sources[#sources + 1] = item end
    end
    details("sources", "Sources", sources, "Where every value above comes from; recorded data is not proof of live activity.")
    return with(ui.col(children), { key = "detail", role = "cockpit.detail" })
end

function view.render(state, cx)
    -- Nothing paints until the first complete snapshot: one clean entrance, no pop-in.
    if not state.loaded or not state.ready then return { layer = ui.col({ { k = "col", p = { key = "agents" } } }) } end
    local current = selection.current(state)
    local items, order = agents(state, cx)
    return {
        layer = ui.col({
            {
                k = "picker",
                p = {
                    key = "agents", role = "cockpit.picker",
                    aria = "Agent cockpit. j and k select, Enter opens the session, Escape returns.",
                    size = "lg", layout = "cards", query = tern.json.null,
                    preview = "side", selected = current and (current.provider .. ":" .. current.key) or tern.json.null,
                    items = items, order = order, focus = "list",
                    empty = state.loaded and "No detected agent sessions." or "Connecting to this window…",
                    actions = {
                        { id = "focus", label = "Open session", keys = { "enter" }, primary = true },
                        { id = "close", label = "Close", keys = { "esc" }, ["end"] = true },
                    },
                },
                c = { detail(state) },
            },
        }),
    }
end

return view
