-- Standalone tests for model.luau. Run with plain Lua 5.4:
--   lua tests/test_model.lua [path/to/model.luau]
-- Without an argument the module is loaded from ../model.luau next to this file.

local model_path = arg and arg[1]
if model_path == nil then
	local dir = string.match(arg and arg[0] or "", "^(.*)[/\\][^/\\]*$") or "."
	model_path = dir .. "/../model.luau"
end
local M = dofile(model_path)

local function show(v, depth)
	depth = depth or 0
	if type(v) == "string" then
		return string.format("%q", v)
	end
	if type(v) ~= "table" then
		return tostring(v)
	end
	if depth > 4 then
		return "{...}"
	end
	local keys = {}
	for k in pairs(v) do
		keys[#keys + 1] = k
	end
	table.sort(keys, function(a, b)
		return tostring(a) < tostring(b)
	end)
	local parts = {}
	for _, k in ipairs(keys) do
		parts[#parts + 1] = "[" .. show(k) .. "]=" .. show(v[k], depth + 1)
	end
	return "{" .. table.concat(parts, ", ") .. "}"
end

local function same(a, b)
	if type(a) ~= type(b) then
		return false
	end
	if type(a) ~= "table" then
		return a == b
	end
	for k, v in pairs(a) do
		if not same(v, b[k]) then
			return false
		end
	end
	for k in pairs(b) do
		if a[k] == nil then
			return false
		end
	end
	return true
end

local function eq(actual, expected, label)
	if not same(actual, expected) then
		error((label or "value") .. ": expected " .. show(expected) .. ", got " .. show(actual), 2)
	end
end

local tests = {}
local function test(name, fn)
	tests[#tests + 1] = { name = name, fn = fn }
end

local PATCH = table.concat({
	"diff --git a/src/a.lua b/src/a.lua",
	"index 1111111..2222222 100644",
	"--- a/src/a.lua",
	"+++ b/src/a.lua",
	"@@ -1,4 +1,4 @@ local M = {}",
	" local M = {}",
	"--- old comment",
	"+++ new comment",
	" \tindented  ",
	"-return M",
	"+return M.value",
	"@@ -10,2 +10,3 @@",
	" x = 1",
	'+y = "a.*(b)%d"',
	" z = 3",
	"diff --git a/b.txt b/b.txt",
	"index 3333333..4444444 100644",
	"--- a/b.txt",
	"+++ b/b.txt",
	"@@ -1 +1 @@",
	"-Foo",
	"\\ No newline at end of file",
	"+foo",
	"\\ No newline at end of file",
	"",
}, "\n")

local function paths(results)
	local out = {}
	for i, r in ipairs(results) do
		out[i] = type(r.file) == "string" and r.file or r.file.path
	end
	return out
end

test("parse splits hunks by their counts, keeping ---/+++ rows inside hunks", function()
	local hunks, unparsed = M.parse(PATCH)
	eq(#hunks, 3, "hunk count")
	eq(unparsed, {}, "unparsed")
	local h1 = hunks[1]
	eq(h1.header, "@@ -1,4 +1,4 @@ local M = {}", "header")
	eq(h1.section, "local M = {}", "section")
	eq({ h1.old_start, h1.old_count, h1.new_start, h1.new_count }, { 1, 4, 1, 4 }, "h1 ranges")
	eq(h1.lines, {
		" local M = {}",
		"--- old comment",
		"+++ new comment",
		" \tindented  ",
		"-return M",
		"+return M.value",
	}, "h1 lines")
	eq(h1.incomplete, nil, "h1 complete")
	local h2 = hunks[2]
	eq({ h2.old_start, h2.old_count, h2.new_start, h2.new_count }, { 10, 2, 10, 3 }, "h2 ranges")
	eq(h2.section, "", "h2 section")
	eq(h2.lines, { " x = 1", '+y = "a.*(b)%d"', " z = 3" }, "h2 lines stop before next file metadata")
	local h3 = hunks[3]
	eq({ h3.old_start, h3.old_count, h3.new_start, h3.new_count }, { 1, 1, 1, 1 }, "omitted counts are 1")
	eq(h3.lines, {
		"-Foo",
		"\\ No newline at end of file",
		"+foo",
		"\\ No newline at end of file",
	}, "no-newline markers kept on both sides")
end)

test("parse reads zero counts for added and deleted files", function()
	local added = M.parse("--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+one\n+two\n")
	eq(#added, 1, "added hunks")
	eq({ added[1].old_start, added[1].old_count, added[1].new_start, added[1].new_count }, { 0, 0, 1, 2 }, "added ranges")
	eq(added[1].lines, { "+one", "+two" }, "added lines")
	local deleted = M.parse("--- a/old.txt\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-one\n-two\n")
	eq({ deleted[1].old_start, deleted[1].old_count, deleted[1].new_start, deleted[1].new_count }, { 1, 2, 0, 0 }, "deleted ranges")
	eq(deleted[1].lines, { "-one", "-two" }, "deleted lines")
	local removal = M.parse("@@ -3 +2,0 @@\n-gone\n")
	eq({ removal[1].old_start, removal[1].old_count, removal[1].new_start, removal[1].new_count }, { 3, 1, 2, 0 }, "removal ranges")
end)

test("parse keeps CRLF, non-ASCII bytes and whitespace exactly", function()
	local hunks = M.parse("@@ -1,2 +1,2 @@\r\n  two  spaces\t\r\n-a\r\n+é ünï\r\n")
	eq(#hunks, 1, "hunks")
	eq(hunks[1].header, "@@ -1,2 +1,2 @@\r", "header keeps CR")
	eq(hunks[1].section, "", "section drops CR")
	eq(hunks[1].lines, { "  two  spaces\t\r", "-a\r", "+é ünï\r" }, "lines")
end)

test("parse flags incomplete hunks and reports unreadable headers", function()
	local truncated = M.parse("@@ -1,3 +1,3 @@\n a\n-b\n")
	eq(truncated[1].lines, { " a", "-b" }, "truncated lines")
	eq(truncated[1].incomplete, true, "truncated flagged")
	local broken = M.parse("@@ -1,2 +1,2 @@\n a\n-b\n-c\n@@ -9 +9 @@\n x\n")
	eq(#broken, 2, "header after a short hunk starts a new hunk")
	eq(broken[1].lines, { " a", "-b" }, "short hunk stops at the row its counts cannot hold")
	eq(broken[1].incomplete, true, "short hunk flagged")
	eq(broken[2].lines, { " x" }, "next hunk")
	local hunks, unparsed = M.parse("@@@ -1,2 -1,2 +1,3 @@@\n  a\n+ b\n")
	eq(#hunks, 0, "combined diff hunks")
	eq(unparsed, { "@@@ -1,2 -1,2 +1,3 @@@" }, "combined header reported")
	eq(M.parse(""), {}, "empty patch")
	eq(M.parse("Binary files a/x.png and b/x.png differ\n"), {}, "binary patch")
	eq(pcall(M.parse, nil), false, "non-string patch errors")
end)

test("parse stores a stripped empty context row as a single space", function()
	local hunks = M.parse("@@ -1,2 +1,2 @@\n\n-x\n+y\n")
	eq(hunks[1].lines, { " ", "-x", "+y" }, "lines")
	eq(hunks[1].incomplete, nil, "complete")
end)

test("rows number old and new sides and skip markers", function()
	local hunks = M.parse(PATCH)
	eq(M.rows(hunks[1]), {
		{ kind = "context", old_line = 1, new_line = 1 },
		{ kind = "delete", old_line = 2 },
		{ kind = "add", new_line = 2 },
		{ kind = "context", old_line = 3, new_line = 3 },
		{ kind = "delete", old_line = 4 },
		{ kind = "add", new_line = 4 },
	}, "h1 rows")
	eq(M.rows(hunks[3]), {
		{ kind = "delete", old_line = 1 },
		{ kind = "marker" },
		{ kind = "add", new_line = 1 },
		{ kind = "marker" },
	}, "h3 rows")
end)

test("search is plain, smartcase and numbers both sides", function()
	local hunks = M.parse(PATCH)
	eq(M.search(hunks, ""), {}, "empty query")
	eq(M.search(hunks, nil), {}, "nil query")
	eq(M.search(hunks, "return"), {
		{ hunk = 1, line = 5, text = "return M", kind = "delete", col = 1, old_line = 4 },
		{ hunk = 1, line = 6, text = "return M.value", kind = "add", col = 1, new_line = 4 },
	}, "deleted and added rows")
	eq(M.search(hunks, '.*(b)%d'), {
		{ hunk = 2, line = 2, text = 'y = "a.*(b)%d"', kind = "add", col = 7, new_line = 11 },
	}, "metacharacters are literal")
	eq(#M.search(hunks, "a.b"), 0, "dot is not a wildcard")
	eq(#M.search(hunks, "M"), 3, "uppercase query is case-sensitive")
	eq(#M.search(hunks, "m"), 5, "lowercase query ignores case")
	eq(M.search(hunks, "Foo"), {
		{ hunk = 3, line = 1, text = "Foo", kind = "delete", col = 1, old_line = 1 },
	}, "Foo only matches Foo")
	eq(M.search(hunks, "foo"), {
		{ hunk = 3, line = 1, text = "Foo", kind = "delete", col = 1, old_line = 1 },
		{ hunk = 3, line = 3, text = "foo", kind = "add", col = 1, new_line = 1 },
	}, "foo matches both")
	eq(M.search(hunks, "--"), {
		{ hunk = 1, line = 2, text = "-- old comment", kind = "delete", col = 1, old_line = 2 },
	}, "row prefix is not searched")
	eq(#M.search(hunks, "newline"), 0, "no-newline marker is not searched")
	eq(#M.search(hunks, "b.txt"), 0, "file metadata is not searched")
	eq(M.search(hunks, "z = 3"), {
		{ hunk = 2, line = 3, text = "z = 3", kind = "context", col = 1, old_line = 11, new_line = 12 },
	}, "context row carries both numbers")
	eq(M.search(M.parse("@@ -1 +1 @@\n-ÉTÉ été\n"), "été"), {
		{ hunk = 1, line = 1, text = "ÉTÉ été", kind = "delete", col = 7, old_line = 1 },
	}, "non-ASCII bytes are matched as written")
end)

local VIEW_PATCH = table.concat({
	"@@ -1,3 +1,4 @@",
	" a",
	"-b",
	"-c",
	"\\ No newline at end of file",
	"+B",
	"+C",
	"+D",
	"\\ No newline at end of file",
	"@@ -10,2 +11,1 @@ fn()",
	" x",
	"-y",
	"",
}, "\n")
local MARK = "\\ No newline at end of file"

local function shape(rows)
	local out = {}
	for i, row in ipairs(rows) do
		out[i] = { row.hunk, row.kind, row.old_start, row.new_start, row.lines, row.hunk_lines }
	end
	return out
end

test("layout unified gives one row per diff line, markers attached", function()
	local hunks = M.parse(VIEW_PATCH)
	local rows = M.layout(hunks, "unified")
	eq(shape(rows), {
		{ 1, "context", 1, 1, { " a" }, { 1 } },
		{ 1, "delete", 2, 2, { "-b" }, { 2 } },
		{ 1, "delete", 3, 2, { "-c", MARK }, { 3, 4 } },
		{ 1, "add", 4, 2, { "+B" }, { 5 } },
		{ 1, "add", 4, 3, { "+C" }, { 6 } },
		{ 1, "add", 4, 4, { "+D", MARK }, { 7, 8 } },
		{ 2, "context", 10, 11, { " x" }, { 1 } },
		{ 2, "delete", 11, 12, { "-y" }, { 2 } },
	}, "rows")
	eq({ rows[1].first, rows[1].header, rows[2].first, rows[2].header }, { true, "@@ -1,3 +1,4 @@" }, "hunk 1 boundary")
	eq({ rows[7].first, rows[7].header }, { true, "@@ -10,2 +11,1 @@ fn()" }, "hunk 2 boundary")
	eq({ rows[3].line, rows[6].line, rows[3].split }, { 3, 7 }, "first hunk line, not split")
	eq(M.layout(M.parse("@@ -0,0 +0,0 @@\n"), "unified"), {}, "empty hunk has no rows")
	eq(M.layout(hunks, nil), rows, "default mode is unified")
end)

test("layout split pairs deletions with additions in order", function()
	local rows = M.layout(M.parse(VIEW_PATCH), "split")
	eq(shape(rows), {
		{ 1, "context", 1, 1, { " a" }, { 1 } },
		{ 1, "change", 2, 2, { "-b", "+B" }, { 2, 5 } },
		{ 1, "change", 3, 3, { "-c", MARK, "+C" }, { 3, 4, 6 } },
		{ 1, "add", 4, 4, { "+D", MARK }, { 7, 8 } },
		{ 2, "context", 10, 11, { " x" }, { 1 } },
		{ 2, "delete", 11, 12, { "-y" }, { 2 } },
	}, "rows")
	eq({ rows[1].split, rows[2].split, rows[4].split, rows[6].split }, { nil, true, true, true }, "split flags")
	local extra = M.layout(M.parse("@@ -5,3 +5,1 @@\n-p\n-q\n-r\n+P\n"), "split")
	eq(shape(extra), {
		{ 1, "change", 5, 5, { "-p", "+P" }, { 1, 4 } },
		{ 1, "delete", 6, 6, { "-q" }, { 2 } },
		{ 1, "delete", 7, 6, { "-r" }, { 3 } },
	}, "leftover deletions keep the next new line number")
end)

test("row lookups find hunk starts and search hits", function()
	local hunks = M.parse(VIEW_PATCH)
	local rows = M.layout(hunks, "split")
	eq(M.hunk_row(rows, 2), 5, "hunk 2 start")
	eq(M.hunk_row(rows, 3), nil, "missing hunk")
	eq(M.row_at(rows, 1, 6), 3, "paired addition")
	eq(M.row_at(rows, 1, 4), 3, "marker")
	eq(M.row_at(rows, 2, 2), 6, "second hunk")
	eq(M.row_at(rows, 2, 9), nil, "missing line")
	local hit = M.search(hunks, "D")[1]
	eq(M.row_at(rows, hit.hunk, hit.line), 4, "search hit row")
end)

test("clamp keeps the viewport inside the rows", function()
	eq(M.clamp(5, 8, 6), 3, "past the end")
	eq(M.clamp(-2, 8, 6), 1, "before the start")
	eq(M.clamp(2, 8, 6), 2, "inside")
	eq(M.clamp(3, 4, 10), 1, "viewport taller than rows")
	eq(M.clamp(1, 0, 10), 1, "no rows")
end)

test("window groups visible rows per hunk with exact starts", function()
	local hunks = M.parse(VIEW_PATCH)
	local unified = M.layout(hunks, "unified")
	eq(M.window(unified, 1, 100), {
		{ hunk = 1, old_start = 1, new_start = 1, lines = hunks[1].lines, first_row = 1, last_row = 6, header = "@@ -1,3 +1,4 @@" },
		{ hunk = 2, old_start = 10, new_start = 11, lines = hunks[2].lines, first_row = 7, last_row = 8, header = "@@ -10,2 +11,1 @@ fn()" },
	}, "whole unified diff")
	eq(M.window(unified, 4, 2), {
		{ hunk = 1, old_start = 4, new_start = 2, lines = { "+B", "+C" }, first_row = 4, last_row = 5 },
	}, "unified slice mid hunk has no header")
	local split = M.layout(hunks, "split")
	eq(M.window(split, 2, 3), {
		{ hunk = 1, old_start = 2, new_start = 2, lines = { "-b", "-c", MARK, "+B", "+C", "+D", MARK }, first_row = 2, last_row = 4 },
	}, "split run reordered deletions first")
	eq(M.window(split, 3, 3), {
		{ hunk = 1, old_start = 3, new_start = 3, lines = { "-c", MARK, "+C", "+D", MARK }, first_row = 3, last_row = 4 },
		{ hunk = 2, old_start = 10, new_start = 11, lines = { " x" }, first_row = 5, last_row = 5, header = "@@ -10,2 +11,1 @@ fn()" },
	}, "split window across hunks")
	eq(M.window(split, 4, 1), {
		{ hunk = 1, old_start = 4, new_start = 4, lines = { "+D", MARK }, first_row = 4, last_row = 4 },
	}, "leftover addition row")
	eq(M.window(split, 0, 1)[1].first_row, 1, "first clipped to 1")
	eq(M.window(split, 99, 3)[1].first_row, 6, "first clipped to the last row")
	eq(M.window({}, 1, 10), {}, "no rows")
	eq(M.window(split, 1, 0), {}, "empty viewport")
end)

test("filter prefers contiguous basename matches", function()
	local files = { "src/models/view.luau", "docs/readme.md", "tests/test_model.lua", "model.luau" }
	local results = M.filter(files, "model")
	eq(paths(results), { "model.luau", "tests/test_model.lua", "src/models/view.luau" }, "order")
	eq(results[1].index, 4, "original index")
	eq(results[1].positions, { 1, 2, 3, 4, 5 }, "positions")
	eq(paths(M.filter(files, "MODEL")), paths(results), "case-insensitive")
	local fuzzy = M.filter(files, "tmd")
	eq(paths(fuzzy), { "tests/test_model.lua" }, "subsequence")
	eq(M.filter(files, "zzz"), {}, "no match")
	eq(M.filter(files, "modelz"), {}, "every query character must match")
	eq(paths(M.filter(files, "src view")), { "src/models/view.luau" }, "every term must match")
end)

test("filter ranks segment starts over scattered letters", function()
	local files = { "a/fsabcdefgo.txt", "lib/foo.lua" }
	eq(paths(M.filter(files, "fo")), { "lib/foo.lua", "a/fsabcdefgo.txt" }, "order")
end)

test("filter breaks ties by path then input order and never duplicates", function()
	local files = { "b/x.lua", "a/x.lua", "a/x.lua" }
	local results = M.filter(files, "x")
	eq(#results, 3, "each entry once")
	eq({ results[1].index, results[2].index, results[3].index }, { 2, 3, 1 }, "path order then input order")
	eq(results[1].score, results[3].score, "equal scores")
end)

test("filter empty query orders recent first then input order", function()
	local files = { { path = "a" }, { path = "b" }, { path = "c" }, { path = "d" } }
	local results = M.filter(files, "", { c = 5, a = 9, zzz = 100 })
	eq(paths(results), { "a", "c", "b", "d" }, "order")
	eq({ results[1].index, results[2].index, results[3].index, results[4].index }, { 1, 3, 2, 4 }, "indices")
	eq(rawequal(results[1].file, files[1]), true, "original reference")
	eq(paths(M.filter(files, "  ")), { "a", "b", "c", "d" }, "blank query, no recent")
	eq(M.filter({}, ""), {}, "no files")
	eq(pcall(M.filter, { {} }, "x"), false, "file without a path errors")
end)

test("filter matches codepoints and keeps raw bytes intact", function()
	local files = { "docs/café.md", "docs/cafe.md", "bad/\255\254name" }
	eq(paths(M.filter(files, "é")), { "docs/café.md" }, "codepoint query")
	eq(paths(M.filter(files, "cafe")), { "docs/cafe.md" }, "é is not e")
	eq(M.filter(files, "fé")[1].positions, { 8, 9 }, "byte offsets of matched characters")
	local raw = M.filter(files, "name")
	eq(#raw, 1, "invalid UTF-8 path still matches")
	eq(raw[1].file, "bad/\255\254name", "path unchanged")
	eq(raw[1].positions, { 7, 8, 9, 10 }, "raw positions")
	eq(#M.filter(files, "\255"), 1, "invalid byte matches itself")
end)

test("next wraps both ways and handles empty lists", function()
	eq(M.next(nil, 0, 1), nil, "empty")
	eq(M.next(1, 0, -1), nil, "empty with index")
	eq(M.next(3, 3, 1), 1, "wrap forward")
	eq(M.next(1, 3, -1), 3, "wrap backward")
	eq(M.next(2, 5, 7), 4, "large delta")
	eq(M.next(2, 5, -12), 5, "large negative delta")
	eq(M.next(nil, 3, 1), 1, "no index forward")
	eq(M.next(nil, 3, -1), 3, "no index backward")
	eq(M.next(9, 3, 1), 1, "stale index forward")
	eq(M.next(nil, 3, 0), 1, "no index, no step")
	eq(M.next(2, 3), 3, "default step")
end)

local failed = 0
for _, t in ipairs(tests) do
	local ok, err = pcall(t.fn)
	if ok then
		print("ok   " .. t.name)
	else
		failed = failed + 1
		print("FAIL " .. t.name .. "\n     " .. tostring(err))
	end
end
print(string.format("%d passed, %d failed", #tests - failed, failed))
if failed > 0 then
	if os.exit then
		os.exit(1)
	end
	error(failed .. " test(s) failed")
end
