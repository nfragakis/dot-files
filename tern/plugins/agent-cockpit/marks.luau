-- Tab colour flags. Red is the user's own "come back to this"; yellow (an agent
-- is asking) and green (a turn finished and has not been looked at) are automatic.
-- Automatic colours only ever replace a colour this module set itself, so a
-- colour chosen by hand in the tab menu is never overwritten.
local M = {}

M.MANUAL = "red"
M.WAITING = "yellow"
M.DONE = "green"

-- Toggle the manual flag: red clears, anything else becomes red.
function M.toggle(current)
    if current == M.MANUAL then return nil end
    return M.MANUAL
end

-- The automatic colour for one tab's agents: waiting outranks done.
function M.auto(agents)
    local done = false
    for _, agent in ipairs(agents) do
        if agent.status == "waiting_input" then return M.WAITING end
        if agent.done then done = true end
    end
    return done and M.DONE or nil
end

-- Returns the colour changes to apply and updates `owned` (tab -> colour we set).
-- `tabs` is { [tab] = current colour or false }, `wanted` is { [tab] = colour or nil }.
function M.plan(tabs, owned, wanted)
    local changes = {}
    for tab, current in pairs(tabs) do
        current = current or nil
        if current ~= nil and current ~= owned[tab] then
            -- Someone else's colour (manual red included): leave it, forget ours.
            owned[tab] = nil
        else
            local want = wanted[tab]
            if want ~= current then changes[#changes + 1] = { tab = tab, color = want } end
            owned[tab] = want
        end
    end
    for tab in pairs(owned) do
        if tabs[tab] == nil then owned[tab] = nil end
    end
    table.sort(changes, function(a, b) return a.tab < b.tab end)
    return changes
end

return M
