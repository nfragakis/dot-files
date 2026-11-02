-- Native window commands only open host-owned blocks. Git never runs here.
local function open(cx, source)
    local args = source and { source } or nil
    if not cx:new_block("diff.viewer", args, "tab") then
        cx:toast("error", "Diff is not installed on this host", "Install the plugin on the machine running the repository.")
    end
end

tern.command({ id = "open", title = "Open diff viewer", group = "Git", run = function(cx) open(cx) end })
tern.command({ id = "pr", title = "Open pull request diff…", group = "Git", run = function(cx) open(cx, "pr") end })
