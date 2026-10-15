-- Cursor identity is opaque: never derive pane ids or positions from a key.
local selection = {}

local function index_of(rows, key)
	for i, row in ipairs(rows) do
		if row.key == key then
			return i
		end
	end
	return nil
end

function selection.new(token, saved)
	saved = type(saved) == "table" and saved or {}
	return {
		token = type(token) == "string" and token ~= "" and token or nil,
		rows = {},
		cursor = type(saved.cursor) == "string" and saved.cursor or nil,
		index = type(saved.index) == "number" and math.max(1, math.floor(saved.index)) or 1,
		loaded = false,
		force_select = true,
		pending_g = false,
	}
end

function selection.claim(state, token)
	if type(token) ~= "string" or token == "" then
		return false
	end
	if state.token ~= token then
		-- Do not display a previous window's observations under a new owner.
		state.rows = {}
		state.problem = nil
		state.loaded = false
	end
	state.token = token
	state.force_select = true
	state.pending_g = false
	return true
end

function selection.snapshot(state, snapshot)
	if type(snapshot) ~= "table" or not state.token or snapshot.token ~= state.token
		or type(snapshot.rows) ~= "table" then
		return false, false
	end
	local previous = state.cursor
	local old_index = index_of(state.rows, previous) or state.index or 1
	state.rows = snapshot.rows
	state.index = index_of(state.rows, previous)
	if not state.index and #state.rows > 0 then
		state.index = math.min(old_index, #state.rows)
	end
	state.cursor = state.index and state.rows[state.index].key or nil
	state.problem = type(snapshot.problem) == "string" and snapshot.problem or nil
	state.loaded = true
	local notify = state.cursor ~= nil and (state.force_select or state.cursor ~= previous)
	state.force_select = false
	return true, notify
end

function selection.select(state, key)
	local index = index_of(state.rows, key)
	if not index or state.cursor == key then
		return false
	end
	state.cursor = key
	state.index = index
	state.pending_g = false
	return true
end

function selection.move(state, index)
	if #state.rows == 0 then
		return false
	end
	local row = state.rows[math.max(1, math.min(index, #state.rows))]
	return selection.select(state, row.key)
end

function selection.current(state)
	local index = index_of(state.rows, state.cursor)
	return index and state.rows[index] or nil
end

-- Return a reverse-transport verb only when a real effect is needed.
function selection.key(state, key)
    if key.ctrl and key.name == "c" and not key.alt and not key.meta then
        return true, "return"
    end
	if key.ctrl or key.alt or key.meta or key.name == "paste" then
		return false, nil
	end
	local text = key.text or key.name
	if key.name == "g" and key.shift then
		text = "G"
	end
	local was_g = state.pending_g
	state.pending_g = false
	local target
	if key.name == "up" or text == "k" then
		target = (state.index or 1) - 1
	elseif key.name == "down" or text == "j" then
		target = (state.index or 1) + 1
    elseif key.name == "pageup" or key.name == "pageUp" then
        target = (state.index or 1) - (state.page_size or 8)
    elseif key.name == "pagedown" or key.name == "pageDown" then
        target = (state.index or 1) + (state.page_size or 8)
	elseif key.name == "home" then
		target = 1
	elseif key.name == "end" or text == "G" then
		target = #state.rows
	elseif text == "g" then
		if was_g then
			target = 1
		else
			state.pending_g = true
			return true, nil
		end
	elseif key.name == "enter" or text == "o" then
		return true, selection.current(state) and "focus" or nil
	elseif key.name == "escape" or text == "q" then
		return true, "return"
	elseif text == "r" then
		return true, "refresh"
	else
		return was_g, nil
	end
	local changed = selection.move(state, target)
	return true, changed and "select" or nil
end

return selection
