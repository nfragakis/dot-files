--!strict
-- Pure discovery: terminal command identity is not evidence of agent activity.
local M = {}

local providers = { omp = "omp", claude = "claude", codex = "codex" }
local utilities = {
    ["--version"] = true, ["--help"] = true, ["-V"] = true, ["-h"] = true,
    login = true, logout = true, completion = true, ["app-server"] = true,
    ["mcp-server"] = true, mcp = true, features = true,
}

function M.clean(value, limit)
    if type(value) ~= "string" then return "" end
    local text = value:gsub("[%z\1-\8\11\12\14-\31\127]", ""):gsub("%s+", " ")
    text = text:match("^%s*(.-)%s*$") or ""
    local at = utf8.offset(text, (limit or 180) + 1)
    return at and (text:sub(1, at - 1) .. "…") or text
end

local function words(line)
    local result, word, quote, escaped = {}, {}, nil, false
    for i = 1, #line do
        local c = line:sub(i, i)
        if escaped then
            word[#word + 1], escaped = c, false
        elseif c == "\\" and quote ~= "'" then
            escaped = true
        elseif quote then
            if c == quote then quote = nil else word[#word + 1] = c end
        elseif c == "'" or c == '"' then
            quote = c
        elseif c:match("[;&|\n]") then
            break
        elseif c:match("%s") then
            if #word > 0 then result[#result + 1], word = table.concat(word), {} end
        else
            word[#word + 1] = c
        end
    end
    if #word > 0 then result[#result + 1] = table.concat(word) end
    return result
end

function M.provider(command)
    if type(command) ~= "string" then return nil end
    local tokens = words(command)
    local i = 1
    while tokens[i] do
        local name = tokens[i]:match("([^/]+)$") or tokens[i]
        if name == "env" or name == "exec" or name == "command" or tokens[i]:match("^[%a_][%w_]*=") then
            i = i + 1
        else
            return providers[name] and not utilities[tokens[i + 1]] and providers[name] or nil
        end
    end
    return nil
end

local function project(cwd, title, provider)
    if title ~= "" and title:lower() ~= provider and not M.provider(title) then return title end
    return (cwd ~= "" and cwd:match("([^/]+)/?$")) or provider
end

function M.collect(panes, agents, hosts, sessions, tabs, results)
    local byAgent, byHost, hostOfPane, bySession, byTab = {}, {}, {}, {}, {}
    for _, agent in ipairs(agents) do byAgent[agent.pane] = agent end
    for _, host in ipairs(hosts) do
        byHost[host.id] = host
        for _, pane in ipairs(host.panes or {}) do hostOfPane[pane] = host end
    end
    for _, session in ipairs(sessions) do bySession[session.id] = session end
    for _, tab in ipairs(tabs) do byTab[tab.id] = tab end
    local rows, targets = {}, {}
    for _, pane in ipairs(panes) do
        local agent = byAgent[pane.pane]
        local command = agent and agent.command
        local provider = agent and (type(command) ~= "string" and "omp" or M.provider(command))
        provider = provider or M.provider(pane.running and pane.running.line) or M.provider(pane.program)
        if provider or agent or pane.kind == "agent" then
            provider = provider or "agent"
            local tab = byTab[pane.tab]
            local session = tab and bySession[tab.session]
            local host = hostOfPane[pane.pane] or (session and byHost[session.host])
            local cwd = M.clean((agent and agent.cwd) or pane.cwd, 300)
            local title = M.clean(pane.title)
            local status, source = "unknown", "Terminal observation · phase unavailable"
            if provider == "omp" and agent then
                status, source = agent.state, "Native omp lifecycle"
                if status == "idle" and results[pane.pane] == "failed" then
                    status, source = "failed", "Native omp · last turn failed"
                end
            elseif agent and agent.state == "waiting_input" then
                status, source = "waiting_input", "Tern input/progress signal"
            end
            if pane.exited ~= nil then
                status = pane.exited == 0 and "exited" or "failed"
                source = "Process exit · code " .. tostring(pane.exited)
            end
            if type(pane.error) == "string" and pane.error ~= "" then
                status, source = "failed", "Tern startup error"
            elseif agent and type(agent.delivery_error) == "string" and agent.delivery_error ~= "" then
                status, source = "failed", "Tern prompt delivery error"
            end
            if host and host.kind == "remote" and host.state ~= "connected" then
                status, source = "unknown", "Host " .. tostring(host.state) .. " · last received data"
            end
            local key = "pane-" .. string.format("%.0f", pane.pane)
            local activity = provider == "omp" and agent and M.clean(agent.last_message) or ""
            activity = activity ~= "" and activity or nil
            local row = {
                key = key, provider = provider, title = project(cwd, title, provider),
                activity = activity, status = status, source = source, cwd = cwd,
                host = host and M.clean(host.name) or "Unknown host",
                session = session and M.clean(session.name) or (pane.parked and "Parked" or "Unknown session"),
                model = agent and type(agent.model) == "string" and M.clean(agent.model, 80) or nil,
                parked = pane.parked == true,
            }
            rows[#rows + 1] = row
            targets[key] = { pane = pane.pane, session = session and session.id, host = host and host.id, parked = row.parked }
        end
    end
    table.sort(rows, function(a, b)
        for _, field in ipairs({ "host", "session", "title", "provider", "key" }) do
            if a[field] ~= b[field] then return a[field] < b[field] end
        end
        return false
    end)
    return rows, targets
end

return M
