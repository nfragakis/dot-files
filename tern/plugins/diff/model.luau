-- The pure half of tern-diff: unified-diff hunks, fuzzy file picking, search
-- inside a diff and wrapping navigation. It never touches Tern, git or the
-- filesystem, and it sticks to the syntax Lua 5.4 and Luau share (no type
-- annotations, no `continue`, no generalized iteration, no bit operators) so
-- plain `lua` can load and test the exact module the plugin requires.
--
-- Hunks follow the SDK `diff` node: `lines` are raw unified rows starting with
-- a space, `+` or `-`, plus the optional `\ No newline at end of file` marker.
-- The view maps each hunk to `{oldStart = h.old_start, newStart = h.new_start,
-- lines = h.lines}`.

local M = {}

local BYTE_SPACE = 32
local BYTE_PLUS = 43
local BYTE_MINUS = 45
local BYTE_BACKSLASH = 92

-- ASCII-only lowering through a byte table, so the result never depends on
-- the C locale and bytes of multi-byte UTF-8 sequences pass through untouched.
local ASCII_LOWER = {}
for c = 65, 90 do
	ASCII_LOWER[string.char(c)] = string.char(c + 32)
end

local function ascii_lower(s)
	return (string.gsub(s, "[A-Z]", ASCII_LOWER))
end

-- Splits on "\n" only: a "\r" before it stays in the line, so CRLF content
-- survives byte for byte. A final "\n" does not add an empty line.
local function split_lines(text)
	local out, n, pos, len = {}, 0, 1, #text
	while pos <= len do
		local nl = string.find(text, "\n", pos, true)
		n = n + 1
		if nl == nil then
			out[n] = string.sub(text, pos)
			break
		end
		out[n] = string.sub(text, pos, nl - 1)
		pos = nl + 1
	end
	return out
end

-- Parses `@@ -a[,b] +c[,d] @@[ section]`. An omitted count is 1; an explicit
-- count may be 0 (new or deleted file, pure insertion or removal).
local function parse_header(line)
	local old_start, old_comma, old_count, new_start, new_comma, new_count, rest =
		string.match(line, "^@@ %-(%d+)(,?)(%d*) %+(%d+)(,?)(%d*) @@(.*)$")
	if old_start == nil then
		return nil
	end
	if (old_comma ~= "" and old_count == "") or (new_comma ~= "" and new_count == "") then
		return nil
	end
	return {
		header = line,
		section = string.match(rest, "^ ?(.-)\r?$"),
		old_start = tonumber(old_start),
		old_count = old_comma == "" and 1 or tonumber(old_count),
		new_start = tonumber(new_start),
		new_count = new_comma == "" and 1 or tonumber(new_count),
		lines = {},
	}
end

