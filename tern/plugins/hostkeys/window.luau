--!strict
-- Quick host switching and named-session navigation.

local DEV = "fw-dev"

local function on_dev(cx): boolean
	local cur = cx.hosts:current()
	return cur ~= nil and string.lower(cur.name or "") == DEV
end

tern.command({
	id = "toggle_host",
	title = "Toggle host: local ⇄ " .. DEV,
	icon = "terminal",
	group = "Hosts",
	run = function(cx)
		if on_dev(cx) then
			cx.hosts:switch("local")
		else
			cx.hosts:switch(DEV)
		end
	end,
})

tern.command({
	id = "dev",
	title = "Go to " .. DEV,
	icon = "terminal",
	group = "Hosts",
	run = function(cx)
		cx.hosts:switch(DEV)
	end,
})

tern.command({
	id = "local",
	title = "Go to this machine",
	icon = "terminal",
	group = "Hosts",
	run = function(cx)
		cx.hosts:switch("local")
	end,
})

-- Cycle through every named session (all hosts), like tmux's ( and ).
local function step_session(cx, delta: number)
	local list = cx.sessions:list()
	local n = #list
	if n < 2 then
		return
	end
	local at = 1
	for i, s in list do
		if s.current then
			at = i
			break
		end
	end
	local next = list[((at - 1 + delta) % n) + 1]
	cx.sessions:switch(next.id)
	cx:toast("info", next.name or "session")
end

tern.command({
	id = "next_session",
	title = "Next session",
	icon = "terminal",
	group = "Hosts",
	run = function(cx)
		step_session(cx, 1)
	end,
})

tern.command({
	id = "previous_session",
	title = "Previous session",
	icon = "terminal",
	group = "Hosts",
	run = function(cx)
		step_session(cx, -1)
	end,
})
