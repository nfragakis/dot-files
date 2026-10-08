--!strict
-- Quick host switching and a herdr dashboard tab on the dev box.

local DEV = "fw-dev"
-- mise's herdr; /usr/bin/herdr on fw-dev is an older client the server rejects.
local HERDR = "/home/nfragakis/.local/bin/herdr"

local function on_dev(cx): boolean
	local cur = cx.hosts:current()
	return cur ~= nil and string.lower(cur.name or "") == DEV
end

local function find_herdr(cx): number?
	for _, pane in cx.session:panes() do
		local program = pane.program or ""
		local title = string.lower(pane.title or "")
		if string.find(program, "herdr", 1, true) or string.find(title, "herdr", 1, true) then
			return pane.pane
		end
	end
	return nil
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

tern.command({
	id = "agents",
	title = "Agents dashboard (herdr on " .. DEV .. ")",
	icon = "sparkle",
	group = "Hosts",
	run = function(cx)
		if not on_dev(cx) then
			cx.hosts:switch(DEV)
		end
		local pane = find_herdr(cx)
		if pane then
			cx.layout:focus(pane)
		else
			cx.hosts:terminal(DEV, { command = HERDR })
		end
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
