--!strict
-- Based on tern-forge/omarchy (MIT). Keep dispatch on Tern's native focused pane:
-- Tern 0.9.0 can return a remote pane id that numeric lookup cannot round-trip.
local agents = require("./lib/agents")
local geometry = require("./lib/geometry")
local heartbeat = require("./lib/heartbeat")
local hypr = require("./lib/hypr")

local DIRS = {
	{ key = "left", dir = "l", opposite = "right", swap = "a" },
	{ key = "right", dir = "r", opposite = "left", swap = "d" },
	{ key = "up", dir = "u", opposite = "down", swap = "w" },
	{ key = "down", dir = "d", opposite = "up", swap = "s" },
}

local function context(cx)
	return { host = cx.hosts:current().id, session = cx.sessions:current().id, pane = cx.session:focused() }
end

local function same_context(cx, before)
	return cx.hosts:current().id == before.host and cx.sessions:current().id == before.session
end

local function focus(cx, direction)
	local before = context(cx)
	cx:action("focus_pane:" .. direction.key)
	-- Native actions apply after their callback. Do not mistake that old snapshot for an edge.
	tern.timer(0, function(next_cx)
		if next_cx and same_context(next_cx, before) and next_cx.session:focused() == before.pane then
			hypr.dispatch('hl.dsp.focus({ direction = "' .. direction.dir .. '" })')
		end
	end)
end

local function enter(cx, direction)
	local before = context(cx)
	local function step(next_cx)
		if not next_cx or not same_context(next_cx, before) then return end
		local pane = next_cx.session:focused()
		if not pane then return end
		next_cx:action("focus_pane:" .. direction.opposite)
		tern.timer(0, function(after_cx)
			if after_cx and same_context(after_cx, before) and after_cx.session:focused() ~= pane then
				step(after_cx)
			end
		end)
	end
	step(cx)
end

local function geometry_error(cx, message)
	tern.log.warn("omarchy: native pane geometry failed", message)
	cx:toast("error", "Omarchy cannot inspect this tab", message)
end

local function class_token(classes, token)
	return type(classes) == "string" and (" " .. classes .. " "):find(" " .. token .. " ", 1, true) ~= nil
end