-- Parses one unified patch (git diff output for one or more files) into hunks:
-- `{header, section, old_start, old_count, new_start, new_count, lines}`.
--
-- The `@@` counts decide where a hunk ends, which is what tells a deleted line
-- `--- x` or an added line `+++ x` apart from the next file's `---`/`+++`
-- header. A hunk that runs out of input, or meets a row its remaining counts
-- cannot hold, is kept with `incomplete = true` instead of passing as whole.
-- A bare empty row inside a hunk is an empty context line some tools strip to
-- nothing; it is stored as " " so every row keeps its prefix.
--
-- Returns the hunks, then the `@@`-prefixed lines that were not a hunk header
-- this parser reads (combined `@@@` merge diffs, malformed ranges) so the
-- caller can say so rather than show an empty diff as if nothing changed.
function M.parse(patch)
	if type(patch) ~= "string" then
		error("model.parse: patch must be a string, got " .. type(patch), 2)
	end
	local hunks, unparsed = {}, {}
	local hunk, old_left, new_left = nil, 0, 0
	for _, line in ipairs(split_lines(patch)) do
		local taken = false
		if hunk ~= nil then
			local lines = hunk.lines
			local c = string.byte(line, 1)
			if old_left > 0 or new_left > 0 then
				taken = true
				if c == BYTE_SPACE and old_left > 0 and new_left > 0 then
					old_left, new_left = old_left - 1, new_left - 1
					lines[#lines + 1] = line
				elseif c == BYTE_MINUS and old_left > 0 then
					old_left = old_left - 1
					lines[#lines + 1] = line
				elseif c == BYTE_PLUS and new_left > 0 then
					new_left = new_left - 1
					lines[#lines + 1] = line
				elseif c == BYTE_BACKSLASH then
					lines[#lines + 1] = line
				elseif c == nil and old_left > 0 and new_left > 0 then
					old_left, new_left = old_left - 1, new_left - 1
					lines[#lines + 1] = " "
				else
					hunk.incomplete = true
					hunk = nil
					taken = false
				end
			elseif c == BYTE_BACKSLASH then
				-- The marker for the hunk's last row comes after the counts run out.
				taken = true
				lines[#lines + 1] = line
			else
				hunk = nil
			end
		end
		if not taken and string.sub(line, 1, 2) == "@@" then
			local parsed = parse_header(line)
			if parsed == nil then
				unparsed[#unparsed + 1] = line
			else
				hunk = parsed
				old_left, new_left = parsed.old_count, parsed.new_count
				hunks[#hunks + 1] = parsed
			end
		end
	end
	if hunk ~= nil and (old_left > 0 or new_left > 0) then
		hunk.incomplete = true
	end
	return hunks, unparsed
end

-- One entry per row of `hunk.lines`: `{kind, old_line?, new_line?}` with kind
-- "context", "delete", "add" or "marker" and 1-based source line numbers.
function M.rows(hunk)
	local out = {}
	local old, new = hunk.old_start, hunk.new_start
	for i, line in ipairs(hunk.lines) do
		local c = string.byte(line, 1)
		if c == BYTE_SPACE then
			out[i] = { kind = "context", old_line = old, new_line = new }
			old, new = old + 1, new + 1
		elseif c == BYTE_MINUS then
			out[i] = { kind = "delete", old_line = old }
			old = old + 1
		elseif c == BYTE_PLUS then
			out[i] = { kind = "add", new_line = new }
			new = new + 1
		else
			out[i] = { kind = "marker" }
		end
	end
	return out
end

-- Plain substring search over the hunks' rows, old and new sides alike. The
-- query is never a pattern. Smartcase: a query with an ASCII capital matches
-- case-sensitively, otherwise ASCII case is ignored. The row prefix, the
-- no-newline marker and file metadata are never searched.
--
-- Each matching row is one hit: `{hunk, line, text, kind, col, old_line?,
-- new_line?}` where `line` indexes `hunks[hunk].lines`, `text` is the row
-- without its prefix and `col` is the 1-based byte offset of the first match
-- in `text`.
function M.search(hunks, query)
	local hits = {}
	if type(query) ~= "string" or query == "" then
		return hits
	end
	local sensitive = string.find(query, "[A-Z]") ~= nil
	for h, hunk in ipairs(hunks) do
		local old, new = hunk.old_start, hunk.new_start
		for i, line in ipairs(hunk.lines) do
			local c = string.byte(line, 1)
			local kind, old_line, new_line = nil, nil, nil
			if c == BYTE_SPACE then
				kind, old_line, new_line = "context", old, new
				old, new = old + 1, new + 1
			elseif c == BYTE_MINUS then
				kind, old_line = "delete", old
				old = old + 1
			elseif c == BYTE_PLUS then
				kind, new_line = "add", new
				new = new + 1
			end
			if kind ~= nil then
				local text = string.sub(line, 2)
				local col = string.find(sensitive and text or ascii_lower(text), query, 1, true)
				if col ~= nil then
					hits[#hits + 1] = {
						hunk = h,
						line = i,
						text = text,
						kind = kind,
						col = col,
						old_line = old_line,
						new_line = new_line,
					}
				end
			end
		end
	end
	return hits
end

-- The index `delta` steps from `index` among `count` items, wrapping at both
-- ends; nil when there is nothing. With no valid current index a forward step
-- lands on the first item and a backward step on the last.
function M.next(index, count, delta)
	if type(count) ~= "number" or count < 1 then
		return nil
	end
	count = math.floor(count)
	delta = math.floor(delta or 1)
	if type(index) ~= "number" or index < 1 or index > count then
		if delta == 0 then
			return 1
		end
		index = delta < 0 and count + 1 or 0
	end
	return (math.floor(index) - 1 + delta) % count + 1
end

-- Display rows and the visible window --------------------------------------
--
-- Tern scrolls nothing for us, so the view keeps a logical viewport over
-- display rows and renders only the rows in it, one `diff` node per source
-- hunk. A row is what one screen line of the diff shows:
--
--   unified  one row per diff line
--   split    one row per context line, and for each run of deletions and
--            additions the k-th deletion beside the k-th addition, the longer
--            side's leftovers on rows of their own
--
-- A no-newline marker stays in the row of the line it qualifies.

-- The hunk's rows as entries `{side, index, old, new, marker?}`: `old`/`new`
-- are both sides' line numbers when the row starts, `marker` the index of a
-- following no-newline marker. A marker with no line before it is its own
-- "marker" entry.
local function hunk_entries(hunk)
	local entries, n = {}, 0
	local old, new = hunk.old_start, hunk.new_start
	for i, line in ipairs(hunk.lines) do
		local c = string.byte(line, 1)
		if c == BYTE_BACKSLASH and n > 0 and entries[n].marker == nil and entries[n].side ~= "marker" then
			entries[n].marker = i
		else
			local side = "marker"
			if c == BYTE_SPACE then
				side = "context"
			elseif c == BYTE_MINUS then
				side = "delete"
			elseif c == BYTE_PLUS then
				side = "add"
			end
			n = n + 1
			entries[n] = { side = side, index = i, old = old, new = new }
			if side == "context" then
				old, new = old + 1, new + 1
			elseif side == "delete" then
				old = old + 1
			elseif side == "add" then
				new = new + 1
			end
		end
	end
	return entries
end

local function push_entry(row, hunk, entry)
	if entry == nil then
		return
	end
	row.lines[#row.lines + 1] = hunk.lines[entry.index]
	row.hunk_lines[#row.hunk_lines + 1] = entry.index
	if entry.marker ~= nil then
		row.lines[#row.lines + 1] = hunk.lines[entry.marker]
		row.hunk_lines[#row.hunk_lines + 1] = entry.marker
	end
end

local function new_row(h, kind, old_start, new_start, split)
	return {
		hunk = h,
		kind = kind,
		old_start = old_start,
		new_start = new_start,
		lines = {},
		hunk_lines = {},
		split = split or nil,
	}
end

-- Lays `hunks` out as display rows for `mode` ("split", anything else is
-- unified). Each row is `{hunk, kind, old_start, new_start, lines, hunk_lines,
-- line, split?, first?, header?}`:
--   kind        "context", "delete", "add", "change" (a split pair) or "marker"
--   old_start,  both sides' source line numbers where the row starts, so a
--   new_start   side the row has no line on holds the number its next line gets
--   lines       the raw unified rows shown, markers included
--   hunk_lines  their indexes in `hunks[hunk].lines`; `line` is the first one
--   first       true on a hunk's first row, which also carries its `header`
-- A hunk without lines has no rows.
function M.layout(hunks, mode)
	local split = mode == "split"
	local rows = {}
	for h, hunk in ipairs(hunks) do
		local entries = hunk_entries(hunk)
		local first_row = #rows + 1
		local i, n = 1, #entries
		while i <= n do
			local entry = entries[i]
			if not split or entry.side == "context" or entry.side == "marker" then
				local row = new_row(h, entry.side, entry.old, entry.new, false)
				push_entry(row, hunk, entry)
				rows[#rows + 1] = row
				i = i + 1
			else
				local dels, adds = {}, {}
				local start_old, start_new = entry.old, entry.new
				while i <= n and (entries[i].side == "delete" or entries[i].side == "add") do
					local side = entries[i].side == "delete" and dels or adds
					side[#side + 1] = entries[i]
					i = i + 1
				end
				local end_old, end_new = start_old + #dels, start_new + #adds
				for k = 1, math.max(#dels, #adds) do
					local del, add = dels[k], adds[k]
					local kind = (del ~= nil and add ~= nil) and "change" or (del ~= nil and "delete" or "add")
					local row = new_row(h, kind, del ~= nil and del.old or end_old, add ~= nil and add.new or end_new, true)
					push_entry(row, hunk, del)
					push_entry(row, hunk, add)
					rows[#rows + 1] = row
				end
			end
		end
		for r = first_row, #rows do
			rows[r].line = rows[r].hunk_lines[1]
		end
		if rows[first_row] ~= nil then
			rows[first_row].first = true
			rows[first_row].header = hunk.header
		end
	end
	return rows
end

-- The top row that keeps a `count`-row viewport inside `total` rows.
function M.clamp(first, total, count)
	local top = math.max(1, total - count + 1)
	first = math.floor(first or 1)
	if first < 1 then
		return 1
	end
	if first > top then
		return top
	end
	return first
end

-- The index of the first row of hunk `h`, or nil.
function M.hunk_row(rows, h)
	for r, row in ipairs(rows) do
		if row.hunk == h then
			return r
		end
	end
	return nil
end

-- The index of the row showing line `line` of hunk `h` (a search hit's
-- `hunk`/`line`), or nil.
function M.row_at(rows, h, line)
	for r, row in ipairs(rows) do
		if row.hunk == h then
			for _, index in ipairs(row.hunk_lines) do
				if index == line then
					return r
				end
			end
		elseif row.hunk > h then
			return nil
		end
	end
	return nil
end

-- Rows `first .. first + count - 1` (clipped to the rows there are) grouped by
-- source hunk into `diff` node hunks: `{hunk, old_start, new_start, lines,
-- first_row, last_row, header?}`. `old_start`/`new_start` come from the
-- group's first row; `header` is set when that row is the hunk's first. Within
-- each visible run of split rows all deletions come before all additions, so
-- the native split view pairs them exactly as the rows did.
function M.window(rows, first, count)
	local groups = {}
	local total = #rows
	if total == 0 or type(count) ~= "number" or count < 1 then
		return groups
	end
	first = math.max(1, math.min(math.floor(first or 1), total))
	local last = math.min(total, first + math.floor(count) - 1)
	local group, dels, adds = nil, {}, {}
	local function flush()
		if group == nil then
			return
		end
		local lines = group.lines
		for _, line in ipairs(dels) do
			lines[#lines + 1] = line
		end
		for _, line in ipairs(adds) do
			lines[#lines + 1] = line
		end
		dels, adds = {}, {}
	end
	for r = first, last do
		local row = rows[r]
		if group == nil or group.hunk ~= row.hunk then
			flush()
			group = {
				hunk = row.hunk,
				old_start = row.old_start,
				new_start = row.new_start,
				lines = {},
				first_row = r,
				last_row = r,
				header = row.header,
			}
			groups[#groups + 1] = group
		end
		group.last_row = r
		if row.split then
			local side = dels
			for _, line in ipairs(row.lines) do
				local c = string.byte(line, 1)
				if c == BYTE_MINUS then
					side = dels
				elseif c == BYTE_PLUS then
					side = adds
				end
				side[#side + 1] = line
			end
		else
			flush()
			for _, line in ipairs(row.lines) do
				group.lines[#group.lines + 1] = line
			end
		end
	end
	flush()
	return groups
end

-- Fuzzy file filter --------------------------------------------------------

local SCORE_MATCH = 16
local BONUS_START = 10
local BONUS_SLASH = 10
local BONUS_SEPARATOR = 7
local BONUS_CAMEL = 7
local BONUS_BASENAME = 4
local BONUS_CONSECUTIVE = 12
local PENALTY_GAP_START = 3
local PENALTY_GAP_MAX = 10
local BONUS_EXACT_PATH = 60
local BONUS_EXACT_BASENAME = 40
local BONUS_BASENAME_PREFIX = 20
-- Contiguous occurrences scored per term and path; the first ones are enough.
local MAX_OCCURRENCES = 16

local INVALID_BYTE = 0x110000

local function continuation(s, i)
	local b = string.byte(s, i)
	if b ~= nil and b >= 0x80 and b <= 0xBF then
		return b - 0x80
	end
	return nil
end

-- Decodes `s` into codepoint units without ever failing: each byte of an
-- invalid or overlong sequence becomes its own unit (INVALID_BYTE + byte), so
-- arbitrary byte strings are matched as-is and never rewritten. ASCII capitals
-- are folded in `low`; `orig` keeps case for camelCase boundaries; `start[u]`
-- is the unit's first byte and `unit_at[b]` maps a first byte back to its unit.
local function decode(s)
	local orig, low, start, unit_at = {}, {}, {}, {}
	local n, i, len = 0, 1, #s
	while i <= len do
		local b = string.byte(s, i)
		local cp, size = nil, 1
		if b < 0x80 then
			cp = b
		elseif b >= 0xC2 and b <= 0xDF then
			local c1 = continuation(s, i + 1)
			if c1 ~= nil then
				cp, size = (b - 0xC0) * 64 + c1, 2
			end
		elseif b >= 0xE0 and b <= 0xEF then
			local c1, c2 = continuation(s, i + 1), continuation(s, i + 2)
			if c1 ~= nil and c2 ~= nil and not (b == 0xE0 and c1 < 0x20) and not (b == 0xED and c1 >= 0x20) then
				cp, size = (b - 0xE0) * 4096 + c1 * 64 + c2, 3
			end
		elseif b >= 0xF0 and b <= 0xF4 then
			local c1, c2, c3 = continuation(s, i + 1), continuation(s, i + 2), continuation(s, i + 3)
			if
				c1 ~= nil
				and c2 ~= nil
				and c3 ~= nil
				and not (b == 0xF0 and c1 < 0x10)
				and not (b == 0xF4 and c1 >= 0x10)
			then
				cp, size = (b - 0xF0) * 262144 + c1 * 4096 + c2 * 64 + c3, 4
			end
		end
		if cp == nil then
			cp = INVALID_BYTE + b
		end
		n = n + 1
		orig[n] = cp
		low[n] = (cp >= 65 and cp <= 90) and cp + 32 or cp
		start[n] = i
		unit_at[i] = n
		i = i + size
	end
	return { orig = orig, low = low, start = start, unit_at = unit_at, n = n }
end

local function boundary_bonus(orig, i)
	if i == 1 then
		return BONUS_START
	end
	local p = orig[i - 1]
	if p == 47 then -- /
		return BONUS_SLASH
	end
	if p == 95 or p == 45 or p == 46 or p == 32 then -- _ - . space
		return BONUS_SEPARATOR
	end
	local c = orig[i]
	if p >= 97 and p <= 122 and c >= 65 and c <= 90 then
		return BONUS_CAMEL
	end
	return 0
end

local function score_positions(pos, m, orig, base_start)
	local score, prev = 0, nil
	for k = 1, m do
		local p = pos[k]
		score = score + SCORE_MATCH + boundary_bonus(orig, p)
		if p >= base_start then
			score = score + BONUS_BASENAME
		end
		if prev ~= nil then
			if p == prev + 1 then
				score = score + BONUS_CONSECUTIVE
			else
				score = score - PENALTY_GAP_START - math.min(p - prev - 2, PENALTY_GAP_MAX)
			end
		end
		prev = p
	end
	return score
end

-- Linear subsequence match from unit `from`: find the earliest end of a match,
-- walk back for the tightest start, and return both the right-leaning (from the
-- backward walk) and left-leaning (greedy from that start) placements.
local function subsequence(low, n, q, m, from)
	local qi, last = 1, nil
	for i = from, n do
		if low[i] == q[qi] then
			if qi == m then
				last = i
				break
			end
			qi = qi + 1
		end
	end
	if last == nil then
		return nil, nil
	end
	local right, first = {}, nil
	qi = m
	for i = last, from, -1 do
		if low[i] == q[qi] then
			right[qi] = i
			if qi == 1 then
				first = i
				break
			end
			qi = qi - 1
		end
	end
	local left = {}
	qi = 1
	for i = first, last do
		if low[i] == q[qi] then
			left[qi] = i
			if qi == m then
				break
			end
			qi = qi + 1
		end
	end
	return left, right
end

-- Best score and matched units of one query term in one decoded path, or nil.
local function score_term(path, d, base_start, base_lower, term)
	local q, m, n = term.units.low, term.units.n, d.n
	if m > n then
		return nil
	end
	local left, right = subsequence(d.low, n, q, m, 1)
	if left == nil then
		return nil
	end
	local best, best_pos = score_positions(left, m, d.orig, base_start), left
	local candidates = { right }
	if base_start > 1 then
		local bl, br = subsequence(d.low, n, q, m, base_start)
		if bl ~= nil then
			candidates[#candidates + 1] = bl
			candidates[#candidates + 1] = br
		end
	end
	local init, found = 1, 0
	while found < MAX_OCCURRENCES do
		local s, e = string.find(path.lower, term.lower, init, true)
		if s == nil then
			break
		end
		found = found + 1
		local u = d.unit_at[s]
		if u ~= nil and ((d.unit_at[e + 1] or n + 1) - u) == m then
			local pos = {}
			for k = 1, m do
				pos[k] = u + k - 1
			end
			candidates[#candidates + 1] = pos
		end
		init = s + 1
	end
	for _, pos in ipairs(candidates) do
		local score = score_positions(pos, m, d.orig, base_start)
		if score > best then
			best, best_pos = score, pos
		end
	end
	if path.lower == term.lower then
		best = best + BONUS_EXACT_PATH
	elseif base_lower == term.lower then
		best = best + BONUS_EXACT_BASENAME
	elseif string.sub(base_lower, 1, #term.lower) == term.lower then
		best = best + BONUS_BASENAME_PREFIX
	end
	return best, best_pos
end

local function file_path(file, index)
	if type(file) == "string" then
		return file
	end
	if type(file) == "table" and type(file.path) == "string" then
		return file.path
	end
	error("model.filter: files[" .. index .. "] has no string path", 3)
end

-- Query terms split on ASCII spaces and tabs; every term must match.
local function query_terms(query)
	local terms = {}
	if type(query) ~= "string" then
		return terms
	end
	for word in string.gmatch(query, "[^ \t]+") do
		local lower = ascii_lower(word)
		terms[#terms + 1] = { lower = lower, units = decode(lower) }
	end
	return terms
end

-- Fuzzy-filters `files` (path strings or tables with a string `path`) by
-- `query`: each space-separated term is a case-insensitive subsequence of the
-- path, compared by codepoint so UTF-8 never splits and raw bytes stay raw
-- (only ASCII letters fold case). Contiguous runs, the basename and segment or
-- word starts score higher; ties go to path byte order, then input order.
--
-- An empty query keeps every file: paths in `recent` (map path -> monotonic
-- number, higher is more recent) first, most recent first, then input order.
--
-- Returns `{file, index, score, positions}` per kept entry, each input entry at
-- most once; `positions` are sorted 1-based byte offsets of the first byte of
-- every matched character, for highlighting.
function M.filter(files, query, recent)
	recent = recent or {}
	local terms = query_terms(query)
	local out = {}
	if #terms == 0 then
		for i, file in ipairs(files) do
			local stamp = recent[file_path(file, i)]
			out[#out + 1] = { file = file, index = i, score = stamp or 0, recent = stamp, positions = {} }
		end
		table.sort(out, function(a, b)
			if a.recent ~= nil and b.recent ~= nil and a.recent ~= b.recent then
				return a.recent > b.recent
			end
			if (a.recent ~= nil) ~= (b.recent ~= nil) then
				return a.recent ~= nil
			end
			return a.index < b.index
		end)
		for _, entry in ipairs(out) do
			entry.recent = nil
		end
		return out
	end
	for i, file in ipairs(files) do
		local raw = file_path(file, i)
		local path = { raw = raw, lower = ascii_lower(raw) }
		local d = decode(raw)
		local base_start = 1
		for u = d.n, 1, -1 do
			if d.orig[u] == 47 then
				base_start = u + 1
				break
			end
		end
		local base_lower = base_start <= d.n and string.sub(path.lower, d.start[base_start]) or ""
		local total, matched = 0, {}
		for _, term in ipairs(terms) do
			local score, pos = score_term(path, d, base_start, base_lower, term)
			if score == nil then
				total = nil
				break
			end
			total = total + score
			for _, u in ipairs(pos) do
				matched[u] = true
			end
		end
		if total ~= nil then
			local positions = {}
			for u = 1, d.n do
				if matched[u] then
					positions[#positions + 1] = d.start[u]
				end
			end
			out[#out + 1] = { file = file, index = i, score = total, positions = positions, path = raw }
		end
	end
	table.sort(out, function(a, b)
		if a.score ~= b.score then
			return a.score > b.score
		end
		if a.path ~= b.path then
			return a.path < b.path
		end
		return a.index < b.index
	end)
	for _, entry in ipairs(out) do
		entry.path = nil
	end
	return out
end

return M
