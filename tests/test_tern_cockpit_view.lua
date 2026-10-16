-- Run from the repository root: /usr/bin/lua tests/test_tern_cockpit_view.lua
-- Exercise the rendered picker and its host interactions across observation updates.
local function node(kind)
	return function(...) return { k = kind, args = { ... } } end
end
local ui = setmetatable({}, { __index = function(_, name) return node(name) end })
local snapshots, block = {}, nil
tern = {
	ui = ui,
	json = {
		array = function(value) return value or {} end,
		null = {},
		decode = function(value) return snapshots[value] end,
	},
	block = { define = function(_, definition) block = definition end },
}
local selection = dofile("tern/plugins/agent-cockpit/selection.luau")
package.preload["./selection"] = function() return selection end
local view = dofile("tern/plugins/agent-cockpit/view.luau")
package.preload["./view"] = function() return view end
dofile("tern/plugins/agent-cockpit/host.luau")

local opened = {}
local cx = { rows = 40, open = function(_, uri) opened[#opened + 1] = uri end }
local function find(value, predicate)
	if type(value) ~= "table" then return nil end
	if predicate(value) then return value end
	for _, child in pairs(value) do
		local result = find(child, predicate)
		if result then return result end
	end
end
local function contains(value, text)
	if value == text then return true end
	if type(value) ~= "table" then return false end
	for _, child in pairs(value) do
		if contains(child, text) then return true end
	end
	return false
end
local function picker(state)
	local tree = block.view(state, cx)
	local result = find(tree, function(value) return value.p and value.p.role == "cockpit.picker" end)
	assert(result, "the cockpit picker is visible")
	assert(find(result, function(value) return value.p and value.p.role == "cockpit.detail" end),
		"the picker includes its detail column")
	return result
end
local function snapshot(state, name, rows, token)
	snapshots[name] = { token = token or "owner", rows = rows }
	block.event(state, { ev = "action", act = "cockpit_snapshot", id = view.LIST_ID, value = name }, cx)
end
local function action(state, act)
	block.event(state, { ev = "action", act = act, id = view.LIST_ID }, cx)
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
local bare = { key = "pane-3", provider = "omp", status = "unknown" }

-- Before discovery, show the real shell and loading text without inventing an agent.
local state = selection.new("owner")
local loading = picker(state)
assert(contains(loading, "Loading agent sessions…"), "loading is visible before any snapshot")
assert(#loading.p.items == 0 and loading.p.selected == tern.json.null, "loading has no fake selection")
assert(contains(loading, "Close"), "the loading shell offers Close")
assert(not contains(loading, "No detected agent sessions."), "loading is not an empty discovery")
assert(block.key(state, { name = "enter" }, cx))
action(state, "focus")
assert(#opened == 0, "Enter and Open session have no destination while loading")
assert(block.key(state, { name = "escape" }, cx))
assert(opened[#opened] == "tern-agent-cockpit://return/owner/", "Escape dismisses while loading")
action(state, "close")
assert(#opened == 2 and opened[2] == "tern-agent-cockpit://return/owner/", "Close dismisses while loading")

snapshot(state, "stale-before-discovery", { full }, "old-owner")
assert(not state.loaded and #picker(state).p.items == 0, "a stale owner cannot replace loading")
snapshot(state, "discovered", { bare, codex })
local populated = picker(state)
assert(state.loaded and #populated.p.items == 2, "the first discovery populates the picker")
assert(populated.p.role == loading.p.role and populated.p.key == loading.p.key, "discovery keeps the same picker shell")
assert(populated.p.selected == "omp:pane-3")
assert(not contains(populated, "Loading agent sessions…"), "discovery replaces the loading presentation")

-- Enrichment changes content without resetting the user's selected identity.
block.event(state, { ev = "select", id = view.LIST_ID, item = "codex:pane-2" }, cx)
local enriched = {}
for key, value in pairs(codex) do enriched[key] = value end
enriched.title = "Enriched Codex session"
enriched.model = "Observed model"
local before_enrichment = #opened
snapshot(state, "enriched", { enriched, full, bare })
local updated = picker(state)
assert(updated.p.selected == "codex:pane-2", "enrichment and reordering preserve selection")
assert(contains(updated, "Enriched Codex session") and contains(updated, "Observed model"), "selected details enrich progressively")
assert(#opened == before_enrichment, "enrichment does not resend an unchanged selection")
snapshot(state, "stale-after-discovery", {}, "old-owner")
assert(#picker(state).p.items == 3 and picker(state).p.selected == "codex:pane-2", "stale snapshots cannot clear the picker")
assert(block.key(state, { name = "enter" }, cx))
assert(opened[#opened] == "tern-agent-cockpit://focus/owner/pane-2", "Enter opens the selected real session")

-- An observed empty result is distinct from loading, but remains dismissible.
local empty = selection.new("owner")
snapshot(empty, "empty-discovery", {})
local empty_picker = picker(empty)
assert(empty.loaded and #empty_picker.p.items == 0)
assert(contains(empty_picker, "No detected agent sessions.") and contains(empty_picker, "No agent selected"))
assert(not contains(empty_picker, "Loading agent sessions…"))
local before_empty = #opened
block.key(empty, { name = "enter" }, cx)
action(empty, "focus")
assert(#opened == before_empty, "empty discovery has no destination")
action(empty, "close")
assert(opened[#opened] == "tern-agent-cockpit://return/owner/", "empty discovery can close")

-- Ownership handoff clears old observations and restores loading until new discovery.
block.event(state, { ev = "action", act = "cockpit_claim", value = "replacement-owner" }, cx)
assert(contains(picker(state), "Loading agent sessions…") and #picker(state).p.items == 0)
snapshot(state, "late-old-owner", { full })
assert(not state.loaded and #picker(state).p.items == 0)
snapshot(state, "replacement-discovery", { full }, "replacement-owner")
assert(#picker(state).p.items == 1 and picker(state).p.selected == "claude:pane-1")
assert(contains(picker(state), "Cockpit details") and contains(picker(state), "Fix the pane"), "new owner receives genuine agent details")
print("cockpit view transitions: ok")
