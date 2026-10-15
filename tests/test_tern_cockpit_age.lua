-- Run from the repository root: /usr/bin/lua tests/test_tern_cockpit_age.lua
local discovery = dofile("tern/plugins/agent-cockpit/discovery.luau")

local function equal(actual, expected, message)
	assert(actual == expected, (message or "unexpected value") .. ": expected " .. tostring(expected) .. ", got " .. tostring(actual))
end

-- Recorded timestamps become UTC epoch seconds regardless of the local timezone.
equal(discovery.epoch("1970-01-01T00:00:00Z"), 0)
equal(discovery.epoch("2026-10-15T17:35:04.001Z"), 1792085704)
equal(discovery.epoch("2024-02-29T12:00:00+00:00"), 1709208000, "leap day")
equal(discovery.epoch("1792085704001"), 1792085704, "epoch milliseconds")
equal(discovery.epoch("2026-10-15T17:35:04+02:00"), nil, "non-UTC offsets are not guessed")
equal(discovery.epoch("yesterday"), nil)
equal(discovery.epoch(nil), nil)

-- Working agents never tick; idle ages are whole minutes from real activity.
local now = 1792085704
equal(discovery.age("working", now, now - 600, nil), nil)
equal(discovery.age("idle", now, now - 30, nil), nil, "under a minute shows nothing")
equal(discovery.age("idle", now, now - 125, nil), 120000)
equal(discovery.age("idle", now, now - 7200, now - 60), 60000, "an observed transition beats older activity")
equal(discovery.age("idle", now, nil, nil), nil, "unknown is not 'since the plugin loaded'")
equal(discovery.age("waiting_input", now, now - 3600, nil), 3600000)
-- The value only changes on a minute boundary, so snapshots stay still between them.
equal(discovery.age("idle", now + 59, now - 120, nil), discovery.age("idle", now, now - 120, nil))

print("cockpit ages: ok")
