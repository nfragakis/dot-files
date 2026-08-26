-- Personal input settings migrated from dot-files/hypr/input.conf.
hl.config({
  input = {
    kb_layout = "us",
    kb_options = "compose:ralt,caps:escape",
    repeat_rate = 40,
    repeat_delay = 600,
    numlock_by_default = true,
    sensitivity = 0.4,
    touchpad = {
      natural_scroll = true,
      scroll_factor = 0.5,
    },
  },
})

o.window("(Alacritty|kitty|foot)", { scroll_touchpad = 1.5 })
o.window("com.mitchellh.ghostty", { scroll_touchpad = 1.0 })
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })
