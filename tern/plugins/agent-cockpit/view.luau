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
    local items = {}
    state.page_size = math.max(1, math.floor((cx.rows - 10) / 3))
    for _, row in ipairs(state.rows) do
        local info = phase(row)
        local provider = providers[row.provider]
        local activity = row.activity
        if activity == row.title or activity == row.provider then activity = nil end
        items[#items + 1] = {
            id = row.provider .. ":" .. row.key,
            label = present(row.title, "Untitled agent"),
            detail = provider.label .. " · "
                .. present(row.host, "Unknown host") .. " / " .. present(row.session, "Unknown session")
                .. "\n" .. present(activity, "Activity not reported"),
            mark = { text = provider.label, seed = row.provider },
            badges = { { text = info.label, tone = info.tone } },
        }
    end
    return tern.json.array(items)
end

local function detail(state, cx)
    local row = selection.current(state)
    if not row then
        return with(ui.col({
            label("DETAILS"),
            ui.text(state.loaded and "Open omp, claude, or codex in a Tern pane." or "Waiting for observations…"),
            ui.text({ ui.span("Select a session with j / k. Enter jumps to its pane.", "muted") }),
        }), { key = "detail", role = "cockpit.detail", grow = 1, basis = 0.64 })
    end
    local info = phase(row)
    local provider = providers[row.provider]
    local mark = ui.node("col", { key = "provider-mark", role = "cockpit.provider." .. row.provider })
    local facts = {
        { row.recorded_model and "Recorded model" or "Model", present(row.model, "Not reported") },
    }
    if row.git_branch then facts[#facts + 1] = { "Branch", row.git_branch } end
    facts[#facts + 1] = { "Host / session", present(row.host, "Unknown") .. " / " .. present(row.session, "Unknown") }
    if row.usage then facts[#facts + 1] = { "Recorded usage", row.usage } end
    if row.session_id then facts[#facts + 1] = { "Session", row.session_id } end
    if row.updated_at then facts[#facts + 1] = { "Updated", row.updated_at } end
    local children = {
        with(ui.row({
            mark,
            ui.text({ ui.span(provider.label, "strong") }),
            ui.badge(info.label, info.tone),
            row.parked and ui.badge("Parked", "muted") or ui.text(""),
        }), { role = "cockpit.identity" }),
        with(ui.text(present(row.title, "Selected agent")), { role = "cockpit.title", lines = 2 }),
        with(ui.text(present(row.cwd, "Workspace unavailable")), { role = "cockpit.workspace", lines = 1 }),
        with(ui.kv(facts), { role = "cockpit.metadata" }),
    }
    if row.activity and row.activity ~= row.provider and row.activity ~= row.title then
        children[#children + 1] = with(ui.col({
            label(row.status == "working" and "CURRENT ACTIVITY" or "LAST OBSERVATION"),
            with(ui.text(row.activity), { role = "cockpit.activity", lines = 3 }),
        }), { role = "cockpit.activity-panel" })
    end
    if row.request then
        children[#children + 1] = label("LATEST REQUEST")
        children[#children + 1] = with(ui.text(row.request), { lines = 4 })
    end
    if row.last_response and row.last_response ~= row.activity and row.status ~= "working" then
        children[#children + 1] = label("LAST RESPONSE")
        children[#children + 1] = with(ui.text(row.last_response), { lines = 4 })
    end
    children[#children + 1] = with(ui.text({
        ui.span(present(row.metadata_source, present(row.source, "Telemetry unavailable")), "muted"),
    }), {
        role = "cockpit.source", lines = 1,
        title = row.session_id and ("Session " .. row.session_id .. (row.updated_at and " · " .. row.updated_at or "")) or nil,
    })
    return with(ui.col(children), { key = "detail", role = "cockpit.detail" })
end

function view.render(state, cx)
    if not state.loaded then return { layer = ui.col({ { k = "col", p = { key = "agents" } } }) } end
    local current = selection.current(state)
    return {
        layer = ui.col({
            {
                k = "picker",
                p = {
                    key = "agents", role = "cockpit.picker",
                    aria = "Agent cockpit. j and k select, Enter opens the session, Escape returns.",
                    size = "lg", layout = "cards", query = tern.json.null,
                    preview = "side", selected = current and (current.provider .. ":" .. current.key) or tern.json.null,
                    items = agents(state, cx), focus = "list",
                    empty = state.loaded and "No detected agent sessions." or "Connecting to this window…",
                    actions = {
                        { id = "focus", label = "Open session", keys = { "enter" }, primary = true },
                        { id = "close", label = "Close", keys = { "esc" }, ["end"] = true },
                    },
                },
                c = { detail(state, cx) },
            },
        }),
    }
end

return view
