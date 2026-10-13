-- Personal bindings migrated from dot-files/hypr/bindings.conf for Omarchy 4.
-- Omarchy's defaults load first, so replace conflicting keys explicitly.

local function rebind(keys, description, command, options)
  hl.unbind(keys)
  o.bind(keys, description, command, options)
end

-- Leave native Alt navigation untouched in Tern; bind it only elsewhere.
local function update_window_navigation()
  local window = hl.get_active_window()
  local tern_focused = window and window.class == "so.stencil.tern"
  for _, binding in ipairs({
    { "H", "left", "l" },
    { "J", "down", "d" },
    { "K", "up", "u" },
    { "L", "right", "r" },
  }) do
    local keys = "ALT + " .. binding[1]
    hl.unbind(keys)
    if not tern_focused then
      o.bind(keys, "Focus " .. binding[2] .. " window", hl.dsp.focus({ direction = binding[3] }))
    end
  end
end

hl.on("window.active", update_window_navigation)
update_window_navigation()

rebind("SUPER + ALT + RETURN", "Tmux", { omarchy = "terminal-tmux" })
rebind("SUPER + RETURN", "Terminal", { omarchy = "terminal" })
rebind("SUPER + SHIFT + RETURN", "Browser", { omarchy = "browser" })
rebind("SUPER + SHIFT + F", "File manager", { omarchy = "nautilus" })
rebind("SUPER + SHIFT + B", "Browser", { omarchy = "browser" })
rebind("SUPER + SHIFT + ALT + B", "Browser (private)", { omarchy = "browser --private" })
rebind("SUPER + SHIFT + M", "Music", { omarchy = "spotify" })
rebind("SUPER + SHIFT + ALT + M", "Music TUI", { tui = "cliamp", focus = true })
rebind("SUPER + SHIFT + C", "Telegram", "uwsm app -- Telegram")
rebind("SUPER + SHIFT + N", "Editor", { omarchy = "editor" })
rebind("SUPER + SHIFT + D", "Docker", { tui = "lazydocker" })
rebind("SUPER + SHIFT + G", "Gmail", { webapp = "https://mail.google.com" })
rebind("SUPER + SHIFT + A", "ChatGPT", { webapp = "https://chatgpt.com" })
rebind("SUPER + SHIFT + ALT + A", "Grok", { webapp = "https://grok.com" })
rebind("SUPER + SHIFT + Y", "YouTube", { webapp = "https://youtube.com/" })
rebind("SUPER + SHIFT + X", "X", { webapp = "https://x.com/" })

rebind(
  "SUPER + SHIFT + L",
  "Whisper STT",
  "omarchy-shell whisper-stt toggle"
)

rebind("SUPER + S", "Audio controls", "omarchy-shell shell toggle omarchy.audio")
rebind("SUPER + SHIFT + S", "Sleep screen", [[sleep 0.6; hyprctl dispatch dpms off]])
rebind("SUPER + SHIFT + P", "Screenshot", "omarchy-capture-screenshot")
-- Omarchy's default for this is SUPER + CTRL + PRINT, which is not reachable
-- with one hand. The default binding is left in place.
rebind("SUPER + SHIFT + O", "Extract text (OCR) from screenshot", "omarchy-capture-text")
rebind(
  "SUPER + SHIFT + V",
  "Screenrecording",
  "omarchy-capture-screenrecording --stop-recording || omarchy-menu toggle trigger.capture.screenrecord"
)
rebind("SUPER + SHIFT + T", "Todoist", "omarchy shell shell toggle io.github.aryan-techie.todoist")
rebind("SUPER + SHIFT + E", "Omamail", "omarchy shell shell toggle omamail '{}'")

-- flea --default: begin. Written by `flea --default`; `flea --default off` removes the block whole.
hl.unbind("SUPER + SHIFT + F")
o.bind("SUPER + SHIFT + F", "File manager", { launch = 'flea --gui' })
hl.unbind("SUPER + ALT + SHIFT + F")
o.bind("SUPER + ALT + SHIFT + F", "File manager (cwd)", { launch = 'flea --gui "$(omarchy-cmd-terminal-cwd)"' })
-- flea --default: end.

-- flea --picker: begin. Written by `flea --picker`; `flea --picker off` removes the block whole.
o.window("com.thisisgm.flea.picker", { tag = "+floating-window" })
-- flea --picker: end.

require("hypr.tern-clipboard")
