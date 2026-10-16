--!strict
-- Window authority stays here; a transient host block supplies the native picker.
local discovery = require("./discovery")
local marks = require("./marks")
local BLOCK = "agent-cockpit.cockpit"
local SCHEME = "tern-agent-cockpit://"
local token = tostring(os.time()) .. "-" .. tostring(tern.now()):gsub("[^%w]", "") .. "-" .. tostring(math.random(1, 2147483647))
local cockpit, selected, previous, previousSession
local targets, lastResults = {}, {}
local lastSnapshot = ""
local revision, acknowledged = 0, -1
local wireSnapshot = ""
local pending, refreshJob, refreshAgain
local STEP_MS = 16
local refresh
local modalReady = false
local dismiss
-- Per host id: one collector run in flight, its next due time and round-robin position.
local metadataCache, metadataBusy = {}, {}
local metadataDue, metadataOffset, metadataGeneration = {}, {}, 0
local workspaceCache, workspaceBusy, workspaceDue = {}, false, 0
-- Tab flags and per-agent phase history; these run whether or not the cockpit is open.
local ownedColors, doneUnseen, phaseSince = {}, {}, {}
local lifecycleCache, lifecycleBusy, lifecycleDue = {}, {}, 0
local STALE_MS = 60 * 60 * 1000
local workspaceFields = {
    "workspace_branch", "git_status", "git_divergence", "pr_status", "pr_url", "ci_status", "workspace_source",
}


local function send(cx, action, value)
    if cockpit and cx.session:pane(cockpit) then
        cx.session:event(cockpit, { ev = "action", id = "layer.agents", act = action, value = value })
    end
end

local function queue_refresh()
    if pending or not cockpit then return end
    local ticket, owner, pane = {}, token, cockpit
    pending = ticket
    tern.timer(STEP_MS, function(cx)
        if pending ~= ticket then return end
        pending = nil
        if cx and token == owner and cockpit == pane then refresh(cx) end
    end)
end
-- Each host's own collector reads its own processes and records. Remote panes are
-- numbered host.id * 2^44 + that host's pane id (the TERN_PANE its programs see).
local PROTOCOL = 3
local HOST_SHIFT = 2 ^ 44
local REMOTE_COLLECTOR = 'PATH="$HOME/.local/bin:$PATH"; TERN_DAEMON_SOCKET="/run/user/$(id -u)/tern/daemon.sock"; '
    .. 'export PATH TERN_DAEMON_SOCKET; '
    .. 'd=$(cat "${XDG_CONFIG_HOME:-$HOME/.config}/tern/plugins/agent-cockpit.path" 2>/dev/null) || exit 3; '
    .. 'exec python3 "$d/metadata.py"'
local hostNotes = {}

local function placement(cx)
    local result = {}
    for _, host in ipairs(cx.hosts:list()) do
        local reachable = host.kind == "local" or (host.state == "connected" and type(host.address) == "string"
            and host.address:match("^[%w._-]+@?[%w._-]*$") ~= nil and host.address:sub(1, 1) ~= "-")
        if reachable then
            for _, pane in ipairs(host.panes or {}) do
                local id = host.kind == "local" and pane or pane - host.id * HOST_SHIFT
                if id > 0 and id == math.floor(id) then result[pane] = { host = host, id = string.format("%.0f", id) } end
            end
        end
    end
    return result
end

-- Runs metadata.py on `host` (ssh for remote hosts, one shared connection) and hands back its rows.
local function collect(host, items, done)
    local argv, timeout = { "python3", tern.plugin.dir .. "/metadata.py" }, 4000
    if host.kind ~= "local" then
        argv, timeout = {
            "ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4",
            "-o", "ControlMaster=auto", "-o", "ControlPath=~/.ssh/agent-cockpit-%C", "-o", "ControlPersist=300",
            "--", host.address, REMOTE_COLLECTOR,
        }, 9000
    end
    tern.process.run(argv, {
        stdin = tern.json.encode({ panes = tern.json.array(items) }), timeout_ms = timeout,
    }):next(function(result, _err, cx)
        local value, note
        if result and result.status == 0 then
            local ok, decoded = pcall(tern.json.decode, result.stdout)
            if ok and type(decoded) == "table" and type(decoded.rows) == "table" then value = decoded end
        end
        if value and value.protocol ~= PROTOCOL then
            value, note = nil, host.name .. " runs an older Agent Cockpit; pull and run ./install-tern-cockpit.py there"
        elseif not value then
            local status = result and result.status
            note = status == 3 and ("Agent Cockpit is not installed on " .. host.name)
                or status == 255 and ("Could not reach " .. host.name .. " over ssh")
                or ("Metadata collector failed on " .. host.name)
        end
        hostNotes[host.id] = note
        done(value and value.rows or nil, cx)
    end)
