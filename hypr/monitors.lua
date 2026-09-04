-- Personal monitor settings migrated from dot-files/hypr/monitors.conf.
hl.env("GDK_SCALE", "2")

-- Keep the built-in display as the layout anchor. Any external display is
-- centered directly above it, so moving the pointer up crosses screens.
hl.monitor({ output = "eDP-1", mode = "preferred", position = "0x0", scale = "auto" })
hl.monitor({ output = "", mode = "preferred", position = "auto-center-up", scale = "auto" })
