-- Simple, conventional keymap.  hl.bind("MODS + key", dispatcher, { options })
local term    = "uwsm app -- fw-term"  -- kitty or Ghostty, Settings → fw13
local browser = "uwsm app -- chromium-browser"
local files   = "uwsm app -- thunar"
local editor  = "uwsm app -- code"
local menu    = [[fuzzel --launch-prefix="uwsm app -- "]]

local exec = hl.dsp.exec_cmd

-- Apps
hl.bind("SUPER + RETURN",    exec(term))
hl.bind("SUPER + SPACE",     exec(menu))
hl.bind("SUPER + B",         exec(browser))
hl.bind("SUPER + E",         exec(files))
hl.bind("SUPER + SHIFT + C", exec(editor))
hl.bind("SUPER + C",         exec("fw-clip-key copy"))
hl.bind("SUPER + X",         exec("fw-clip-key cut"))
hl.bind("SUPER + SHIFT + A", exec("uwsm app -- fw-term -e claude"))
hl.bind("SUPER + A",         exec("fw-jarvis"))
hl.bind("SUPER + I",         exec("fw-settings"))
hl.bind("SUPER + W",         exec("fw-wallpaper"))
hl.bind("SUPER + SHIFT + T", exec("uwsm app -- fw-term --class fw13.btop -e btop"))

-- Windows
hl.bind("SUPER + Q",         hl.dsp.window.close())
hl.bind("SUPER + F",         hl.dsp.window.fullscreen({ action = "toggle" }))
hl.bind("SUPER + T",         hl.dsp.window.float({ action = "toggle" }))
hl.bind("SUPER + J",         hl.dsp.layout("togglesplit"))
hl.bind("SUPER + P",         hl.dsp.window.pseudo())
hl.bind("SUPER + S",         hl.dsp.workspace.toggle_special("scratchpad"))
hl.bind("SUPER + SHIFT + S", hl.dsp.window.move({ workspace = "special:scratchpad", follow = false }))

-- Session
hl.bind("SUPER + L",         exec("loginctl lock-session"))
hl.bind("SUPER + ESCAPE",    exec("fw-system-menu"))

-- Focus / move / resize
local dirs = { left = { -50, 0 }, right = { 50, 0 }, up = { 0, -50 }, down = { 0, 50 } }
for dir, delta in pairs(dirs) do
  hl.bind("SUPER + " .. dir,         hl.dsp.focus({ direction = dir }))
  hl.bind("SUPER + SHIFT + " .. dir, hl.dsp.window.move({ direction = dir }))
  hl.bind("SUPER + CTRL + " .. dir,  hl.dsp.window.resize({ x = delta[1], y = delta[2], relative = true }), { repeating = true })
end
hl.bind("SUPER + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind("SUPER + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Workspaces — per screen: SUPER+N is workspace N of the focused screen (fw-workspaces)
for i = 1, 9 do
  hl.bind("SUPER + " .. i,         exec("fw-workspaces go " .. i))
  hl.bind("SUPER + SHIFT + " .. i, exec("fw-workspaces move " .. i))
end
hl.bind("SUPER + TAB",        hl.dsp.focus({ workspace = "previous" }))
hl.bind("SUPER + mouse_down", hl.dsp.focus({ workspace = "m+1" }))
hl.bind("SUPER + mouse_up",   hl.dsp.focus({ workspace = "m-1" }))

-- Clipboard / capture / tools
hl.bind("SUPER + V",             exec("fw-clipboard"))
hl.bind("PRINT",                 exec("fw-capture region"))
hl.bind("SHIFT + PRINT",         exec("fw-capture screen"))
hl.bind("ALT + PRINT",           exec("fw-record"))
hl.bind("SUPER + PRINT",         exec("hyprpicker -a"))
hl.bind("SUPER + N",             exec("fw-nightlight"))
hl.bind("SUPER + comma",         exec("makoctl dismiss"))
hl.bind("SUPER + SHIFT + comma", exec("makoctl dismiss --all"))
hl.bind("SUPER + SHIFT + B",     exec("uwsm app -- timeshift-launcher"))
hl.bind("SUPER + period",        exec("fw-emoji"))
hl.bind("SUPER + equal",         exec("fw-calc"))

-- Laptop keys (work on the lock screen; volume/brightness repeat while held; fw-osd shows the new value)
local held = { locked = true, repeating = true }
hl.bind("XF86AudioRaiseVolume",  exec("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+ && fw-osd volume"),  held)
hl.bind("XF86AudioLowerVolume",  exec("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%- && fw-osd volume"),       held)
hl.bind("XF86AudioMute",         exec("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle && fw-osd volume"),      { locked = true })
hl.bind("XF86AudioMicMute",      exec("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle && fw-osd mic"),       { locked = true })
hl.bind("XF86MonBrightnessUp",   exec("brightnessctl -e4 -n2 set 5%+ && fw-osd brightness"),               held)
hl.bind("XF86MonBrightnessDown", exec("brightnessctl -e4 -n2 set 5%- && fw-osd brightness"),               held)
hl.bind("XF86AudioPlay",         exec("playerctl play-pause"),                                             { locked = true })
hl.bind("XF86AudioNext",         exec("playerctl next"),                                                   { locked = true })
hl.bind("XF86AudioPrev",         exec("playerctl previous"),                                               { locked = true })