end

local function collect_metadata(cx, rows)
    local where, perHost = placement(cx), {}
    for _, row in ipairs(rows) do
        local place = where[targets[row.key].pane]
        if place and (row.provider == "omp" or row.provider == "claude" or row.provider == "codex")
            and row.status ~= "exited" and row.status ~= "failed" then
            local group = perHost[place.host.id] or { host = place.host, items = {} }
            perHost[place.host.id] = group
            local item = { key = row.key, provider = row.provider, pane = place.id }
            if row.key == selected then group.selected = item else group.items[#group.items + 1] = item end
        end
    end
    for id, group in pairs(perHost) do
        if not metadataBusy[id] and tern.now() >= (metadataDue[id] or 0) then
            -- The selected agent every round; the rest round-robin, four at a time.
            local request, count = { group.selected }, #group.items
            for offset = 0, math.min(3, count - 1) do
                request[#request + 1] = group.items[(((metadataOffset[id] or 1) + offset - 1) % count) + 1]
            end
            if count > 0 then metadataOffset[id] = (((metadataOffset[id] or 1) + 3) % count) + 1 end
            metadataBusy[id], metadataDue[id] = true, tern.now() + (group.host.kind == "local" and 1500 or 2500)
            local owner, generation = token, metadataGeneration
            collect(group.host, request, function(found, currentCx)
                metadataBusy[id] = false
                if owner ~= token or generation ~= metadataGeneration or not cockpit or not currentCx then return end
                if found then
                    for _, item in ipairs(request) do
                        metadataCache[item.key] = type(found[item.key]) == "table" and found[item.key] or nil
                        if metadataCache[item.key] then metadataCache[item.key].provider = item.provider end
                    end
                end
                queue_refresh()
            end)
        end
    end
end

local function workspace_metadata(cx, row)
    if not row then return end
    local cached = workspaceCache[row.key]
    if cached and (cached.provider ~= row.provider or cached.cwd ~= row.cwd) then
        workspaceCache[row.key], cached, workspaceDue = nil, nil, 0
    end
    if cached then
        for _, field in ipairs(workspaceFields) do
            local value = discovery.clean(cached[field], field == "pr_url" and 1000 or 300)
            if value ~= "" then row[field] = value end
        end
    end
    if workspaceBusy or tern.now() < workspaceDue or row.status == "exited" or row.status == "failed" then return end
    local place = placement(cx)[targets[row.key].pane]
    if not place then return end
    workspaceBusy, workspaceDue = true, tern.now() + 10000
    local owner, generation, key, cwd, provider = token, metadataGeneration, row.key, row.cwd, row.provider
    collect(place.host, { { key = key, provider = provider, pane = place.id, workspace = true } }, function(found, currentCx)
        workspaceBusy = false
        if owner ~= token or generation ~= metadataGeneration or not cockpit or not currentCx then return end
        local value = found and type(found[key]) == "table" and found[key]
            or { workspace_source = hostNotes[place.host.id] or "Workspace lookup unavailable for the exact process" }
        value.provider, value.cwd = provider, cwd
        workspaceCache[key] = value
        queue_refresh()
    end)
end

local function enrich(row, live)
    local cached = metadataCache[row.key]
    if cached and cached.provider ~= row.provider then metadataCache[row.key], cached = nil, nil end
    if not cached then return end
    for _, field in ipairs({
        "session_id", "request", "last_response", "git_branch", "updated_at", "usage", "metadata_source",
        "session_tokens", "session_cost", "context_usage", "subagents", "usage_source",
    }) do
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
    if type(cached.usage_stats) == "table" then row.usage_stats = cached.usage_stats end
end

-- The newest exact hook phase wins, from either the full or the background probe.
local function apply_lifecycle(row, live)
    if not live or row.provider ~= "claude" or row.status == "exited" or row.status == "failed" then return end
    local phase
    for _, cache in ipairs({ metadataCache[row.key], lifecycleCache[row.key] }) do
        local candidate = cache and cache.provider == row.provider and cache.lifecycle
        if candidate and (not phase or candidate.observed_at > phase.observed_at) then phase = candidate end
    end
    if not phase then return end
    row.status, row.activity = phase.status, phase.activity ~= "" and phase.activity or nil
    row.source = "Claude lifecycle hook · " .. phase.event
    row.observed_at = phase.observed_at
end

-- Claude phases come from hook records on each host; probe them so tabs colour while the cockpit is closed.
local function probe_lifecycle(cx, rows, rowTargets)
    -- With the cockpit open, the full metadata collection already carries lifecycle.
    if cockpit or tern.now() < lifecycleDue then return end
    local where, perHost = placement(cx), {}
    for _, row in ipairs(rows) do
        local place = where[rowTargets[row.key].pane]
        if place and row.provider == "claude" and row.status ~= "exited" and row.status ~= "failed" then
            local group = perHost[place.host.id] or { host = place.host, items = {} }
            perHost[place.host.id] = group
            group.items[#group.items + 1] = { key = row.key, provider = row.provider, pane = place.id, lifecycle = true }
        end
    end
    for key in pairs(lifecycleCache) do
        if not rowTargets[key] then lifecycleCache[key] = nil end
    end
    lifecycleDue = tern.now() + 2000
    for id, group in pairs(perHost) do
        if not lifecycleBusy[id] then
            lifecycleBusy[id] = true
            collect(group.host, group.items, function(found)
                lifecycleBusy[id] = false
                if not found then return end
                for _, item in ipairs(group.items) do
                    local value = found[item.key]
                    lifecycleCache[item.key] = type(value) == "table" and type(value.lifecycle) == "table"
                        and { provider = item.provider, lifecycle = value.lifecycle } or nil
                end
            end)
        end
    end
end

-- Phase history drives idle age, the "finished, not yet looked at" flag and automatic tab colours.
local function track(cx, rows)
    local now, focusedTab = os.time(), nil
    local focused = cx.session:focused()
    local focusedPane = focused and cx.session:pane(focused)
    if focusedPane then focusedTab = focusedPane.tab end
    local seen, byTab = {}, {}
    for _, row in ipairs(rows) do
        seen[row.key] = true
        local previous = phaseSince[row.key]
        if not previous or previous.status ~= row.status then
            if previous and previous.status == "working" and row.status == "idle" then doneUnseen[row.key] = true end
            -- First sight is not a transition: a reload must not restart every agent's clock together.
            phaseSince[row.key] = { status = row.status, at = previous and now or nil }
        end
        if row.status == "working" or row.status == "waiting_input" or (row.tab and row.tab == focusedTab) then
            doneUnseen[row.key] = nil
        end
        local recorded = math.max(discovery.epoch(row.updated_at) or 0, discovery.epoch(row.observed_at) or 0)
        -- Whole minutes only: the snapshot (and every native meter in it) changes at most once a minute.
        row.phase_ms = discovery.age(row.status, now, recorded > 0 and recorded or nil, phaseSince[row.key].at)
        row.done_unseen = doneUnseen[row.key] == true
        row.stale = (row.status == "idle" or row.status == "unknown") and (row.phase_ms or 0) >= STALE_MS
        row.flagged = row.tab_color == marks.MANUAL and ownedColors[row.tab] ~= marks.MANUAL
        if row.tab then
            byTab[row.tab] = byTab[row.tab] or {}
            table.insert(byTab[row.tab], { status = row.status, done = row.done_unseen })
        end
    end
    for key in pairs(phaseSince) do
        if not seen[key] then phaseSince[key], doneUnseen[key] = nil, nil end
    end
    local tabs, wanted = {}, {}
    for _, tab in ipairs(cx.session:tabs()) do tabs[tab.id] = tab.color or false end
    for tab, agents in pairs(byTab) do wanted[tab] = marks.auto(agents) end
    for _, change in ipairs(marks.plan(tabs, ownedColors, wanted)) do
        cx.layout:color_tab(change.tab, change.color)
    end
end


local function liveness(panes, hosts)
    local live = {}
    for _, item in ipairs(panes) do
        live[item.pane] = item.exited == nil and (not item.error or item.error == "")
    end
    for _, host in ipairs(hosts) do
        if host.kind == "remote" and host.state ~= "connected" then
            for _, id in ipairs(host.panes or {}) do live[id] = false end
        end
    end
    return live
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


local function publish(cx, rows)
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

-- Each stage gets a fresh window context and a separate callback budget. A closed,
-- reopened, reselected or invalidated cockpit must never receive an old stage.
local function defer(job, work)
    tern.timer(STEP_MS, function(cx)
        if refreshJob ~= job then return end
        if not cx or token ~= job.owner or cockpit ~= job.pane
            or selected ~= job.selected or metadataGeneration ~= job.generation then
            refreshJob, refreshAgain = nil, false
            if cx then queue_refresh() end
            return
        end
        if cockpit then
            local pane = cx.session:pane(cockpit)
            if not pane or pane.exited ~= nil then
                refreshJob = nil
                if pane then dismiss(cx, true) end
                return
            end
        end
        work(cx)
    end)
end

local function finish_refresh(cx, job)
    track(cx, job.rows)
    if job.pane then
        publish(cx, job.rows)
        defer(job, function(current)
            collect_metadata(current, job.rows)
            refreshJob = nil
            if refreshAgain then refreshAgain = false queue_refresh() end
        end)
    else
        probe_lifecycle(cx, job.rows, job.targets)
        refreshJob = nil
    end
end

local function enrich_next(job, index)
    defer(job, function(cx)
        local row = job.rows[index]
        if not row then
            finish_refresh(cx, job)
            return
        end
        local target = job.targets[row.key]
        if cx.session:pane(target.pane) then
            if row.provider == "omp" and (row.status == "working" or row.key == selected) then
                native_metadata(cx, target.pane, row)
            end
            enrich(row, job.live[target.pane])
            apply_lifecycle(row, job.live[target.pane])
            if row.key == selected then workspace_metadata(cx, row) end
        end
        enrich_next(job, index + 1)
    end)
end

refresh = function(cx)
    if refreshJob then refreshAgain = true return end
    if cockpit then
        local pane = cx.session:pane(cockpit)
        -- Creation can precede visibility in the window snapshot; pane_created
        -- will schedule the first observation without doing work in that event.
        if not pane then return end
        if pane.exited ~= nil then dismiss(cx, true) return end
        send(cx, "cockpit_ping", token)
    end
    local job = { owner = token, pane = cockpit, selected = selected, generation = metadataGeneration }
    refreshJob, refreshAgain = job, false
    defer(job, function(current)
        job.agents = current.agents:list()
        for _, agent in ipairs(job.agents) do
            if agent.state == "working" then lastResults[agent.pane] = nil end
        end
        defer(job, function(current)
            job.panes, job.hosts = current.session:panes(), current.hosts:list()
            job.sessions, job.tabs = current.sessions:list(), current.session:tabs()
            job.live = liveness(job.panes, job.hosts)
            defer(job, function(current)
                job.rows, job.targets = discovery.collect(job.panes, job.agents, job.hosts,
                    job.sessions, job.tabs, lastResults)
                defer(job, function(current)
                    for _, row in ipairs(job.rows) do
                        apply_lifecycle(row, job.live[job.targets[row.key].pane])
                    end
                    if not job.pane then finish_refresh(current, job) return end
                    targets = job.targets
                    for key in pairs(metadataCache) do
                        if not targets[key] then metadataCache[key] = nil end
                    end
                    for key in pairs(workspaceCache) do
                        if not targets[key] or not job.live[targets[key].pane] then workspaceCache[key] = nil end
                    end
                    for pane in pairs(lastResults) do
                        if job.live[pane] == nil then lastResults[pane] = nil end
                    end
                    local where = placement(current)
                    for _, row in ipairs(job.rows) do
                        local place = where[targets[row.key].pane]
                        row.collector_note = place and hostNotes[place.host.id] or nil
                        enrich(row, job.live[targets[row.key].pane])
                    end
                    -- Discoveries appear without waiting for transcripts or ssh.
                    -- Later refreshes retain the enriched view until replacement.
                    if lastSnapshot == "" then publish(current, job.rows) end
                    enrich_next(job, 1)
                end)
            end)
        end)
    end)
end

local function claim(cx, pane)
    cockpit, selected, lastSnapshot, acknowledged = pane, "pane-" .. string.format("%.0f", previous), "", -1
    -- Retain exact-pane caches across opens, but cancel every previous UI job.
    pending, refreshJob, refreshAgain = nil, nil, false
    metadataDue, workspaceDue = {}, 0
    metadataGeneration = metadataGeneration + 1
    send(cx, "cockpit_claim", token)
    queue_refresh()
end

dismiss = function(cx, restore)
    local pane = cockpit
    cockpit, selected, targets = nil, nil, {}
    modalReady = false
    pending, refreshJob, refreshAgain = nil, nil, false
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
            workspaceDue = 0
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
    -- A turn shorter than one poll never shows as working; record it directly.
    doneUnseen["pane-" .. string.format("%.0f", event.pane)] = true
    queue_refresh()
end)
tern.on("pane_closed", function(event, _cx)
    local key = "pane-" .. string.format("%.0f", event.pane)
    metadataCache[key] = nil
    workspaceCache[key] = nil
    lifecycleCache[key], doneUnseen[key], phaseSince[key] = nil, nil, nil
    if event.pane == cockpit then
        cockpit, selected, lastSnapshot = nil, nil, ""
        targets = {}
        pending, refreshJob, refreshAgain = nil, nil, false
    end
end)
for _, name in ipairs({ "command_started", "command_finished", "cwd" }) do
    tern.on(name, function(event, _cx)
        metadataCache["pane-" .. string.format("%.0f", event.pane)] = nil
        workspaceCache["pane-" .. string.format("%.0f", event.pane)] = nil
        workspaceDue = 0
        metadataDue, metadataGeneration = {}, metadataGeneration + 1
    end)
end
for _, event in ipairs({ "pane_created", "title" }) do
    tern.on(event, function(_event, _cx) queue_refresh() end)
end
for _, event in ipairs({ "pane_closed", "tab_created", "tab_closed", "cwd", "command_started", "command_finished" }) do
    tern.on(event, function(_event, _cx) queue_refresh() end)
end
tern.on("focus", function(_event, cx)
    if cockpit and modalReady and cx.session:focused() ~= cockpit then dismiss(cx, false) end
end)

local function toggle_flag(cx)
    -- In the cockpit, flag the selected agent's tab; elsewhere, the focused pane's tab.
    local focused, tab = cx.session:focused(), nil
    if cockpit and focused == cockpit and selected and targets[selected] then
        tab = targets[selected].tab
    else
        local pane = focused and cx.session:pane(focused)
        tab = pane and pane.tab
    end
    if not tab then
        cx:toast("info", "No tab to flag")
        return
    end
    local current
    for _, info in ipairs(cx.session:tabs()) do
        if info.id == tab then current = info.color end
    end
    local color = marks.toggle(current)
    cx.layout:color_tab(tab, color)
    ownedColors[tab] = nil
    cx:toast("info", color and "Flagged to revisit" or "Revisit flag cleared")
    lastSnapshot = ""
    queue_refresh()
end

tern.command({ id = "toggle_flag", title = "Flag Tab to Revisit", icon = "sparkle", group = "Agents", run = toggle_flag })
-- Settings keybinds load only at window start or Ctrl+S R; the plugin binds its own chord too.
tern.bind("ctrl+s>b", toggle_flag)

-- A timer also observes progress changes, which have no public change event.
-- With the cockpit closed it still tracks phases so tab colours follow agents.
local function poll(cx)
    if cx then refresh(cx) end
    tern.timer(1000, poll)
end
tern.timer(1000, poll)
