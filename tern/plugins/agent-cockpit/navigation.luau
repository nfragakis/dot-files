-- Pane ids are opaque observations. Focus through native actions when the
-- window cannot resolve an id it returned (Tern 0.9 remote namespace bug).
local navigation = {}
local active

function navigation.observe(cx)
    if not active then return end
    local focused = cx.session:focused()
    if active.waiting then
        active.waiting, active.expected = false, focused
    elseif focused ~= active.expected then
        active.cancelled = true
    end
end

function navigation.focus(cx, pane, valid, done)
    local remaining = #cx.session:panes() + #cx.session:tabs() + 2
    local job = {}
    local function step(current)
        if not valid() or job.cancelled then return end
        if not active or active ~= job then active = job end
        local focused = current.session:focused()
        if job.expected and not job.waiting and focused ~= job.expected then return end
        job.waiting, job.expected = false, focused
        if current.session:focused() == pane then done(current, true) return end
        local target
        for _, info in ipairs(current.session:panes()) do
            if info.pane == pane then
                if target then done(current, false, "Tern returned an ambiguous pane identity") return end
                target = info
            end
        end
        if not target then done(current, false, "That pane is no longer available") return end
        job.waiting = true
        if current.session:pane(pane) then
            current.layout:focus(pane)
        elseif remaining > 0 then
            local focused = current.session:pane("@focused")
            current:command(focused and focused.tab == target.tab and "next_pane" or "next_tab_across_sessions")
        else
            done(current, false, "Tern could not focus the selected pane")
            return
        end
        remaining = remaining - 1
        if remaining < 0 then done(current, false, "Tern could not focus the selected pane") return end
        tern.timer(0, step)
    end
    -- Creation and native actions are committed after their callback returns.
    tern.timer(0, step)
end

return navigation
