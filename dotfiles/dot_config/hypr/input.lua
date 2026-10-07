hl.config({
  input = {
    kb_layout = "us",
    follow_mouse = 1,
    repeat_rate = 40,
    repeat_delay = 250,
    touchpad = {
      natural_scroll = true,
      clickfinger_behavior = true,
      disable_while_typing = true,
      scroll_factor = 0.4,
    },
  },
})

hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })
