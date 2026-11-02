-- Strings stay UTF-8; native input offsets are UTF-16 code units (Tern SDK).
local M = {}

local function points(text)
    local out = { { byte = 1, units = 0 } }
    local units = 0
    for byte, cp in utf8.codes(text) do
        units = units + (cp > 65535 and 2 or 1)
        local next_byte = utf8.offset(text, 2, byte) or (#text + 1)
        out[#out + 1] = { byte = next_byte, units = units }
    end
    return out
end

function M.length(text)
    local p = points(text)
    return p[#p].units
end

local function at(text, units)
    local result = { byte = 1, units = 0 }
    for _, p in ipairs(points(text)) do
        if p.units > units then break end
        result = p
    end
    return result
end

function M.new(text)
    text = text or ""
    return { text = text, cursor = M.length(text) }
end

function M.edit(field, from, to, text, cursor)
    local a, b = at(field.text, from), at(field.text, to)
    text = (text or ""):gsub("[\r\n]", " ")
    field.text = field.text:sub(1, a.byte - 1) .. text .. field.text:sub(b.byte)
    field.cursor = at(field.text, cursor or (a.units + M.length(text))).units
end

function M.key(field, key)
    local name = key.name
    local p, previous, following = at(field.text, field.cursor), 0, M.length(field.text)
    for _, q in ipairs(points(field.text)) do
        if q.units < p.units then previous = q.units end
        if q.units > p.units then following = q.units; break end
    end
    if key.alt then return false end
    if key.ctrl or key.meta then
        if name == "u" then M.edit(field, 0, field.cursor, "", 0)
        elseif name == "a" then field.cursor = 0
        elseif name == "e" then field.cursor = M.length(field.text)
        elseif name == "w" then
            local prefix = field.text:sub(1, p.byte - 1)
            local trimmed = prefix:gsub("%s+$", ""):gsub("%S+$", "")
            M.edit(field, M.length(trimmed), field.cursor, "", M.length(trimmed))
        else return false end
    elseif name == "left" then field.cursor = previous
    elseif name == "right" then field.cursor = following
    elseif name == "home" then field.cursor = 0
    elseif name == "end" then field.cursor = M.length(field.text)
    elseif name == "backspace" then M.edit(field, previous, field.cursor, "", previous)
    elseif name == "delete" then M.edit(field, field.cursor, following, "", field.cursor)
    elseif key.text and key.text ~= "" then M.edit(field, field.cursor, field.cursor, key.text)
    elseif name == "space" then M.edit(field, field.cursor, field.cursor, " ")
    else return false end
    return true
end

return M
