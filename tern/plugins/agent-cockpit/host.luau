local selection = require("./selection")
local view = require("./view")

local function route(state, verb, cx)
	if not state.token then
		return
	end
	local key = ""
	if verb == "select" or verb == "focus" then
		local row = selection.current(state)
		if not row then
			return
		end
		key = row.key
	end
	cx:open("tern-agent-cockpit://" .. verb .. "/" .. state.token .. "/" .. key)
end

tern.block.define("cockpit", {
    init = function(cx, args)
        local state = selection.new(args[1], { cursor = args[2] })
        state.last_seen = tern.now()
        local function expire()
            if state.stopped then return end
            if tern.now() - state.last_seen > 15000 then
                if not state.loaded then state.stopped = true; cx:exit(0) return end
                -- Occluded windows throttle their UI timers. Verify ownership
                -- before ending the transient block, rather than expiring an open modal.
                tern.process.run({
                    "python3", tern.plugin.dir .. "/lease.py", state.origin,
                    "Agent Cockpit · " .. state.token, state.window_key,
                }, { timeout_ms = 5000 }):next(function(result)
                    if state.stopped then return end
                    if result and result.status == 0 then
                        state.last_seen = tern.now()
                        tern.timer(5000, expire)
                    else
                        state.stopped = true
                        cx:exit(0)
                    end
                end)
            else
                tern.timer(5000, expire)
            end
        end
        tern.timer(5000, expire)
        return state
    end,

	title = function(state)
        return "Agent Cockpit · " .. (state.token or "")
	end,

    view = function(state, cx)
        -- Keep the transport hidden until placement and the first snapshot agree.
        if state.stopped or not state.prepared or not state.loaded then return {} end
        return view.render(state, cx)
    end,

	key = function(state, key, cx)
		local handled, verb = selection.key(state, key)
		if verb then
			route(state, verb, cx)
		end
		return handled
	end,

	event = function(state, ev, cx)
        if state.stopped then return end
		if ev.ev == "action" and ev.act == "cockpit_claim" then
			selection.claim(state, ev.value)
        elseif ev.ev == "action" and ev.act == "cockpit_present" and ev.value == state.token then
            if state.preparing or state.prepared then return end
            state.preparing = true
            tern.process.run({
                "python3", tern.plugin.dir .. "/present.py", state.token, string.format("%.0f", cx.pane),
            }, { timeout_ms = 5000 }):next(function(result)
                if state.stopped then return end
                local ok, placement = pcall(tern.json.decode, result and result.stdout or "")
                if result and result.status == 0 and ok and type(placement) == "table"
                    and type(placement.pane) == "string" and placement.pane:match("^%d+$")
                    and type(placement.window) == "string" and (placement.window == "" or placement.window:match("^%d+$")) then
                    state.origin, state.window_key = placement.pane, placement.window
                    state.prepared = true
                    cx:open("tern-agent-cockpit://ready/" .. state.token .. "/")
                    cx:render()
                else
                    local err = result and result.stderr or "The native presentation command did not finish"
                    cx:toast("error", "Could not open Agent Cockpit", err)
                    cx:open("tern-agent-cockpit://failed/" .. state.token .. "/")
                    state.stopped = true
                    cx:exit(0)
                end
            end)
        elseif ev.ev == "action" and ev.act == "cockpit_ping" and ev.value == state.token then
            state.last_seen = tern.now()
        elseif ev.ev == "action" and ev.act == "cockpit_close" and ev.value == state.token then
            state.stopped = true
            cx:exit(0)
		elseif ev.ev == "action" and ev.act == "cockpit_snapshot" and ev.id == view.LIST_ID then
			if type(ev.value) ~= "string" then
				return
			end
			local ok, snapshot = pcall(tern.json.decode, ev.value)
			if ok then
				local accepted, notify = selection.snapshot(state, snapshot)
				if accepted and type(snapshot.revision) == "number" then
					cx:open("tern-agent-cockpit://ack/" .. state.token .. "/" .. tostring(snapshot.revision))
				end
				if accepted and notify then
					route(state, "select", cx)
				end
			end
        elseif ev.ev == "action" and ev.id == view.LIST_ID then
            if ev.act == "close" then route(state, "return", cx)
            elseif ev.act == "focus" then route(state, "focus", cx) end
		elseif (ev.ev == "select" or ev.ev == "activate") and ev.id == view.LIST_ID then
			local key = view.item_key(ev.item)
			if key and selection.select(state, key) then
				route(state, "select", cx)
			end
			if ev.ev == "activate" and state.cursor == key and selection.current(state) then
				route(state, "focus", cx)
			end
		end
	end,
})
