local theme = require("theme")

hl.config({
  general = {
    gaps_in = 5,
    gaps_out = 10,
    border_size = 2,
    col = {
      active_border = { colors = { theme.accent, theme.magenta }, angle = 45 },
      inactive_border = theme.muted,
    },
    layout = "dwindle",
    resize_on_border = false,
    allow_tearing = true,                -- games opt in via `immediate` rules
  },

  decoration = {
    rounding = 0,
    shadow = {
      enabled = true,
      range = 2,
      render_power = 3,
      color = theme.shadow,
    },
    blur = {
      enabled = true,
      size = 3,
      passes = 1,
    },
  },

  animations = { enabled = true },

  dwindle = {
    preserve_split = true,
    force_split = 2,
  },

  misc = {
    disable_hyprland_logo = true,
    disable_splash_rendering = true,
    focus_on_activate = true,
    vrr = 2,
  },
})

hl.curve("easeOutQuint", { type = "bezier", points = { { 0.23, 1 }, { 0.32, 1 } } })
hl.animation({ leaf = "windows",    enabled = true, speed = 4.8, bezier = "easeOutQuint" })
hl.animation({ leaf = "fade",       enabled = true, speed = 3,   bezier = "easeOutQuint" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 2,   bezier = "easeOutQuint", style = "slide" })
