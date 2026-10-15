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

-- UTC epoch seconds for a recorded ISO-8601 UTC timestamp (or epoch milliseconds); nil otherwise.
-- Pure arithmetic (days from civil), so the window's local timezone cannot skew it.
function M.epoch(text)
    if type(text) ~= "string" then return nil end
    if text:match("^%d+$") and #text == 13 then return math.floor(tonumber(text) / 1000) end
    local y, mo, d, h, mi, s = text:match("^(%d%d%d%d)-(%d%d)-(%d%d)[T ](%d%d):(%d%d):(%d%d)")
    if not y or not (text:match("Z$") or text:match("[+-]00:?00$")) then return nil end
    y, mo = tonumber(y), tonumber(mo)
    if mo <= 2 then y = y - 1 end
    local era = math.floor(y / 400)
    local yoe = y - era * 400
    local doy = math.floor((153 * ((mo + 9) % 12) + 2) / 5) + tonumber(d) - 1
    local days = era * 146097 + yoe * 365 + math.floor(yoe / 4) - math.floor(yoe / 100) + doy - 719468
    return days * 86400 + tonumber(h) * 3600 + tonumber(mi) * 60 + tonumber(s)
end

-- How long an agent has been in its phase, in whole minutes (ms), or nil when not worth showing.
-- Working agents get no counter. Otherwise the clock starts at an observed transition, else the
-- provider's last recorded activity; with neither, the age is unknown rather than "since we looked".
function M.age(status, now, recorded, transition)
    if status == "working" then return nil end
    local since = transition or recorded
    if not since then return nil end
    local minutes = math.floor(math.max(0, now - since) / 60)
    return minutes >= 1 and minutes * 60000 or nil
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

local function milliseconds(value)
    return type(value) == "number" and value >= 0 and value < math.huge and math.floor(value) or nil
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
            local connected = host and host.state == "connected"
            local running, last = pane.running, pane.last
            local row = {
                key = key, provider = provider, title = project(cwd, title, provider),
                activity = activity, status = status, source = source, cwd = cwd,
                host = host and M.clean(host.name) or "Unknown host",
                session = session and M.clean(session.name) or (pane.parked and "Parked" or "Unknown session"),
                host_key = host and string.format("%.0f", host.id) or "unknown",
                session_key = session and string.format("%.0f", session.id) or (pane.parked and "parked" or "unknown"),
                host_remote = host and host.kind == "remote" or false,
                host_state = host and M.clean(host.state, 40) or "unknown",
                -- Coarse on purpose: per-second values would re-render the whole cockpit every second.
                host_latency_ms = host and host.kind == "remote" and connected and milliseconds(host.rtt_ms)
                    and math.floor(milliseconds(host.rtt_ms) / 10 + 0.5) * 10 or nil,
                command = running and M.clean(running.line, 200) or nil,
                command_ms = running and connected and pane.exited == nil and milliseconds(running.ms)
                    and math.floor(milliseconds(running.ms) / 60000) * 60000 or nil,
                last_command = last and M.clean(last.line, 200) or nil,
                last_command_ms = last and milliseconds(last.took_ms) or nil,
                last_exit = last and last.status or nil,
                process_exit = pane.exited,
                model = agent and type(agent.model) == "string" and M.clean(agent.model, 80) or nil,
                parked = pane.parked == true,
                tab = tab and tab.id or nil,
                tab_color = tab and type(tab.color) == "string" and tab.color or nil,
            }
            rows[#rows + 1] = row
            targets[key] = {
                pane = pane.pane, session = session and session.id, host = host and host.id,
                parked = row.parked, tab = tab and tab.id,
            }
        end
    end
    table.sort(rows, function(a, b)
        for _, field in ipairs({ "session", "session_key", "host", "host_key", "title", "provider", "key" }) do
            if a[field] ~= b[field] then return a[field] < b[field] end
        end
        return false
    end)
    return rows, targets
end

return M
