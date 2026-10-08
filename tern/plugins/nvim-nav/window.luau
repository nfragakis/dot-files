--!strict
-- Neovim handles its own splits; title events carry edge requests over remoting.
local EDITOR = "nvim [tern-nav] "
local REQUEST = "nvim [tern-nav-request] "
local directions = { h = "left", j = "down", k = "up", l = "right" }
local controls = { h = "\x08", j = "\x0a", k = "\x0b", l = "\x0c" }

-- A sibling on the requested side of any ancestor means a tiled neighbor exists.
local function has_neighbor(tree, pane: number, key: string): (boolean, boolean)
	if tree.pane then
		return tree.pane == pane, false
	end
	local found, neighbor = has_neighbor(tree[1], pane, key)
	if found then
		return true, neighbor or (tree.split == "right" and key == "l") or (tree.split == "down" and key == "j")
	end
	found, neighbor = has_neighbor(tree[2], pane, key)
	if found then
		return true, neighbor or (tree.split == "right" and key == "h") or (tree.split == "down" and key == "k")
	end
	return false, false
end

local function focus_outer(cx, key: string)
	local pane = cx.session:pane(cx.session:focused())
	local layout = pane and cx.session:layout(pane.tab)
	if layout then
		local found, neighbor = has_neighbor(layout.root, pane.pane, key)
		if found and neighbor then
			cx:action("focus_pane:" .. directions[key])
		end
	end
end

local function navigate(cx, key: string)
	local id = cx.session:focused()
	if not id then
		return
	end
	local pane = cx.session:pane(id)
	if pane and (string.sub(pane.title, 1, #EDITOR) == EDITOR or string.sub(pane.title, 1, #REQUEST) == REQUEST) then
		cx:run(id, controls[key])
	else
		focus_outer(cx, key)
	end
end

for key, direction in directions do
	tern.command({
		id = "navigate_" .. key,
		title = "Navigate Neovim or pane " .. direction,
		group = "Navigation",
		run = function(cx)
			navigate(cx, key)
		end,
	})
end

tern.on("title", function(ev, cx)
	local key = string.match(ev.title, "^nvim %[tern%-nav%-request%] ([hjkl]):%d+$")
	if key and cx.session:focused() == ev.pane then
		focus_outer(cx, key)
	end
end)
