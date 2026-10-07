-- Hyprland — Framework 13 (AMD Ryzen AI 9 HX 370 · Radeon 890M)
-- Clean, minimal look (Tokyo Night, flat borders); simple conventional keys.
-- Lua config (Hyprland ≥ 0.55; hyprlang .conf is deprecated). Check: Hyprland --verify-config -c <this file>
-- API reference for the installed version: /usr/share/hypr/stubs/hl.meta.lua

require("monitors")
require("displays")    -- fw-display-panel layout (written on Keep), overrides monitors
require("autostart")
require("looknfeel")
require("input")
require("windows")
require("bindings")
require("local")       -- machine-local, created once, never overwritten by chezmoi
