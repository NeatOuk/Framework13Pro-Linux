-- Colours for looknfeel.lua. The palette is ~/.config/fw13/theme/hypr.lua, written by fw13.theme
-- (Tokyo Night or the wallpaper's colours). Tokyo Night below is the fallback: a missing or broken
-- file, or a missing or malformed key, never breaks Hyprland.
local fallback = {
  accent  = "rgb(7aa2f7)",
  magenta = "rgb(bb9af7)",
  bg      = "rgb(1a1b26)",
  muted   = "rgb(414868)",
  shadow  = "rgba(1a1a1aee)",
}

local config = os.getenv("XDG_CONFIG_HOME")
if not config or config == "" then
  config = (os.getenv("HOME") or "") .. "/.config"
end

local ok, theme = pcall(dofile, config .. "/fw13/theme/hypr.lua")
if not ok or type(theme) ~= "table" then
  return fallback
end
local function color(v)
  if type(v) ~= "string" then return false end
  local hex = v:match("^rgb%((%x+)%)$") or v:match("^rgba%((%x+)%)$")
  return hex ~= nil and (#hex == 6 or #hex == 8)
end
for key, value in pairs(fallback) do
  if not color(theme[key]) then
    theme[key] = value
  end
end
return theme
