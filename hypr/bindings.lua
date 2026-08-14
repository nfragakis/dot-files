-- Personal bindings migrated from dot-files/hypr/bindings.conf for Omarchy 4.
-- Omarchy's defaults load first, so replace conflicting keys explicitly.

local function rebind(keys, description, command, options)
  hl.unbind(keys)
  o.bind(keys, description, command, options)
end

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
  "/home/nfragakis/.config/whisper-stt/toggle-recording.sh"
)

rebind("SUPER + S", "Audio controls", "omarchy-shell shell toggle omarchy.audio")
rebind("SUPER + SHIFT + S", "Sleep screen", [[sleep 0.6; hyprctl dispatch dpms off]])
rebind("SUPER + SHIFT + P", "Screenshot", "omarchy-capture-screenshot")
rebind(
  "SUPER + SHIFT + V",
  "Screenrecording",
  "omarchy-capture-screenrecording --stop-recording || omarchy-menu toggle trigger.capture.screenrecord"
)
rebind("SUPER + SHIFT + T", "Activity", { webapp = "https://app.todoist.com/app/today" })
rebind("SUPER + SHIFT + E", "Activity", "omarchy-launch-or-focus evolution")
