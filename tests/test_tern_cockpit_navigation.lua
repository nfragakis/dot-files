local navigation = dofile("tern/plugins/agent-cockpit/navigation.luau")

local function scenario(broken)
    local target = 21998822490125
    local state = { focused = 1, commands = {}, timers = {}, effects = {}, completed = nil, valid = true }
    local panes = { {pane=1,tab=10}, {pane=2,tab=20}, {pane=target,tab=20} }
    local function find(id)
        for _, pane in ipairs(panes) do if pane.pane == id then return pane end end
    end
    local cx = {
        session = {
            focused = function() return state.focused end,
            panes = function() return panes end,
            tabs = function() return {{id=10},{id=20}} end,
            pane = function(_, id)
                if id == "@focused" then return find(state.focused) end
                if not (broken and id == target) then return find(id) end
            end,
        },
        layout = { focus = function(_, id)
            assert(not (broken and id == target), "sent an unresolvable remote id back to layout")
            state.effects[#state.effects+1] = function() state.focused = id end
        end },
        command = function(_, command)
            state.commands[#state.commands+1] = command
            state.effects[#state.effects+1] = function()
                if state.stuck then return end
                if command == "next_tab_across_sessions" then
                    state.focused = state.focused == 1 and 2 or 1
                else
                    assert(command == "next_pane")
                    state.focused = state.focused == 2 and target or 2
                end
            end
        end,
    }
    tern = {timer=function(_, fn) state.timers[#state.timers+1] = fn end}
    navigation.focus(cx, target, function() return state.valid end, function(_, ok, err)
        state.completed, state.error = ok, err
    end)
    local function drain()
        local count = 0
        while #state.timers > 0 do
            count = count + 1
            assert(count < 32, "native focus did not terminate")
            local effects = state.effects
            state.effects = {}
            for _, effect in ipairs(effects) do
                local before = state.focused
                effect()
                if before ~= state.focused then navigation.observe(cx) end
            end
            if state.interrupt and #effects > 0 then
                state.interrupt = false
                state.focused = 1
                navigation.observe(cx)
            end
            table.remove(state.timers, 1)(cx)
        end
    end
    return state, panes, drain, target
end

local direct, _, drain, target = scenario(false)
drain()
assert(direct.completed and direct.focused == target and #direct.commands == 0)

local remote, _, drain_remote, remote_target = scenario(true)
drain_remote()
assert(remote.completed and remote.focused == remote_target)
assert(remote.commands[1] == "next_tab_across_sessions" and remote.commands[2] == "next_pane")

local cancelled, _, drain_cancelled = scenario(true)
cancelled.valid = false
drain_cancelled()
assert(cancelled.focused == 1 and cancelled.completed == nil and #cancelled.commands == 0)

local superseded, _, drain_superseded = scenario(true)
superseded.interrupt = true
drain_superseded()
assert(superseded.focused == 1 and superseded.completed == nil and #superseded.commands == 1,
    "queued navigation overrode a newer manual selection")

local missing, panes, drain_missing = scenario(true)
table.remove(panes)
drain_missing()
assert(missing.completed == false and missing.error:find("no longer available", 1, true))
assert(missing.focused == 1 and #missing.commands == 0)

local stuck, _, drain_stuck = scenario(true)
stuck.stuck = true
drain_stuck()
assert(stuck.completed == false and stuck.error:find("could not focus", 1, true))
assert(stuck.focused == 1)
print("cockpit native navigation: ok")