-- The focused selector resolves before Tern's defective numeric pane lookup. Its full id addresses
-- this exact window's control endpoint even when every id exposed by hosts:list() is truncated.
local function visible_where(cx, done)
	local before = context(cx)
	local focused = cx.session:pane("@focused")
	local anchor = focused and focused.pane
	if not anchor then
		geometry_error(cx, "The focused pane is unavailable for the window control query")
		return
	end
	local runtime = tern.getenv("XDG_RUNTIME_DIR")
	local socket = tern.getenv("TERN_DAEMON_SOCKET") or (runtime and (runtime .. "/tern/daemon.sock"))
	if not socket then
		geometry_error(cx, "The local Tern daemon socket is unavailable")
		return
	end
	local started, err = pcall(tern.process.run, { "tern", "ctl", "tree", ".tn-pane" }, {
		timeout_ms = 2000,
		env = { TERN_PANE = string.format("%.0f", anchor), TERN_PANE_SOCKET = socket },
	}, function(result, next_cx)
		if not next_cx or not same_context(next_cx, before) or next_cx.session:focused() ~= before.pane then return end
		if result.status ~= 0 or result.timed_out then
			geometry_error(next_cx, string.format("Window control query failed (status %s, timed out %s): %s%s",
				tostring(result.status), tostring(result.timed_out == true), result.stderr or "", result.stdout or ""))
			return
		end
		local decoded, tree = pcall(tern.json.decode, result.stdout)
		if not decoded or type(tree) ~= "table" or tree.ok ~= true or type(tree.nodes) ~= "table" then
			geometry_error(next_cx, "Window control query returned an invalid pane tree: " .. tostring(tree))
			return
		end
		local visible, focused = {}, nil
		local left, top, right, bottom = math.huge, math.huge, -math.huge, -math.huge
		for _, node in ipairs(tree.nodes) do
			local r = node.rect
			if not class_token(node.class, "pip") and type(r) == "table"
				and type(r[1]) == "number" and type(r[2]) == "number"
				and type(r[3]) == "number" and type(r[4]) == "number" and r[3] > 0 and r[4] > 0 then
				visible[#visible + 1] = r
				if class_token(node.class, "on") then
					if focused then
						geometry_error(next_cx, "The native pane tree has more than one focused tiled pane")
						return
					end
					focused = #visible
				end
				left, top = math.min(left, r[1]), math.min(top, r[2])
				right, bottom = math.max(right, r[1] + r[3]), math.max(bottom, r[2] + r[4])
			end
		end
		local pane = next_cx.session:pane("@focused")
		if not pane or not focused or right <= left or bottom <= top then
			geometry_error(next_cx, "The native pane tree has no focused tiled rectangle")
			return
		end
		local rects, width, height = {}, right - left, bottom - top
		for index, r in ipairs(visible) do
			-- Negative indexes are anonymous geometry keys, not reconstructed pane ids.
			local key = index == focused and pane.pane or -index
			rects[key] = { x = (r[1] - left) / width, y = (r[2] - top) / height, w = r[3] / width, h = r[4] / height }
		end
		done(next_cx, pane, rects, { width, height })
	end)
	if not started then geometry_error(cx, "Cannot start the window control query: " .. tostring(err)) end
end

-- Fallback rectangle keys are anonymous: only a round-trip-safe native tree
-- supplies pane ids that can be used as layout mutation targets.
local function where(cx, done)
	local pane = cx.session:pane("@focused")
	if not pane or pane.floating or pane.parked then done(cx, pane, nil); return end
	local layout = pane.tab and cx.session:layout(pane.tab)
	if not layout then visible_where(cx, done); return end
	if layout.zoomed then done(cx, pane, nil); return end
	local rects = geometry.rects(layout.root)
	if not rects[pane.pane] then
		geometry_error(cx, "The current pane is missing from Tern's current tab layout")
		return
	end
	done(cx, pane, rects, nil, layout.root)
end

local function swap(cx, direction)
	where(cx, function(next_cx, pane, rects, _, root)
		local target = pane and rects and geometry.neighbor(rects, pane.pane, direction.dir)
		if not target then
			hypr.dispatch('hl.dsp.window.swap({ direction = "' .. direction.dir .. '" })')
			return
		end
		if not root or not next_cx.session:pane(pane.pane) or not next_cx.session:pane(target) then
			-- Tern's native action still addresses the focused high-id pane. It may reparent a
			-- nested split, but keeps pane movement working when LayoutCx cannot round-trip ids.
			next_cx:action("move_pane:" .. direction.key)
			return
		end
		-- move_pane:* reparents a leaf: it is not a swap and changes split topology.
		if not next_cx.layout:move(pane.pane, target, "swap") then
			tern.log.warn("omarchy: native pane swap failed")
			next_cx:toast("error", "Omarchy could not swap these panes", "Tern rejected the native layout swap")
		end
	end)
end

-- resize_split moves the nearest divider on the requested axis, not the pane's
-- edge. Track which child owns that divider so positive deltas grow either side.
local function divider_side(node, pane, axis, side)
	if node.pane then return node.pane == pane, side end
	if not node[1] or not node[2] then return false, nil end
	local horizontal = axis == "x"
	local matching = node.split == (horizontal and "right" or "down")
	local found, nearest = divider_side(node[1], pane, axis,
		matching and (horizontal and "right" or "down") or side)
	if found then return true, nearest end
	return divider_side(node[2], pane, axis,
		matching and (horizontal and "left" or "up") or side)
end

local function resize(cx, dx, dy)
	where(cx, function(next_cx, pane, rects, _, root)
		local rect = pane and rects and rects[pane.pane]
		local divided = rect and ((dx ~= 0 and rect.w < 1 - 1e-6) or (dy ~= 0 and rect.h < 1 - 1e-6))
		if not divided then
			hypr.dispatch(string.format("hl.dsp.window.resize({ x = %d, y = %d, relative = true })", dx, dy))
			return
		end
		local horizontal = dx ~= 0
		local side
		if root then
			local _, nearest = divider_side(root, pane.pane, horizontal and "x" or "y")
			side = nearest
		else
			-- A boundary pane has an unambiguous divider side even without the
			-- native split tree. Interior rectangles alone do not encode ancestry.
			local start = horizontal and rect.x or rect.y
			local finish = start + (horizontal and rect.w or rect.h)
			if start <= 1e-6 then side = horizontal and "right" or "down"
			elseif finish >= 1 - 1e-6 then side = horizontal and "left" or "up" end
		end
		if not side then
			geometry_error(next_cx, "Tern's native split tree is unavailable; this interior pane's nearest divider cannot be determined safely")
			return
		end
		local opposite = { right = "left", left = "right", down = "up", up = "down" }
		local direction = dx + dy > 0 and side or opposite[side]
		-- Native actions choose the cell size; Alt retains the smaller step.
		local steps = (math.abs(dx) + math.abs(dy) == 25) and 1 or 4
		for _ = 1, steps do next_cx:action("resize_split:" .. direction) end
	end)
end

local function new_pane(cx)
	if not cx.session:focused() then
		cx:command("new_tab")
		return
	end
	local before = context(cx)
	hypr.active(function(window, next_cx)
		if not next_cx or not same_context(next_cx, before) or next_cx.session:focused() ~= before.pane then return end
		if not window or window.class ~= hypr.TERN_CLASS or type(window.size) ~= "table" then
			tern.log.warn("omarchy: cannot read the active Tern window for splitting")
			next_cx:toast("error", "Omarchy cannot determine the split direction", "The active Tern window geometry is unavailable")
			return
		end
		where(next_cx, function(split_cx, pane, rects, native_size)
			if not pane then return end
			local rect = rects and rects[pane.pane] or { w = 1, h = 1 }
			local size = native_size or window.size
			local horizontal = rect.w * size[1] >= rect.h * size[2]
			-- Native split inherits cwd and host without a numeric layout mutation.
			split_cx:command(horizontal and "split_right" or "split_down")
		end)
	end)
end

local function close(cx)
	local tabs = {}
	for _, session in ipairs(cx.session:sessions()) do
		if session.current then
			for _, tab in ipairs(session.tabs) do tabs[tab] = true end
		end
	end
	local count = 0
	for _, pane in ipairs(cx.session:panes()) do
		if pane.tab and tabs[pane.tab] and not pane.parked then count = count + 1 end
	end
	if count <= 1 then hypr.dispatch("hl.dsp.window.close()")
	else cx:command("close_pane") end
end

for _, direction in ipairs(DIRS) do
	tern.bind("cmd+" .. direction.key, function(cx) focus(cx, direction) end)
	tern.bind("cmd+ctrl+shift+" .. direction.key, function(cx) enter(cx, direction) end)
	tern.bind("cmd+ctrl+shift+" .. direction.swap, function(cx) swap(cx, direction) end)
end
for _, size in ipairs({
	{ key = "h", dx = -100, dy = 0 }, { key = "l", dx = 100, dy = 0 },
	{ key = "k", dx = 0, dy = -100 }, { key = "j", dx = 0, dy = 100 },
	{ key = "y", dx = -25, dy = 0 }, { key = "o", dx = 25, dy = 0 },
	{ key = "i", dx = 0, dy = -25 }, { key = "u", dx = 0, dy = 25 },
}) do
	tern.bind("cmd+ctrl+shift+" .. size.key, function(cx) resize(cx, size.dx, size.dy) end)
end
tern.bind("cmd+enter", new_pane)
tern.bind("cmd+w", close)
tern.bind("cmd+shift+a", "new_agent_block")
tern.bind("cmd+shift+p", "new_browser_block")

local function show_projects(cx)
	for _, canvas in ipairs(cx.canvas:list()) do
		if canvas.owner == "forge" and canvas.title == "Projects" and cx.session:pane(canvas.pane) then
			cx.layout:focus(canvas.pane)
			return
		end
	end
	hypr.press("SUPER ALT SHIFT", "P")
end
tern.bind("cmd+ctrl+shift+b", show_projects)

agents.start()
heartbeat.start()
