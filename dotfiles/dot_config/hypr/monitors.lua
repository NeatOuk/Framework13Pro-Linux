-- Built-in panel: 2256x1504 or 2880x1920@120 — 1.6 is an exact integer scale on both.
hl.monitor({ output = "eDP-1", mode = "highrr", position = "auto", scale = 1.6 })
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })

hl.config({ xwayland = { force_zero_scaling = true } })
