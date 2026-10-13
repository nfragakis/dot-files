-- Personal input settings migrated from dot-files/hypr/input.conf.
hl.config({
  input = {
    kb_layout = "us",
    -- Caps Lock is handled by keyd: tap = Escape, hold = Super.
    kb_options = "compose:ralt",
    repeat_rate = 40,
    repeat_delay = 600,
    numlock_by_default = true,
    sensitivity = 0.4,
    -- Keep general scrolling at its previous speed; terminals are faster below.
    scroll_factor = 1.0,
    touchpad = {
      natural_scroll = true,
      scroll_factor = 0.5,
    },
  },
})

-- Keep terminal-specific touchpad scrolling at 3x.
o.window("(Alacritty|kitty|foot)", { scroll_touchpad = 3.0 })
o.window("com.mitchellh.ghostty", { scroll_touchpad = 3.0 })
-- Tern displays remote shells locally; its scroll speed belongs to this machine.
o.window("so.stencil.tern", { scroll_mouse = 3.0, scroll_touchpad = 3.0 })
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })
