--!strict
-- Window authority stays here; a transient host block supplies the native picker.
local discovery = require("./discovery")
local BLOCK = "agent-cockpit.cockpit"
local SCHEME = "tern-agent-cockpit://"
local token = tostring(os.time()) .. "-" .. tostring(tern.now()):gsub("[^%w]", "") .. "-" .. tostring(math.random(1, 2147483647))
local cockpit, selected, previous, previousSession
local targets, lastResults = {}, {}
local lastSnapshot = ""
local revision, acknowledged = 0, -1
local wireSnapshot = ""
local pending = false
local refresh
local modalReady = false
local dismiss
local metadataCache, metadataBusy = {}, false
local metadataDue, metadataOffset, metadataGeneration = 0, 1, 0


local function send(cx, action, value)
    if cockpit and cx.session:pane(cockpit) then
        cx.session:event(cockpit, { ev = "action", id = "layer.agents", act = action, value = value })
    end
end

local function queue_refresh()
    if pending or not cockpit then return end
    pending = true
    tern.timer(0, function(cx)
        pending = false
        if cx then refresh(cx) end
    end)
end
local function collect_metadata(cx, rows)
    if metadataBusy or tern.now() < metadataDue then return end
    local localPanes, candidates, request, included = {}, {}, {}, {}
    for _, host in ipairs(cx.hosts:list()) do
        if host.kind == "local" then
            for _, pane in ipairs(host.panes or {}) do localPanes[pane] = true end
        end
    end
    for _, row in ipairs(rows) do
        local target = targets[row.key]
        if localPanes[target.pane] and (row.provider == "omp" or row.provider == "claude" or row.provider == "codex")
            and row.status ~= "exited" and row.status ~= "failed" then
            local item = { key = row.key, provider = row.provider, pane = string.format("%.0f", target.pane) }
            candidates[#candidates + 1] = item
            if row.key == selected then request[#request + 1], included[row.key] = item, true end
        end
    end
    if #candidates == 0 then return end
    for offset = 0, math.min(3, #candidates - 1) do
        local index = ((metadataOffset + offset - 1) % #candidates) + 1
        local item = candidates[index]
        if not included[item.key] then request[#request + 1] = item end
    end
    metadataOffset = ((metadataOffset + 3) % #candidates) + 1
    metadataBusy, metadataDue = true, tern.now() + 1500
    local owner, generation = token, metadataGeneration
    tern.process.run({ "python3", tern.plugin.dir .. "/metadata.py" }, {
        stdin = tern.json.encode({ panes = tern.json.array(request) }), timeout_ms = 4000,
    }):next(function(result, _err, currentCx)
        metadataBusy = false
        if owner ~= token or generation ~= metadataGeneration or not cockpit or not currentCx then return end
        if result and result.status == 0 then
            local ok, value = pcall(tern.json.decode, result.stdout)
            if ok and type(value) == "table" and type(value.rows) == "table" then
                for _, item in ipairs(request) do
                    metadataCache[item.key] = type(value.rows[item.key]) == "table" and value.rows[item.key] or nil
                    if metadataCache[item.key] then metadataCache[item.key].provider = item.provider end
                end
                refresh(currentCx)
            end
        end
    end)
end

local function enrich(row, live)
    local cached = metadataCache[row.key]
    if cached and cached.provider ~= row.provider then metadataCache[row.key], cached = nil, nil end
    if not cached then return end
    for _, field in ipairs({ "session_id", "request", "last_response", "git_branch", "updated_at", "usage", "metadata_source" }) do
        if not row[field] then
            local value = discovery.clean(cached[field], 300)
            if value ~= "" then row[field] = value end
        end
    end
    local title = discovery.clean(cached.title, 120)
    if title ~= "" then row.title = title end
    if not row.model then
        local model = discovery.clean(cached.model, 100)
        if model ~= "" then row.model, row.recorded_model = model, true end
    end
    if live and row.provider == "claude" and cached.lifecycle
        and row.status ~= "exited" and row.status ~= "failed" then
        local phase = cached.lifecycle
        row.status, row.activity = phase.status, phase.activity ~= "" and phase.activity or nil
        row.source = "Claude lifecycle hook · " .. phase.event
        row.observed_at = phase.observed_at
    end
end

local function native_metadata(cx, pane, row)
    local messages = cx.agents:transcript(pane, { last = row.key == selected and 30 or 1 })
    local toolFound = false
    for i = #messages, 1, -1 do
        local message = messages[i]
        if row.key == selected and not row.request and message.role == "user" then
            local request = discovery.clean(message.text, 300)
            if request ~= "" then row.request = request end
        end
        if row.key == selected and not row.last_response and message.role == "assistant" then
            local response = discovery.clean(message.text, 300)
            if response ~= "" then row.last_response = response end
        end
        if row.status == "working" and not toolFound then
            local tools = message.tools or {}
            for j = #tools, 1, -1 do
                local tool = tools[j]
                if tool.status == "running" or tool.status == "pending" then
                    local name = discovery.clean(tool.name or tool.title, 50)
                    local target = discovery.clean(tool.target, 120)
                    row.activity = name .. (target ~= "" and (" · " .. target) or "")
                    toolFound = true
                    break
                end
            end
        end
    end
end


refresh = function(cx)
    -- new_block returns before its pane is visible in the window snapshot.
    -- Keep the identity until pane_closed, rather than abandoning first open.
    local pane = cockpit and cx.session:pane(cockpit)
    if not pane then return end
    if pane.exited ~= nil then dismiss(cx, true) return end
    if not modalReady then cx.layout:focus(cockpit) end
    send(cx, "cockpit_ping", token)
    local panes, agents, hosts = cx.session:panes(), cx.agents:list(), cx.hosts:list()
    local live = {}
    for _, item in ipairs(panes) do
        live[item.pane] = item.exited == nil and (not item.error or item.error == "")
    end
    for _, host in ipairs(hosts) do
        if host.kind == "remote" and host.state ~= "connected" then
            for _, id in ipairs(host.panes or {}) do live[id] = false end
        end
    end
    for key in pairs(metadataCache) do
        local id = tonumber(key:match("^pane%-(%d+)$"))
        if not id or live[id] == nil then metadataCache[key] = nil end
    end
    for _, agent in ipairs(agents) do
        if agent.state == "working" then lastResults[agent.pane] = nil end
    end
    local rows
    rows, targets = discovery.collect(panes, agents, hosts, cx.sessions:list(), cx.session:tabs(), lastResults)
    local alive = {}
    for _, row in ipairs(rows) do
        local target = targets[row.key]
        alive[target.pane] = true
        if row.provider == "omp" and (row.status == "working" or row.key == selected) then
            native_metadata(cx, target.pane, row)
        end
        enrich(row, live[target.pane])
    end
    for pane in pairs(lastResults) do if not alive[pane] then lastResults[pane] = nil end end
    collect_metadata(cx, rows)
    local payload = { token = token, rows = tern.json.array(rows) }
    local snapshot = tern.json.encode(payload)
    if snapshot ~= lastSnapshot then
        revision = revision + 1
        payload.revision = revision
        wireSnapshot = tern.json.encode(payload)
        lastSnapshot = snapshot
    end
    if acknowledged ~= revision then
        if acknowledged == -1 then send(cx, "cockpit_claim", token) end
        send(cx, "cockpit_snapshot", wireSnapshot)
    end
end

local function claim(cx, pane)
    cockpit, selected, lastSnapshot, acknowledged = pane, "pane-" .. string.format("%.0f", previous), "", -1
    metadataCache, metadataDue, metadataOffset = {}, 0, 1
    metadataGeneration = metadataGeneration + 1
    send(cx, "cockpit_claim", token)
    refresh(cx)
end

dismiss = function(cx, restore)
    local pane = cockpit
    cockpit, selected, targets = nil, nil, {}
    modalReady = false
    if pane and cx.session:pane(pane) then cx.layout:close(pane) end
    if restore and previous and cx.session:pane(previous) then
        if previousSession then cx.sessions:switch(previousSession) end
        cx.layout:focus(previous)
    end
end

local function open(cx)
    local focused = cx.session:focused()
    if cockpit and focused == cockpit then dismiss(cx, true) return end
    if cockpit then dismiss(cx, false) end
    if not focused then
        cx:toast("info", "Open a pane before opening Agent Cockpit")
        return
    end
    previous = focused
    local session = cx.sessions:current()
    previousSession = session and session.id
    token = tostring(os.time()) .. "-" .. tostring(tern.now()):gsub("[^%w]", "") .. "-" .. tostring(math.random(1, 2147483647))
    local pane = cx:new_block(BLOCK, { token, "pane-" .. string.format("%.0f", previous) }, "beside")
    if not pane then
        cx:toast("error", "Agent Cockpit is not installed on this host", "Run install-tern-cockpit.py on the host owning this pane.")
        return
    end
    -- Float in the same UI transaction as creation: never paint a temporary split.
    local ok, err = cx.layout:float(pane, previous)
    if not ok then
        cx.layout:close(pane)
        cx:toast("error", "Could not open Agent Cockpit overlay", err)
        return
    end
    cx.layout:focus(pane)
    claim(cx, pane)
end

tern.command({
    id = "open", title = "Agent Cockpit", icon = "sparkle", group = "Agents",
    run = open,
})

tern.route.link(function(link, cx)
    if link.url:sub(1, #SCHEME) ~= SCHEME then return nil end
    local verb, owner, key = link.url:sub(#SCHEME + 1):match("^([^/]+)/([^/]+)/?(.*)$")
    -- Consume our private protocol in every window; only its owner acts on it.
    if owner ~= token then return { handled = true } end
    if verb == "ack" then
        if tonumber(key) == revision then acknowledged, modalReady = revision, true end
    elseif verb == "select" then
        if targets[key] then
            selected = key
            queue_refresh()
        end
    elseif verb == "refresh" then
        lastSnapshot = ""
        queue_refresh()
    elseif verb == "return" then
        dismiss(cx, true)
    elseif verb == "focus" then
        local target = targets[key]
        if not target or not cx.session:pane(target.pane) then
            cx:toast("info", "That agent is no longer available")
            queue_refresh()
        else
            if target.session then cx.sessions:switch(target.session)
            elseif target.host then cx.hosts:switch(target.host) end
            if target.parked then
                local ok, err = cx.layout:unpark(target.pane)
                if not ok then cx:toast("error", "Could not show parked agent", err) return { handled = true } end
            end
            dismiss(cx, false)
            cx.layout:focus(target.pane)
        end
    end
    return { handled = true }
end)

tern.on("agent_finished", function(event, _cx)
    lastResults[event.pane] = event.result
    queue_refresh()
end)
tern.on("pane_closed", function(event, _cx)
    local key = "pane-" .. string.format("%.0f", event.pane)
    metadataCache[key] = nil
    if event.pane == cockpit then
        cockpit, selected, lastSnapshot = nil, nil, ""
        targets = {}
    end
end)
for _, name in ipairs({ "command_started", "command_finished" }) do
    tern.on(name, function(event, _cx)
        metadataCache["pane-" .. string.format("%.0f", event.pane)] = nil
        metadataDue, metadataGeneration = 0, metadataGeneration + 1
    end)
end
for _, event in ipairs({ "pane_created", "title" }) do
    tern.on(event, function(event, cx)
        if event.pane == cockpit then
            -- Deliver the first frame immediately; an occluded window may defer timers.
            refresh(cx)
        else
            queue_refresh()
        end
    end)
end
for _, event in ipairs({ "pane_closed", "tab_created", "tab_closed", "cwd", "command_started", "command_finished" }) do
    tern.on(event, function(_event, _cx) queue_refresh() end)
end
tern.on("focus", function(_event, cx)
    if cockpit and modalReady and cx.session:focused() ~= cockpit then dismiss(cx, false) end
end)

-- A timer also observes progress changes, which have no public change event.
local function poll(cx)
    if cx and cockpit then refresh(cx) end
    tern.timer(1000, poll)
end
tern.timer(1000, poll)
