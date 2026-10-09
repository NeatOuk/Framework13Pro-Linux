-- Window rules: hl.window_rule({ name, match = { class/title = regex }, <effect> = value })

-- Apps (terminals) may ask to start maximized, covering the tile instead of splitting; ignore that. SUPER+F still fullscreens.
hl.window_rule({ name = "suppress-maximize", match = { class = ".*" }, suppress_event = "maximize" })

-- Telegram asks for focus on every new message (misc.focus_on_activate is on, for links and Settings): it only
-- gets marked urgent. Class may carry a ._<hash> suffix (Telegram's own launcher entry, see install.sh).
hl.window_rule({ name = "telegram-no-focus-steal", match = { class = "^(org\\.telegram\\.desktop.*)$" }, suppress_event = "activatefocus" })

-- Games may tear (general.allow_tearing) for lower latency.
hl.window_rule({ name = "tearing-steam-games", match = { class = "^(steam_app_.*)$" }, immediate = true })
hl.window_rule({ name = "tearing-gamescope",   match = { class = "^(gamescope)$" },     immediate = true })

-- Small settings dialogs float.
for _, class in ipairs({ "org.pulseaudio.pavucontrol", "blueman-manager", "nm-connection-editor", "org.fcitx.fcitx5-config-qt" }) do
  hl.window_rule({ name = "float-" .. class, match = { class = "^(" .. class .. ")$" }, float = true })
end
hl.window_rule({ name = "float-thunar-progress", match = { class = "^(thunar)$", title = "^(File Operation Progress)$" }, float = true })
hl.window_rule({ name = "float-steam-dialogs", match = { class = "^(steam)$", title = "^(Friends List|Steam Settings)$" }, float = true })

-- Jarvis windows (Ask / Work on repo / crash Diagnose) float in the middle; plain Claude/OpenCode windows tile.
hl.window_rule({
  name = "jarvis",
  match = { class = "^(fw13\\.jarvis)$" },
  float = true,
  size = { "(monitor_w*0.6)", "(monitor_h*0.7)" },
  center = true,
})
