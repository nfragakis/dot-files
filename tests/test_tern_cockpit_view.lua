-- Run from the repository root: /usr/bin/lua tests/test_tern_cockpit_view.lua
-- Renders the cockpit with stub builders: every branch must build without a Lua error.
local function node(kind)
	return function(...) return { k = kind, args = { ... } } end
end
local ui = setmetatable({}, { __index = function(_, name) return node(name) end })
tern = { ui = ui, json = { array = function(value) return value or {} end, null = {} } }
local selection = dofile("tern/plugins/agent-cockpit/selection.luau")
package.preload["./selection"] = function() return selection end
local view = dofile("tern/plugins/agent-cockpit/view.luau")

local cx = { rows = 40 }
local function render(rows)
	local state = selection.new("owner")
	selection.snapshot(state, { token = "owner", rows = rows })
	return view.render(state, cx)
end

local full = {
	key = "pane-1", provider = "claude", title = "Cockpit details", status = "idle", done_unseen = true,
	flagged = true, stale = false, tab_color = "red", phase_ms = 8040000, session = "commercialize", host = "fw-desktop",
	host_key = "1", session_key = "1", model = "claude-opus-5-5", cwd = "/repo", activity = "Ready",
	request = "Fix the pane", last_response = "Done", source = "Claude lifecycle hook · Stop",
	usage_stats = { input = 10, output = 22839, cache_read = 4457171, cache_write = 135532, context = 158752, cost = 3.41, agents = 2 },
	workspace_branch = "main", git_status = "Dirty · 3 tracked · 1 untracked",
	git_divergence = "↑2 ↓0 · origin/main (local tracking ref)", pr_status = "#41 · Open · review required",
	pr_url = "https://github.com/o/r/pull/41", ci_status = "Remote HEAD · Passing · 3 passed / 3 checks",
	command = "claude", command_ms = 5000, last_command = "ls", last_command_ms = 10, last_exit = 0,
}
local codex = {
	key = "pane-2", provider = "codex", status = "waiting_input", phase_ms = 1000, host = "dev", session = "work",
	host_key = "2", session_key = "2", host_remote = true, usage_stats = { output = 5, context = 400, capacity = 2000 },
	workspace_branch = "feature", git_status = "Clean", git_divergence = "No upstream", pr_status = "No open PR",
	ci_status = "Unavailable · branch not pushed",
}
local bare = { key = "pane-3", provider = "agent", status = "unknown", stale = true }
local green = { key = "pane-4", provider = "omp", status = "idle", done_unseen = true, tab_color = "green", stale = true }

for _, rows in ipairs({ { full, codex, bare }, { codex }, { bare }, {} }) do
	local tree = render(rows)
	assert(tree.layer, "render returns a layer")
end
-- A held-back snapshot paints nothing, so the sheet appears once, complete.
local held = selection.new("owner")
selection.snapshot(held, { token = "owner", rows = { full }, ready = false })
assert(view.render(held, cx).layer.args[1][1].k == "col", "not ready renders the empty carrier")
selection.snapshot(held, { token = "owner", rows = { full }, ready = true })
assert(view.render(held, cx).layer.args[1][1].k == "picker")
-- Group headers lead with the session and carry the host on the right.
local picker = render({ full }).layer.args[1][1]
local header = picker.p.order[1]
assert(header.label == "commercialize" and header.count == "fw-desktop")
assert(picker.p.items[1].node == "tab-red", "a card wears its tab colour")
assert(render({ bare }).layer.args[1][1].p.items[1].node == "stale")
assert(render({ green }).layer.args[1][1].p.items[1].node == "tab-green", "tab colour outranks stale dimming")
codex.tab_color = "magenta"
assert(render({ codex }).layer.args[1][1].p.items[1].node == nil, "unknown colours are ignored")
print("cockpit view render: ok")
