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

local function label(text)
    return with(ui.text({ ui.span(text, "muted") }), { role = "cockpit.label" })
end

local function agents(state, cx)
    local items, order = {}, {}
    local lastHost, lastSession
    state.page_size = math.max(1, math.floor((cx.rows - 10) / 3))
    for _, row in ipairs(state.rows) do
        local host, session = row.host_key or row.host, row.session_key or row.session
        if host ~= lastHost or session ~= lastSession then
            order[#order + 1] = {
                group = "group:" .. row.key,
                label = present(row.host, "Unknown host") .. "  /  " .. present(row.session, "Unknown session"),
            }
            lastHost, lastSession = host, session
        end
        local info = phase(row)
        local provider = providers[row.provider] or { label = "Agent" }
        local activity = row.activity
        if activity == row.title or activity == row.provider then activity = nil end
        items[#items + 1] = {
            id = row.provider .. ":" .. row.key,
            label = present(row.title, "Untitled agent"),
            detail = provider.label .. "\n" .. present(activity, "Activity not reported"),
            mark = { text = provider.label, seed = row.provider },
            badges = { { text = info.label, tone = info.tone } },
        }
        order[#order + 1] = row.provider .. ":" .. row.key
    end
    return tern.json.array(items), tern.json.array(order)
end

local function detail(state)
    local row = selection.current(state)
    if not row then
        return with(ui.col({
            label("SESSION BRIEF"),
            ui.text(state.loaded and "No agent selected" or "Waiting for observations…"),
            ui.text({ ui.span("Open omp, Claude Code, or Codex in a connected Tern session.", "muted") }),
        }), { key = "detail", role = "cockpit.detail" })
    end
    local info = phase(row)
    local provider = providers[row.provider] or { label = "Agent" }
    local facts = {
        { row.recorded_model and "Recorded model" or "Model", present(row.model, "Not reported") },
    }
    if row.git_branch then facts[#facts + 1] = { "Branch", row.git_branch } end
    local children = {
        with(ui.text(present(row.host, "Unknown host") .. "  /  " .. present(row.session, "Unknown session")),
            { role = "cockpit.location" }),
        with(ui.row({
            ui.node("col", { key = "provider-mark", role = "cockpit.provider." .. row.provider }),
            ui.text({ ui.span(provider.label, "strong") }),
            ui.badge(info.label, info.tone),
            row.parked and ui.badge("Parked", "muted") or ui.text(""),
        }), { role = "cockpit.identity" }),
        with(ui.text(present(row.title, "Selected agent")), { role = "cockpit.title" }),
        with(ui.col({
            label("WORKSPACE"),
            with(ui.text(present(row.cwd, "Not reported")), { role = "cockpit.workspace" }),
            with(ui.kv(facts), { role = "cockpit.metadata" }),
        }), { role = "cockpit.context" }),
    }
    local function section(heading, text, role)
        children[#children + 1] = with(ui.col({
            label(heading),
            with(ui.md(text), { role = "cockpit.prose" }),
        }), { role = role or "cockpit.section" })
    end
    local active = row.status == "working" or row.status == "waiting_input"
    if active then
        section(row.status == "waiting_input" and "NEEDS YOUR ATTENTION" or "CURRENT ACTIVITY",
            present(row.activity, "The provider has not reported its current action."), "cockpit.activity-panel")
    end
    if row.request then section("LATEST REQUEST", row.request) end
    local response = row.last_response
    if not response and row.provider == "omp" and not active then response = row.activity end
    if response and response ~= row.request and (not active or response ~= row.activity) then
        section("LATEST RESPONSE", response)
    end
    if not row.request and not response then
        children[#children + 1] = with(ui.text({
            ui.span("Conversation details have not been reported for this pane.", "muted"),
        }), { role = "cockpit.empty-detail" })
    end
    local observations = {}
    if row.usage then observations[#observations + 1] = { "Usage", row.usage } end
    if row.updated_at then observations[#observations + 1] = { "Recorded at", row.updated_at } end
    if row.observed_at then observations[#observations + 1] = { "Activity observed", row.observed_at } end
    if row.session_id then observations[#observations + 1] = { "Provider session", row.session_id } end
    if #observations > 0 then
        children[#children + 1] = with(ui.col({
            label("RECORDED DETAILS"),
            ui.kv(observations),
        }), { role = "cockpit.records" })
    end
    local sources = { ui.text({ ui.span(present(row.source, "Live state unavailable"), "muted") }) }
    if row.metadata_source and row.metadata_source ~= row.source then
        sources[#sources + 1] = ui.text({ ui.span(row.metadata_source, "muted") })
    end
    children[#children + 1] = with(ui.col(sources), { role = "cockpit.source" })
    return with(ui.col(children), { key = "detail", role = "cockpit.detail" })
end

function view.render(state, cx)
    if not state.loaded then return { layer = ui.col({ { k = "col", p = { key = "agents" } } }) } end
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
