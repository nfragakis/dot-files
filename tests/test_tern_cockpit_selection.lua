-- Run from the repository root: /usr/bin/lua tests/test_tern_cockpit_selection.lua
local selection = dofile("tern/plugins/agent-cockpit/selection.luau")

local function equal(actual, expected, message)
	assert(actual == expected, (message or "unexpected value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

local function rows(...)
	local result = {}
	for _, key in ipairs({ ... }) do
		result[#result + 1] = { key = key }
	end
	return result
end

local function snapshot(state, list, token)
	return selection.snapshot(state, { token = token or "owner", rows = list })
end

local function key(state, name, text, extra)
	local event = extra or {}
	event.name = name
	event.text = text
	return selection.key(state, event)
end

-- A row's identity, not a numeric-looking key or its old position, wins.
local state = selection.new("owner")
local accepted, notify = snapshot(state, rows("007", "remote-session:2", "last"))
equal(accepted, true)
equal(notify, true)
equal(state.cursor, "007")
equal(selection.select(state, "remote-session:2"), true)
equal(state.index, 2)
accepted, notify = snapshot(state, rows("remote-session:2", "last", "007"))
equal(state.cursor, "remote-session:2", "reorder keeps identity")
equal(state.index, 1)
equal(notify, false, "reorder does not request another selection")

-- Removal chooses the nearest valid position, including the old last row.
selection.select(state, "last")
accepted, notify = snapshot(state, rows("remote-session:2", "007"))
equal(state.cursor, "007")
equal(state.index, 2)
equal(notify, true)
accepted, notify = snapshot(state, rows("remote-session:2"))
equal(state.cursor, "remote-session:2")
equal(state.index, 1)
equal(notify, true)
snapshot(state, rows())
equal(state.cursor, nil)
equal(state.index, nil)
equal(selection.current(state), nil)
equal(selection.move(state, 2), false)
accepted, notify = snapshot(state, rows("new"))
equal(state.cursor, "new")
equal(notify, true)

-- Selecting an unknown identity leaves the current session unchanged.
snapshot(state, rows("new", "other"))
selection.select(state, "other")
equal(selection.select(state, "not-a-row"), false)
equal(state.cursor, "other")

-- Owner tokens gate observations, including restored blocks with no owner.
local original_rows = state.rows
accepted, notify = snapshot(state, rows("foreign"), "foreign-owner")
equal(accepted, false)
equal(notify, false)
equal(state.rows, original_rows)
equal(selection.claim(state, ""), false)
equal(selection.claim(state, "owner"), true)
accepted, notify = snapshot(state, rows("new", "other"))
equal(notify, true, "explicit adoption resends current selection")
equal(selection.claim(state, "replacement-owner"), true)
equal(state.loaded, false)
equal(#state.rows, 0)
accepted = snapshot(state, rows("old-window"))
equal(accepted, false)
accepted, notify = snapshot(state, rows("replacement"), "replacement-owner")
equal(accepted, true)
equal(notify, true)
equal(state.cursor, "replacement")
local restored = selection.new(nil, { cursor = "b", index = 2 })
accepted = snapshot(restored, rows("a", "b"))
equal(accepted, false, "restored unclaimed block rejects snapshots")
selection.claim(restored, "owner")
snapshot(restored, rows("a", "b"))
equal(restored.cursor, "b", "saved identity survives restart")
local missing_saved = selection.new("owner", { cursor = "gone", index = 8 })
snapshot(missing_saved, rows("a", "b"))
equal(missing_saved.cursor, "b", "missing restored identity clamps saved index")

-- Vim/arrow navigation produces a select effect only when identity changes.
state = selection.new("owner")
snapshot(state, rows("a", "b", "c"))
local handled, effect = key(state, "j", "j")
equal(handled, true)
equal(effect, "select")
equal(state.cursor, "b")
handled, effect = key(state, "down")
equal(effect, "select")
equal(state.cursor, "c")
handled, effect = key(state, "down")
equal(effect, "select", "down past the last row wraps")
equal(state.cursor, "a")
handled, effect = key(state, "k", "k")
equal(effect, "select", "up past the first row wraps")
equal(state.cursor, "c")
handled, effect = key(state, "pagedown")
equal(effect, nil, "page keys clamp and do not repeat selection requests")
equal(state.cursor, "c")
handled, effect = key(state, "g", "g")
equal(effect, nil)
equal(state.cursor, "c", "first g is only a prefix")
handled, effect = key(state, "g", "g")
equal(effect, "select")
equal(state.cursor, "a")
handled, effect = key(state, "g", nil, { shift = true })
equal(effect, "select")
equal(state.cursor, "c", "Shift+g without text means G")
key(state, "home")
equal(state.cursor, "a")
key(state, "g", "G")
equal(state.cursor, "c", "uppercase text means G")
key(state, "up")
equal(state.cursor, "b")
key(state, "k", "k")
equal(state.cursor, "a")
key(state, "end")
equal(state.cursor, "c")
key(state, "g", "g")
key(state, "x", "x")
key(state, "g", "g")
equal(state.cursor, "c", "a different key cancels gg")
key(state, "escape")
for _, modifier in ipairs({ "ctrl", "alt", "meta" }) do
	handled, effect = key(state, "j", "j", { [modifier] = true })
	equal(handled, false)
	equal(effect, nil)
	equal(state.cursor, "c")
end
handled, effect = key(state, "paste", "j")
equal(handled, false)
equal(effect, nil)
for _, jump in ipairs({ "enter", "o" }) do
	handled, effect = key(state, jump)
	equal(effect, "focus")
end
for _, leave in ipairs({ "escape", "q" }) do
	handled, effect = key(state, leave)
	equal(effect, "return")
end
handled, effect = key(state, "c", nil, { ctrl = true })
equal(effect, "return", "omp picker Ctrl+C dismisses")
state.page_size = 2
key(state, "pageup")
equal(state.cursor, "a", "PageUp navigates one visible page")
key(state, "pagedown")
equal(state.cursor, "c", "PageDown navigates one visible page")
handled, effect = key(state, "r")
equal(effect, "refresh")
snapshot(state, rows())
handled, effect = key(state, "enter")
equal(effect, nil, "empty lists have no jump target")
handled, effect = key(state, "q")
equal(effect, "return", "empty cockpit can still return")
handled, effect = key(state, "r")
equal(effect, "refresh", "empty cockpit can still refresh")
print("cockpit selection transitions: ok")
