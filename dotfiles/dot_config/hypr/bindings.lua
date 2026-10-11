-- Simple, conventional keymap.  hl.bind("MODS + key", dispatcher, { options })
local term    = "uwsm app -- fw-term"  -- kitty or Ghostty, Settings → My Framework
local browser = "uwsm app -- chromium-browser"
local files   = "uwsm app -- thunar"
local editor  = "uwsm app -- code"
local menu    = [[fuzzel --launch-prefix="uwsm app -- "]]

local exec = hl.dsp.exec_cmd

-- Apps
hl.bind("SUPER + RETURN",    exec(term), { description = "Terminal" })
hl.bind("SUPER + SPACE",     exec(menu), { description = "App launcher" })
hl.bind("SUPER + B",         exec(browser), { description = "Browser" })
hl.bind("SUPER + E",         exec(files), { description = "Files" })
hl.bind("SUPER + SHIFT + C", exec(editor), { description = "VS Code" })
hl.bind("SUPER + C",         exec("fw-clip-key copy"), { description = "Copy" })
hl.bind("SUPER + X",         exec("fw-clip-key cut"), { description = "Cut" })
hl.bind("SUPER + SHIFT + A", exec("fw-jarvis open claude"), { description = "Claude in ~/jarvis" })   -- Claude in ~/jarvis, with Settings → Jarvis model/effort
hl.bind("SUPER + A",         exec("fw-jarvis"), { description = "Ask Jarvis" })
hl.bind("SUPER + I",         exec("fw-settings"), { description = "Settings" })
hl.bind("SUPER + W",         exec("fw-wallpaper"), { description = "Wallpaper picker" })
hl.bind("SUPER + SHIFT + T", exec("uwsm app -- fw-term --class fw13.btop -e btop"), { description = "Task manager (btop)" })

-- Windows
hl.bind("SUPER + Q",         hl.dsp.window.close(), { description = "Close window" })
hl.bind("SUPER + F",         hl.dsp.window.fullscreen({ action = "toggle" }), { description = "Fullscreen" })
hl.bind("SUPER + T",         hl.dsp.window.float({ action = "toggle" }), { description = "Float / tile window" })
hl.bind("SUPER + J",         hl.dsp.layout("togglesplit"), { description = "Flip split direction" })
hl.bind("SUPER + P",         hl.dsp.window.pseudo(), { description = "Pseudo-tile window" })
hl.bind("SUPER + S",         hl.dsp.workspace.toggle_special("scratchpad"), { description = "Show / hide scratchpad" })
hl.bind("SUPER + SHIFT + S", hl.dsp.window.move({ workspace = "special:scratchpad", follow = false }), { description = "Move window to scratchpad" })

-- Session
hl.bind("SUPER + L",         exec("loginctl lock-session"), { description = "Lock screen" })
hl.bind("SUPER + ESCAPE",    exec("fw-system-menu"), { description = "Power menu" })
hl.bind("SUPER + slash",     exec("fw-keys"), { description = "Keyboard shortcuts (this list)" })
hl.bind("SUPER + K",         exec("fw-keys"), { description = "Keyboard shortcuts (this list)" })

-- Focus / move / resize
local dirs = { left = { -50, 0 }, right = { 50, 0 }, up = { 0, -50 }, down = { 0, 50 } }
for dir, delta in pairs(dirs) do
  hl.bind("SUPER + " .. dir,         hl.dsp.focus({ direction = dir }), { description = "Focus " .. dir })
  hl.bind("SUPER + SHIFT + " .. dir, hl.dsp.window.move({ direction = dir }), { description = "Move window " .. dir })
  hl.bind("SUPER + CTRL + " .. dir,  hl.dsp.window.resize({ x = delta[1], y = delta[2], relative = true }),
          { repeating = true, description = "Resize window " .. dir })
end
hl.bind("SUPER + mouse:272", hl.dsp.window.drag(),   { mouse = true, description = "Drag window" })
hl.bind("SUPER + mouse:273", hl.dsp.window.resize(), { mouse = true, description = "Resize window" })

-- Workspaces — per screen: SUPER+N is workspace N of the focused screen (fw-workspaces)
for i = 1, 9 do
  hl.bind("SUPER + " .. i,         exec("fw-workspaces go " .. i), { description = "Workspace " .. i })
  hl.bind("SUPER + SHIFT + " .. i, exec("fw-workspaces move " .. i), { description = "Move window to workspace " .. i })
end
hl.bind("SUPER + TAB",        hl.dsp.focus({ workspace = "previous" }), { description = "Previous workspace" })
hl.bind("SUPER + mouse_down", hl.dsp.focus({ workspace = "m+1" }), { description = "Next workspace on this screen" })
hl.bind("SUPER + mouse_up",   hl.dsp.focus({ workspace = "m-1" }), { description = "Previous workspace on this screen" })

-- Clipboard / capture / tools
hl.bind("SUPER + V",             exec("fw-clipboard"), { description = "Clipboard history" })
hl.bind("PRINT",                 exec("fw-capture region"), { description = "Screenshot: area" })
hl.bind("SHIFT + PRINT",         exec("fw-capture screen"), { description = "Screenshot: screen" })
hl.bind("ALT + PRINT",           exec("fw-record"), { description = "Record screen (start / stop)" })
hl.bind("SUPER + PRINT",         exec("hyprpicker -a"), { description = "Colour picker" })
hl.bind("ALT + SHIFT + 4",       exec("fw-capture snip"), { description = "Snip area → edit (blur, crop)" })
hl.bind("ALT + SHIFT + 3",       exec("fw-capture window"), { description = "Snip window → edit (blur, crop)" })
hl.bind("SUPER + N",             exec("fw-nightlight"), { description = "Night light" })
hl.bind("SUPER + comma",         exec("makoctl dismiss"), { description = "Dismiss notification" })
hl.bind("SUPER + SHIFT + comma", exec("makoctl dismiss --all"), { description = "Dismiss all notifications" })
hl.bind("SUPER + SHIFT + B",     exec("uwsm app -- timeshift-launcher"), { description = "Timeshift snapshots" })
hl.bind("SUPER + period",        exec("fw-emoji"), { description = "Emoji picker" })
hl.bind("SUPER + equal",         exec("fw-calc"), { description = "Calculator" })

-- Laptop keys (work on the lock screen; volume/brightness repeat while held; fw-osd shows the new value)
local function held(d) return { locked = true, repeating = true, description = d } end
local function locked(d) return { locked = true, description = d } end
hl.bind("XF86AudioRaiseVolume",  exec("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+ && fw-osd volume"),  held("Volume up"))
hl.bind("XF86AudioLowerVolume",  exec("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%- && fw-osd volume"),       held("Volume down"))
hl.bind("XF86AudioMute",         exec("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle && fw-osd volume"),      locked("Mute"))
hl.bind("XF86AudioMicMute",      exec("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle && fw-osd mic"),       locked("Mute microphone"))
hl.bind("XF86MonBrightnessUp",   exec("brightnessctl -e4 -n2 set 5%+ && fw-osd brightness"),               held("Brightness up"))
hl.bind("XF86MonBrightnessDown", exec("brightnessctl -e4 -n2 set 5%- && fw-osd brightness"),               held("Brightness down"))
hl.bind("XF86AudioPlay",         exec("playerctl play-pause"),                                             locked("Play / pause"))
hl.bind("XF86AudioNext",         exec("playerctl next"),                                                   locked("Next track"))
hl.bind("XF86AudioPrev",         exec("playerctl previous"),                                               locked("Previous track"))
