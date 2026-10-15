-- Run from the repository root: /usr/bin/lua tests/test_tern_cockpit_marks.lua
local marks = dofile("tern/plugins/agent-cockpit/marks.luau")

local function equal(actual, expected, message)
	assert(actual == expected, (message or "unexpected value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

-- The manual flag toggles red on and off over any other colour.
equal(marks.toggle(nil), "red")
equal(marks.toggle("green"), "red", "manual flag replaces an automatic colour")
equal(marks.toggle("red"), nil)

-- Waiting outranks done; nothing notable means no colour.
equal(marks.auto({ { status = "idle", done = true }, { status = "waiting_input" } }), "yellow")
equal(marks.auto({ { status = "idle", done = true }, { status = "working" } }), "green")
equal(marks.auto({ { status = "working" } }), nil)
equal(marks.auto({}), nil)

-- Automatic colours apply to uncoloured tabs and are remembered as ours.
local owned = {}
local changes = marks.plan({ [1] = false, [2] = false }, owned, { [1] = "yellow" })
equal(#changes, 1)
equal(changes[1].tab, 1)
equal(changes[1].color, "yellow")
equal(owned[1], "yellow")

-- Our colour follows the state, including clearing it.
changes = marks.plan({ [1] = "yellow" }, owned, { [1] = "green" })
equal(changes[1].color, "green")
changes = marks.plan({ [1] = "green" }, owned, {})
equal(#changes, 1)
equal(changes[1].color, nil, "a reviewed tab is cleared")
equal(owned[1], nil)

-- A manual red, or any colour set by hand, is never replaced.
owned = { [1] = "yellow" }
changes = marks.plan({ [1] = "red", [2] = "purple" }, owned, { [1] = "green", [2] = "yellow" })
equal(#changes, 0, "colours we did not set are left alone")
equal(owned[1], nil, "ownership is dropped once the user recolours")
equal(owned[2], nil)

-- Closed tabs are forgotten.
owned = { [9] = "green" }
marks.plan({}, owned, {})
equal(owned[9], nil)

print("cockpit tab marks: ok")
